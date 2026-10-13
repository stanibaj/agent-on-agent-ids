"""Send AOA-IDS's own health notices (e.g. low judge coverage) to the alert destination configured in .env.

Detection alerts are delivered by the observability platform. A judge that stops scoring raises no score, so
nothing there can alert on it; `aoa-ids coverage --notify` (from cron or CI) sends this notice itself.
"""

from __future__ import annotations

import httpx

from .config import Settings

PAGERDUTY_EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"


def send(settings: Settings, kind: str, *, title: str, text: str, link: str, dedup_key: str, resolved: bool) -> bool:
    """Deliver one notice; returns False when there was nothing to send. Only PagerDuty receives resolutions,
    so chat channels hear about problems, not about every healthy run."""
    if resolved and kind != "pagerduty":
        return False
    if kind == "pagerduty":
        body = {"routing_key": settings.pagerduty_routing_key, "dedup_key": dedup_key,
                "event_action": "resolve" if resolved else "trigger",
                "payload": {"summary": title, "source": "aoa-ids", "severity": "warning",
                            "custom_details": {"details": text}},
                "links": [{"href": link, "text": "Traces in Opik"}]}
        response = httpx.post(PAGERDUTY_EVENTS_URL, json=body, timeout=30)
    elif kind == "slack":
        response = httpx.post(settings.slack_webhook_url, json={"text": f"*{title}*\n{text}\n<{link}|Traces in Opik>"},
                              timeout=30)
    elif kind == "telegram":
        response = httpx.post(f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage", timeout=30,
                              json={"chat_id": settings.telegram_chat_id, "text": f"⚠️ {title}\n{text}\n{link}"})
    else:
        headers = {"Authorization": f"Bearer {settings.alert_webhook_secret}"} if settings.alert_webhook_secret else {}
        response = httpx.post(settings.alert_webhook_url, headers=headers, timeout=30, json={
            "source": "aoa-ids", "event_type": "aoa_ids:coverage", "title": title, "text": text, "link": link,
            "dedup_key": dedup_key, "status": "resolved" if resolved else "triggered"})
    response.raise_for_status()
    return True
