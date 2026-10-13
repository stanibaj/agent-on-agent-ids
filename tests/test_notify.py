from dataclasses import replace

import httpx
import pytest

from aoaids import notify
from aoaids.config import Settings


@pytest.fixture
def sent(monkeypatch):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(202, request=httpx.Request("POST", url))

    monkeypatch.setattr(notify.httpx, "post", post)
    return calls


@pytest.fixture
def settings(monkeypatch, tmp_path):
    monkeypatch.setenv("OPIK_CONFIG_PATH", str(tmp_path / "none"))
    return Settings.load(env_file=None)


def test_pagerduty_triggers_and_resolves_one_incident(settings, sent):
    pd = replace(settings, pagerduty_routing_key="R")
    for resolved in (False, True):
        assert notify.send(pd, "pagerduty", title="t", text="x", link="https://o.example", dedup_key="k", resolved=resolved)
    assert [c[1]["json"]["event_action"] for c in sent] == ["trigger", "resolve"]
    assert {c[1]["json"]["dedup_key"] for c in sent} == {"k"} and sent[0][1]["json"]["routing_key"] == "R"


def test_chat_channels_hear_only_problems(settings, sent):
    slack = replace(settings, slack_webhook_url="https://hooks.slack.example/x")
    assert not notify.send(slack, "slack", title="t", text="x", link="l", dedup_key="k", resolved=True)
    assert notify.send(slack, "slack", title="t", text="x", link="l", dedup_key="k", resolved=False)
    assert sent == [("https://hooks.slack.example/x", {"json": {"text": "*t*\nx\n<l|Traces in Opik>"}, "timeout": 30})]


def test_generic_webhook_is_signed_like_opik(settings, sent):
    hook = replace(settings, alert_webhook_url="https://h.example", alert_webhook_secret="s3")
    notify.send(hook, "webhook", title="t", text="x", link="l", dedup_key="k", resolved=False)
    assert sent[0][1]["headers"] == {"Authorization": "Bearer s3"}
    assert sent[0][1]["json"]["event_type"] == "aoa_ids:coverage"
