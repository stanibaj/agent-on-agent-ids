"""Install the AOA-IDS judge into Comet Opik as an online-evaluation rule plus webhook alerts (REST API)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from ..config import Settings
from ..spec import Spec, rename_variables

# Opik injects the trace's spans as JSON for the {{spans}} built-in; mapped mode uses it as the trajectory.
OPIK_VARIABLE_NAMES = {"trajectory": "spans"}
ROLE = {"system": "SYSTEM", "user": "USER"}


def rule_payload(spec: Spec, settings: Settings, project_id: str) -> dict[str, Any]:
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
        response = self.http.request(method, path, **kwargs)
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

    def scored_traces(self, project_id: str, score: str, limit: int = 10) -> list[dict]:
        filters = json.dumps([{"field": "feedback_scores", "key": score, "operator": "is_not_empty", "value": ""}])
        body = self._call("GET", "v1/private/traces",
                          params={"project_id": project_id, "filters": filters, "size": limit, "truncate": True}).json()
        return body.get("content", [])


def install(spec: Spec, settings: Settings) -> list[str]:
    if not settings.opik_project:
        raise OpikError("Set OPIK_PROJECT_NAME in .env to the project that receives your agent's traces.")
    client = OpikClient(settings)
    project_id = client.project_id(settings.opik_project)
    log = [f"project {settings.opik_project} ({project_id})"]

    payload = rule_payload(spec, settings, project_id)
    existing = client.find_rule(project_id, settings.rule_name)
    if existing:
        client.update_rule(existing["id"], payload)
        log.append(f"rule {settings.rule_name} updated ({existing['id']})")
    else:
        log.append(f"rule {settings.rule_name} created ({client.create_rule(payload)})")

    alerts = alert_payloads(spec, settings, project_id)
    if not alerts:
        log.append("alerts skipped (AOA_ALERT_WEBHOOK_URL not set)")
    current = {a["name"]: a for a in client.find_alerts({a["name"] for a in alerts}, project_id)}
    for alert in alerts:
        if alert["name"] in current:
            client.update_alert(current[alert["name"]]["id"], alert)
            log.append(f"alert {alert['name']} updated ({current[alert['name']]['id']})")
        else:
            log.append(f"alert {alert['name']} created ({client.create_alert(alert)})")
    return log


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
