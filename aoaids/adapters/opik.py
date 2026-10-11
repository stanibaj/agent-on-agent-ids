"""Install the AOA-IDS judge into Comet Opik as an online-evaluation rule plus webhook alerts (REST API)."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import httpx
import yaml

from ..config import Settings
from ..spec import JUDGE_DIR, Spec, rename_variables

SMOKE_FILE = JUDGE_DIR / "smoke" / "smoke_traces.yaml"
SMOKE_TAG = "aoa-ids-smoke-test"

# Opik injects the trace's spans as JSON for the {{spans}} built-in; mapped mode uses it as the trajectory.
OPIK_VARIABLE_NAMES = {"trajectory": "spans"}
ROLE = {"system": "SYSTEM", "user": "USER"}


def _decision_code(spec: Spec, settings: Settings) -> dict[str, Any]:
    # Opik's decision-model rules: one user message holding only data, BOOLEAN scores whose descriptions are
    # the yes/no questions, no system prompt / tools / temperature / cost cap.
    state = rename_variables(spec.decision_state(settings.agent_profile_file), OPIK_VARIABLE_NAMES)
    return {
        "model": {"name": settings.judge_model},
        "messages": [{"role": "USER", "content": state}],
        "variables": {"input": settings.var_input, "output": settings.var_output},
        "schema": [{"name": q["name"], "type": "BOOLEAN", "description": " ".join(q["question"].split())}
                   for q in spec.decision["questions"]],
    }


def _chat_code(spec: Spec, settings: Settings) -> dict[str, Any]:
    mode = settings.judge_mode
    if mode not in ("agent", "mapped"):
        raise ValueError(f"AOA_JUDGE_MODE must be 'agent' or 'mapped', got {mode!r}")
    messages = [
        {"role": ROLE[m.role], "content": rename_variables(m.content, OPIK_VARIABLE_NAMES)}
        for m in spec.messages(mode=mode, output="scores", profile_file=settings.agent_profile_file)
    ]
    # Agent mode reads the whole trace through {{trace}}; nothing to map.
    variables = {} if mode == "agent" else {"input": settings.var_input, "output": settings.var_output}
    code: dict[str, Any] = {
        "model": {"name": settings.judge_model, "temperature": settings.judge_temperature},
        "messages": messages,
        "variables": variables,
        "schema": [
            {"name": s["name"], "type": s["type"], "description": s["description"]} for s in spec.scores
        ],
    }
    if settings.max_cost_usd is not None:
        code["max_cost_usd"] = settings.max_cost_usd
    return code


def rule_payload(spec: Spec, settings: Settings, project_id: str) -> dict[str, Any]:
    code = _decision_code(spec, settings) if spec.is_decision_model(settings.judge_model) else _chat_code(spec, settings)
    return {
        "type": "llm_as_judge",
        "action": "evaluator",
        "name": settings.rule_name,
        "project_ids": [project_id],
        "sampling_rate": settings.sampling_rate,
        "enabled": True,
        "filters": [],
        "code": code,
    }


def alert_payloads(spec: Spec, settings: Settings, project_id: str) -> list[dict[str, Any]]:
    if not settings.alert_webhook_url:
        return []
    webhook: dict[str, Any] = {"name": "aoa-ids", "url": settings.alert_webhook_url}
    if settings.alert_webhook_secret:
        webhook["secret_token"] = settings.alert_webhook_secret
    levels = {"actionable": {"actionable"}, "any": {"any"}, "both": {"actionable", "any"}}.get(settings.alert_on)
    if levels is None:
        raise ValueError(f"AOA_ALERT_ON must be actionable, any or both, got {settings.alert_on!r}")
    alerts = []
    for policy in spec.alerting:
        if policy["level"] not in levels:
            continue
        alerts.append({
            "name": policy["name"],
            "enabled": True,
            "alert_type": "general",
            "project_id": project_id,
            "metadata": {"source": "agent-on-agent-ids", "spec_version": spec.version},
            "webhook": webhook,
            "triggers": [{
                "event_type": "trace:feedback_score",
                "trigger_configs": [{
                    "type": "threshold:feedback_score",
                    # Keys from opik-backend AlertTriggerConfig; window is in seconds.
                    "config_value": {
                        "name": policy["score"],
                        "operator": policy["operator"],
                        "threshold": str(policy["threshold"]),
                        "window": str(settings.alert_window_seconds),
                    },
                }],
            }],
        })
    return alerts


class OpikError(RuntimeError):
    pass


class OpikClient:
    def __init__(self, settings: Settings):
        headers = {"content-type": "application/json"}
        if settings.opik_api_key:
            headers["Authorization"] = settings.opik_api_key
        if settings.opik_workspace:
            headers["Comet-Workspace"] = settings.opik_workspace
        self.http = httpx.Client(base_url=settings.opik_url + "/", headers=headers, timeout=30)

    def _call(self, method: str, path: str, **kwargs) -> httpx.Response:
        for attempt in range(4):  # back off on rate limits (Opik Cloud returns 429)
            response = self.http.request(method, path, **kwargs)
            if response.status_code != 429:
                break
            time.sleep(2 ** attempt * 2)
        if response.status_code >= 400:
            raise OpikError(f"{method} {path} -> {response.status_code}: {response.text[:500]}")
        return response

    def project_id(self, name: str) -> str:
        for project in self._call("GET", "v1/private/projects", params={"name": name, "size": 100}).json()["content"]:
            if project["name"] == name:
                return project["id"]
        raise OpikError(f"Opik project {name!r} not found. Log at least one trace to it first, or fix OPIK_PROJECT_NAME.")

    def find_rule(self, project_id: str, name: str) -> dict | None:
        page = self._call("GET", "v1/private/automations/evaluators",
                          params={"project_id": project_id, "name": name, "size": 100}).json()
        return next((r for r in page.get("content", []) if r["name"] == name), None)

    def create_rule(self, payload: dict) -> str:
        response = self._call("POST", "v1/private/automations/evaluators", json=payload)
        return response.headers.get("location", "").rstrip("/").rsplit("/", 1)[-1]

    def update_rule(self, rule_id: str, payload: dict) -> None:
        self._call("PATCH", f"v1/private/automations/evaluators/{rule_id}", json=payload)

    def delete_rules(self, project_id: str, ids: list[str]) -> None:
        self._call("POST", "v1/private/automations/evaluators/delete", params={"project_id": project_id}, json={"ids": ids})

    def rule_logs(self, rule_id: str) -> list[dict]:
        return self._call("GET", f"v1/private/automations/evaluators/{rule_id}/logs").json().get("content", [])

    def find_alerts(self, names: set[str], project_id: str) -> list[dict]:
        found, page = [], 1
        while True:
            body = self._call("GET", "v1/private/alerts", params={"page": page, "size": 100}).json()
            for alert in body.get("content", []):
                if alert.get("name") in names and alert.get("project_id") in (None, project_id):
                    found.append(alert)
            if page * 100 >= body.get("total", 0):
                return found
            page += 1

    def create_alert(self, payload: dict) -> str:
        response = self._call("POST", "v1/private/alerts", json=payload)
        return response.headers.get("location", "").rstrip("/").rsplit("/", 1)[-1]

    def update_alert(self, alert_id: str, payload: dict) -> None:
        self._call("PUT", f"v1/private/alerts/{alert_id}", json={**payload, "id": alert_id})

    def delete_alerts(self, ids: list[str]) -> None:
        self._call("POST", "v1/private/alerts/delete", json={"ids": ids})

    def create_spans(self, spans: list[dict]) -> None:
        self._call("POST", "v1/private/spans/batch", json={"spans": spans})

    def create_traces(self, traces: list[dict]) -> None:
        self._call("POST", "v1/private/traces/batch", json={"traces": traces})

    def get_trace(self, trace_id: str) -> dict | None:
        response = self.http.get(f"v1/private/traces/{trace_id}")
        return response.json() if response.status_code == 200 else None

    def delete_traces(self, ids: list[str]) -> None:
        if ids:
            self._call("POST", "v1/private/traces/delete", json={"ids": ids})

    def traces(self, project_id: str, size: int = 20, filters: list | None = None, truncate: bool = True) -> list[dict]:
        params: dict[str, Any] = {"project_id": project_id, "size": size, "truncate": truncate}
        if filters:
            params["filters"] = json.dumps(filters)
        return self._call("GET", "v1/private/traces", params=params).json().get("content", [])

    def spans(self, project_id: str, trace_id: str) -> list[dict]:
        return self._call("GET", "v1/private/spans", params={
            "project_id": project_id, "trace_id": trace_id, "size": 500, "truncate": False}).json().get("content", [])

    def scored_traces(self, project_id: str, score: str, limit: int = 10) -> list[dict]:
        filters = json.dumps([{"field": "feedback_scores", "key": score, "operator": "is_not_empty", "value": ""}])
        body = self._call("GET", "v1/private/traces",
                          params={"project_id": project_id, "filters": filters, "size": limit, "truncate": True}).json()
        return body.get("content", [])


def _uuid7() -> str:
    """Time-ordered UUIDv7, the id format Opik expects for traces and spans."""
    value = (int(time.time() * 1000) & ((1 << 48) - 1)) << 80 | 0x7 << 76
    rand = int.from_bytes(os.urandom(10), "big")
    value |= ((rand >> 62) & 0xFFF) << 64 | 0b10 << 62 | rand & ((1 << 62) - 1)
    return str(uuid.UUID(int=value))


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def context_check(client: OpikClient, spec: Spec, settings: Settings, project_id: str, sample: int = 10) -> str:
    """Estimate how many recent traces fit a decision model's context once {{spans}} is rendered."""
    limit = spec.decision["max_context_tokens"]
    state = spec.decision_state(settings.agent_profile_file)
    sizes = []
    for trace in client.traces(project_id, size=sample * 2, truncate=False):
        if trace.get("name") == "online_evaluation" or SMOKE_TAG in (trace.get("tags") or []):
            continue
        spans = [{k: sp.get(k) for k in ("name", "type", "input", "output")} for sp in client.spans(project_id, trace["id"])]
        chars = len(state) + len(json.dumps(trace.get("input"))) + len(json.dumps(trace.get("output"))) + len(json.dumps(spans))
        sizes.append(chars / 3.5)  # JSON-heavy text: ~3.5 characters per token
        if len(sizes) == sample:
            break
    if not sizes:
        return "context check: no traces yet to measure"
    fits = sum(size <= limit for size in sizes)
    note = (f"context check: {fits}/{len(sizes)} recent traces fit {settings.judge_model}'s {limit // 1000}k context "
            f"(largest ≈{max(sizes) / 1000:.0f}k tokens).")
    if fits < len(sizes):
        note += (" Opik skips larger traces (see rule logs) -- they are NOT scored. For full coverage use a small "
                 "fast chat model in agent mode, e.g. AOA_JUDGE_MODEL=~anthropic/claude-haiku-latest.")
    return note


def smoke_test(client: OpikClient, spec: Spec, settings: Settings, project_id: str, say: Callable[[str], None],
               timeout: int = 420, keep: bool = False) -> bool:
    """Log 5 known traces (3 attacks, 2 benign), wait for the judge and check every verdict."""
    cases = yaml.safe_load(SMOKE_FILE.read_text())
    run_id, start = _uuid7()[:8], datetime.now(timezone.utc)
    spans, traces, expected = [], [], {}
    for case in cases:
        trace_id = _uuid7()
        expected[trace_id] = case
        for i, step in enumerate(case["trajectory"]):
            spans.append({"id": _uuid7(), "trace_id": trace_id, "project_name": settings.opik_project,
                          "name": f"Tool: {step['tool']}", "type": "tool", "input": step["input"],
                          "output": step["output"], "start_time": _iso(start + timedelta(seconds=i)),
                          "end_time": _iso(start + timedelta(seconds=i + 1))})
        traces.append({"id": trace_id, "project_name": settings.opik_project, "name": case["id"], "source": "sdk",
                       "input": {"role": "user", "content": case["input"]}, "output": {"content": case["output"]},
                       "tags": [SMOKE_TAG], "metadata": {"aoa_ids_smoke_run": run_id, "expected": case["label"]},
                       "start_time": _iso(start), "end_time": _iso(start + timedelta(seconds=len(case["trajectory"]) + 1))})
    # Spans first, then the finished trace: the order most SDKs produce, and what {{spans}} needs.
    client.create_spans(spans)
    time.sleep(3)
    client.create_traces(traces)
    attacks = sum(c["label"] == "incident" for c in cases)
    say(f"smoke test: logged {len(cases)} traces ({attacks} attacks, {len(cases) - attacks} benign, tag {SMOKE_TAG}); "
        f"waiting up to {timeout}s for verdicts...")

    verdicts: dict[str, dict] = {}
    deadline = time.time() + timeout
    while len(verdicts) < len(expected) and time.time() < deadline:
        time.sleep(10)
        for trace_id in set(expected) - set(verdicts):
            scores = {f["name"]: f for f in ((client.get_trace(trace_id) or {}).get("feedback_scores") or [])}
            if "aoa_ids_incident" in scores and "aoa_ids_alert" in scores:
                verdicts[trace_id] = scores

    detected = clean = 0
    for trace_id, case in expected.items():
        scores = verdicts.get(trace_id)
        if scores is None:
            say(f"  ?  {case['id']:38} expected {case['label']:8} -> NOT SCORED within {timeout}s")
            continue
        incident, alert = scores["aoa_ids_incident"]["value"] >= 0.5, scores["aoa_ids_alert"]["value"] >= 0.5
        is_attack = case["label"] == "incident"
        ok = incident == is_attack and alert == is_attack
        detected += ok and is_attack
        clean += ok and not is_attack
        if spec.is_decision_model(settings.judge_model):
            # Decision models store only "Probability: x" as the reason; the mapping comes from category scores.
            yes = {name: f["value"] >= 0.5 for name, f in scores.items() if name.startswith("aoa_ids_cat_")}
            mapping = spec.decision_mapping(yes)
            reason = (f"categories:{','.join(n.removeprefix('aoa_ids_cat_') for n, v in yes.items() if v) or '-'} | "
                      + " | ".join(f"{k}:{','.join(v)}" for k, v in mapping.items()))
        else:
            reason = " ".join((scores["aoa_ids_incident"].get("reason") or "").split())
        reason = reason[:150]
        say(f"  {'✓' if ok else '✗'}  {case['id']:38} expected {case['label']:8} -> incident={int(incident)} "
            f"alert={int(alert)}  {reason}")
    passed = detected == attacks and clean == len(cases) - attacks
    say(f"smoke test {'PASSED' if passed else 'FAILED'}: detected {detected}/{attacks} attacks, "
        f"{clean}/{len(cases) - attacks} benign traces clean.")
    if not passed and len(verdicts) < len(expected):
        say("  hint: unscored traces usually mean the model is not available to Opik's AI provider "
            "(check `aoa-ids status opik` -> rule_logs) or the rule is still warming up.")

    if keep:
        say(f"smoke traces kept (filter: tags contains {SMOKE_TAG}).")
    else:
        # Remove the smoke traces and the judge-run traces Opik logs for them.
        judge_runs = [t["id"] for t in client.traces(project_id, size=100, filters=[
            {"field": "name", "operator": "=", "value": "online_evaluation"}])
            if (t.get("metadata") or {}).get("evaluated_trace_id") in expected]
        client.delete_traces(list(expected) + judge_runs)
        say(f"smoke traces removed ({len(expected)} traces, {len(judge_runs)} judge runs).")
    return passed


def install(spec: Spec, settings: Settings, smoke: bool = False, keep_smoke: bool = False,
            say: Callable[[str], None] = print) -> bool:
    if not settings.opik_project:
        raise OpikError("Set OPIK_PROJECT_NAME in .env to the project that receives your agent's traces.")
    client = OpikClient(settings)
    project_id = client.project_id(settings.opik_project)
    decision = spec.is_decision_model(settings.judge_model)
    say(f"project {settings.opik_project} ({project_id})")
    say(f"judge: {settings.judge_model} ({'decision model, mapped {{spans}}' if decision else settings.judge_mode + ' mode'})")

    payload = rule_payload(spec, settings, project_id)
    existing = client.find_rule(project_id, settings.rule_name)
    if existing:
        client.update_rule(existing["id"], payload)
        say(f"rule {settings.rule_name} updated ({existing['id']})")
    else:
        say(f"rule {settings.rule_name} created ({client.create_rule(payload)})")
    if decision:
        try:
            say(context_check(client, spec, settings, project_id))
        except OpikError as error:  # informational only; never block an install on it
            say(f"context check skipped: {error}")

    alerts = alert_payloads(spec, settings, project_id)
    current = {a["name"]: a for a in client.find_alerts({p["name"] for p in spec.alerting}, project_id)}
    if smoke:
        if current:
            say(f"note: existing alerts {sorted(current)} will see the smoke test's attacks (a free delivery test).")
        if not smoke_test(client, spec, settings, project_id, say, keep=keep_smoke):
            say("alerts not created/updated because the smoke test failed.")
            return False

    # Alerts are created after the smoke test so a fresh install does not page anyone for test traces.
    if not alerts:
        say("alerts skipped (AOA_ALERT_WEBHOOK_URL not set)")
    for alert in alerts:
        if alert["name"] in current:
            client.update_alert(current[alert["name"]]["id"], alert)
            say(f"alert {alert['name']} updated ({current[alert['name']]['id']})")
        else:
            say(f"alert {alert['name']} created ({client.create_alert(alert)})")
    return True


def uninstall(spec: Spec, settings: Settings) -> list[str]:
    client = OpikClient(settings)
    project_id = client.project_id(settings.opik_project)
    log = []
    rule = client.find_rule(project_id, settings.rule_name)
    if rule:
        client.delete_rules(project_id, [rule["id"]])
        log.append(f"rule {settings.rule_name} deleted")
    alerts = client.find_alerts({p["name"] for p in spec.alerting}, project_id)
    if alerts:
        client.delete_alerts([a["id"] for a in alerts])
        log.extend(f"alert {a['name']} deleted" for a in alerts)
    return log or ["nothing to remove"]


def status(spec: Spec, settings: Settings) -> dict[str, Any]:
    client = OpikClient(settings)
    project_id = client.project_id(settings.opik_project)
    rule = client.find_rule(project_id, settings.rule_name)
    incident_score = next(s["name"] for s in spec.scores if s.get("primary"))
    traces = client.scored_traces(project_id, incident_score)
    return {
        "project_id": project_id,
        "rule": rule and {k: rule.get(k) for k in ("id", "name", "enabled", "sampling_rate", "type")},
        "rule_logs": client.rule_logs(rule["id"])[:10] if rule else [],
        "alerts": [{k: a.get(k) for k in ("id", "name", "enabled")}
                   for a in client.find_alerts({p["name"] for p in spec.alerting}, project_id)],
        "recent_scored_traces": [
            {"id": t["id"], "name": t.get("name"),
             "scores": {s["name"]: (s["value"], s.get("reason")) for s in t.get("feedback_scores", [])
                        if s["name"].startswith("aoa_ids_")}}
            for t in traces
        ],
    }
