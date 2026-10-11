from dataclasses import replace

import pytest

from aoaids.adapters import opik
from aoaids.config import Settings
from aoaids.spec import Spec


@pytest.fixture
def settings(monkeypatch, tmp_path):
    monkeypatch.setenv("OPIK_CONFIG_PATH", str(tmp_path / "none"))
    for name in ("AOA_ALERT_WEBHOOK_URL", "AOA_JUDGE_MODE", "AOA_ALERT_ON"):
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


def test_any_incident_alert_is_opt_in(settings):
    alerts = opik.alert_payloads(Spec(), replace(settings, alert_webhook_url="https://h.example", alert_on="both"), "p1")
    assert [a["name"] for a in alerts] == ["aoa_ids_actionable", "aoa_ids_any_incident"]
