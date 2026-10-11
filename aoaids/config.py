"""Settings from environment (.env) with ~/.opik.config as a fallback for Opik credentials."""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

OPIK_CLOUD_URL = "https://www.comet.com/opik/api"


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _opik_config_file() -> dict[str, str]:
    path = Path(os.environ.get("OPIK_CONFIG_PATH", Path.home() / ".opik.config"))
    if not path.exists():
        return {}
    parser = configparser.ConfigParser()
    parser.read(path)
    return dict(parser["opik"]) if parser.has_section("opik") else {}


@dataclass(frozen=True)
class Settings:
    opik_url: str
    opik_api_key: str | None
    opik_workspace: str | None
    opik_project: str | None
    judge_mode: str
    judge_model: str
    judge_temperature: float
    sampling_rate: float
    max_cost_usd: float | None
    agent_profile_file: str | None
    var_input: str
    var_output: str
    alert_webhook_url: str | None
    alert_webhook_secret: str | None
    alert_window_seconds: int
    alert_on: str
    rule_name: str

    @classmethod
    def load(cls, env_file: str | None = ".env") -> "Settings":
        if env_file:
            load_dotenv(env_file, override=False)
        file_cfg = _opik_config_file()
        max_cost = _env("AOA_MAX_COST_USD", "0.25")
        return cls(
            opik_url=(_env("OPIK_URL_OVERRIDE") or file_cfg.get("url_override") or OPIK_CLOUD_URL).rstrip("/"),
            opik_api_key=_env("OPIK_API_KEY") or file_cfg.get("api_key"),
            opik_workspace=_env("OPIK_WORKSPACE") or file_cfg.get("workspace"),
            opik_project=_env("OPIK_PROJECT_NAME"),
            judge_mode=_env("AOA_JUDGE_MODE", "agent"),
            judge_model=_env("AOA_JUDGE_MODEL", "openai/gpt-5.2"),
            judge_temperature=float(_env("AOA_JUDGE_TEMPERATURE", "0")),
            sampling_rate=float(_env("AOA_SAMPLING_RATE", "1.0")),
            max_cost_usd=float(max_cost) if max_cost.lower() != "none" else None,
            agent_profile_file=_env("AOA_AGENT_PROFILE_FILE"),
            var_input=_env("AOA_VAR_INPUT", "input"),
            var_output=_env("AOA_VAR_OUTPUT", "output"),
            alert_webhook_url=_env("AOA_ALERT_WEBHOOK_URL"),
            alert_webhook_secret=_env("AOA_ALERT_WEBHOOK_SECRET"),
            alert_window_seconds=int(_env("AOA_ALERT_WINDOW_SECONDS", "300")),
            alert_on=_env("AOA_ALERT_ON", "actionable"),
            rule_name=_env("AOA_RULE_NAME", "aoa_ids_incident_detector"),
        )
