from dataclasses import replace

import httpx
import pytest

from aoaids.adapters import opik
from aoaids.config import Settings
from aoaids.spec import Spec


@pytest.fixture
def settings(monkeypatch, tmp_path):
    monkeypatch.setenv("OPIK_CONFIG_PATH", str(tmp_path / "none"))
    for name in ("AOA_ALERT_WEBHOOK_URL", "AOA_TELEGRAM_BOT_TOKEN", "AOA_TELEGRAM_CHAT_ID", "AOA_SLACK_WEBHOOK_URL",
                 "AOA_PAGERDUTY_ROUTING_KEY", "AOA_JUDGE_MODE", "AOA_ALERT_ON", "AOA_JUDGE_MODEL", "AOA_SAMPLING_RATE"):
        monkeypatch.delenv(name, raising=False)
    return Settings.load(env_file=None)


def test_agent_mode_uses_trace_without_mapping(settings):
    payload = opik.rule_payload(Spec(), settings, "p1")
    assert payload["code"]["variables"] == {}
    assert "{{trace}}" in payload["code"]["messages"][1]["content"]
    assert [s["name"] for s in payload["code"]["schema"]] == ["aoa_ids_incident", "aoa_ids_alert", "aoa_ids_severity", "aoa_ids_confidence"]
    assert payload["action"] == "evaluator" and payload["project_ids"] == ["p1"]


def test_mapped_mode_uses_spans_builtin(settings):
    payload = opik.rule_payload(Spec(), replace(settings, judge_mode="mapped"), "p1")
    user = payload["code"]["messages"][1]["content"]
    assert "{{spans}}" in user and "{{trajectory}}" not in user
    assert payload["code"]["variables"] == {"input": "input", "output": "output"}


def test_payload_validates_against_opik_sdk_model(settings):
    types = pytest.importorskip("opik.rest_api.types")
    payload = opik.rule_payload(Spec(), settings, "p1")
    code = dict(payload["code"])
    code["schema_"] = code.pop("schema")  # the SDK names the wire field `schema` as `schema_` in Python
    types.AutomationRuleEvaluatorWrite_LlmAsJudge(**{**payload, "code": code})


def test_alerts_only_with_webhook(settings):
    assert opik.alert_payloads(Spec(), settings, "p1") == []
    alerts = opik.alert_payloads(Spec(), replace(settings, alert_webhook_url="https://hook.example/x"), "p1")
    assert [a["name"] for a in alerts] == ["aoa_ids_actionable"]
    config = alerts[0]["triggers"][0]["trigger_configs"][0]
    assert config["type"] == "threshold:feedback_score"
    assert config["config_value"] == {"name": "aoa_ids_alert", "operator": ">", "threshold": "0", "window": "300"}


def test_telegram_alert_posts_to_bot_api(settings):
    tg = replace(settings, telegram_bot_token="123:abc", telegram_chat_id="42", opik_workspace="ws", opik_project="my-agent")
    [alert] = opik.alert_payloads(Spec(), tg, "p1")
    url = httpx.URL(alert["webhook"]["url"])
    assert url.path == "/bot123:abc/sendMessage"
    assert url.params["chat_id"] == "42"
    assert "aoa_ids_actionable" in url.params["text"] and "/ws/projects/p1/traces" in url.params["text"]
    with pytest.raises(ValueError):
        opik.alert_payloads(Spec(), replace(tg, alert_webhook_url="https://h.example"), "p1")


def test_slack_alert_uses_native_type(settings):
    slack = replace(settings, slack_webhook_url="https://hooks.slack.example/T/B/x", opik_url="https://opik.example/api")
    [alert] = opik.alert_payloads(Spec(), slack, "p1")
    assert alert["alert_type"] == "slack" and alert["webhook"]["url"] == "https://hooks.slack.example/T/B/x"
    assert alert["metadata"]["base_url"] == "https://opik.example"  # Opik links each flagged trace from here


def test_pagerduty_alert_puts_routing_key_in_metadata(settings):
    [alert] = opik.alert_payloads(Spec(), replace(settings, pagerduty_routing_key="R0UT1NG"), "p1")
    assert alert["alert_type"] == "pagerduty" and alert["webhook"]["url"] == "https://events.pagerduty.com/v2/enqueue"
    assert alert["metadata"]["routing_key"] == "R0UT1NG"


def test_only_one_alert_destination(settings):
    with pytest.raises(ValueError, match="only one"):
        opik.alert_payloads(Spec(), replace(settings, slack_webhook_url="https://s.example",
                                            pagerduty_routing_key="R"), "p1")


@pytest.mark.parametrize("kind", ["webhook", "slack", "pagerduty"])
def test_alert_payloads_validate_against_opik_sdk_model(settings, kind):
    types = pytest.importorskip("opik.rest_api.types")
    values = {"webhook": {"alert_webhook_url": "https://h.example"}, "slack": {"slack_webhook_url": "https://s.example"},
              "pagerduty": {"pagerduty_routing_key": "R"}}[kind]
    for alert in opik.alert_payloads(Spec(), replace(settings, **values), "p1"):
        types.AlertWrite(**alert)


@pytest.mark.parametrize("model,provider", [
    ("~anthropic/claude-haiku-latest", "openrouter"), ("typesafe/jev-1.13", "openrouter"),
    ("claude-haiku-4-5-20251001", "anthropic"), ("gpt-5-mini", "openai"), ("gemini-3.5-flash", "gemini"),
    ("vertex_ai/gemini-2.5-flash", "vertex-ai"), ("custom-llm/vllm/Qwen/Qwen3-32B", "custom-llm"), ("mystery", None)])
def test_judge_provider(model, provider):
    assert opik.judge_provider(model) == provider


class FakeClient:
    def __init__(self, keys=(), traces=(), logs=(), rule=None):
        self.keys, self._traces, self.logs = list(keys), list(traces), list(logs)
        self.rule = rule if rule is not None else {"id": "r1", "name": "aoa_ids_incident_detector", "enabled": True}

    def provider_keys(self):
        return self.keys

    def traces_between(self, project_id, start, end, limit):
        return self._traces

    def find_rule(self, project_id, name):
        return self.rule

    def rule_logs(self, rule_id):
        return self.logs


def test_provider_check_finds_missing_provider(settings):
    ok, note = opik.provider_check(FakeClient(keys=[{"provider": "openrouter"}]),
                                   replace(settings, judge_model="claude-haiku-4-5-20251001"))
    assert not ok and "anthropic" in note


def test_provider_check_self_hosted_model_must_be_listed(settings):
    model = "custom-llm/vllm/Qwen/Qwen3-32B"
    key = {"provider": "custom-llm", "provider_name": "vllm", "base_url": "http://vllm.internal:8000/v1",
           "configuration": {"models": f"custom-llm/vllm/other, {model}"}}
    assert opik.provider_check(FakeClient(keys=[key]), replace(settings, judge_model=model))[0]
    assert not opik.provider_check(FakeClient(keys=[{**key, "configuration": {"models": "x"}}]),
                                   replace(settings, judge_model=model))[0]


def _trace(id, scored, finished=True, name="run"):
    return {"id": id, "name": name, "start_time": "2026-10-12T10:00:00Z", "end_time": "x" if finished else None,
            "feedback_scores": [{"name": "aoa_ids_incident", "value": 0}] if scored else []}


def test_coverage_counts_misses_and_explains_them(settings):
    traces = [_trace(f"00000000-0000-0000-0000-00000000000{i}", scored=i < 7) for i in range(9)]
    traces += [_trace("00000000-0000-0000-0000-000000000009", scored=False, finished=False),
               _trace("judge-run", scored=False, name="online_evaluation")]  # the judge's own trace is not counted
    logs = [{"level": "ERROR", "message": "Unexpected error while scoring traceId '00000000-0000-0000-0000-000000000007' "
                                          "with rule 'x': 402 credits"}]
    report = opik.coverage(FakeClient(traces=traces, logs=logs), Spec(), settings, "p1")
    assert (report["traces"], report["scored"], report["healthy"]) == (10, 7, False)
    reasons = {t["id"][-1]: t["reason"] for t in report["unscored_traces"]}
    assert "402 credits" in reasons["7"] and reasons["9"].startswith("trace never finished")
    assert report["unscored_by_reason"] == {"judge error": 1, "no error logged": 1, "trace never finished": 1}


def test_coverage_allows_for_sampling(settings):
    traces = [_trace(f"t{i}", scored=i < 5) for i in range(10)]
    report = opik.coverage(FakeClient(traces=traces), Spec(), replace(settings, sampling_rate=0.5), "p1")
    assert report["coverage"] == 1.0 and report["healthy"]
    assert opik.coverage(FakeClient(traces=[]), Spec(), settings, "p1")["healthy"] is None


def test_any_incident_alert_is_opt_in(settings):
    alerts = opik.alert_payloads(Spec(), replace(settings, alert_webhook_url="https://h.example", alert_on="both"), "p1")
    assert [a["name"] for a in alerts] == ["aoa_ids_actionable", "aoa_ids_any_incident"]


def test_decision_model_rule_shape(settings):
    payload = opik.rule_payload(Spec(), replace(settings, judge_model="typesafe/jev-1.13"), "p1")
    code = payload["code"]
    assert [m["role"] for m in code["messages"]] == ["USER"]  # no system prompt for decision models
    assert "{{spans}}" in code["messages"][0]["content"] and "{{trajectory}}" not in code["messages"][0]["content"]
    assert code["model"] == {"name": "typesafe/jev-1.13"} and "max_cost_usd" not in code
    assert {s["type"] for s in code["schema"]} == {"BOOLEAN"}
    names = [s["name"] for s in code["schema"]]
    assert names[:2] == ["aoa_ids_incident", "aoa_ids_alert"]  # alert policies work for both engines


def test_decision_mapping_from_categories():
    mapping = Spec().decision_mapping({"aoa_ids_cat_indirect_injection": True, "aoa_ids_cat_persistence": True})
    assert "AML.T0051.001" in mapping["atlas"] and "T1098.004" in mapping["attack"]
