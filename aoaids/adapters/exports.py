"""Render the spec into ready-to-import files for other observability stacks (written to dist/)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from ..config import Settings
from ..spec import Spec, to_fstring
from . import opik

DIST_DIR = Path(__file__).resolve().parents[2] / "dist"
PROJECT_PLACEHOLDER = "<YOUR_OPIK_PROJECT_ID>"


def _opik_rules(spec: Spec, settings: Settings) -> dict[str, str]:
    out = {}
    for mode in ("agent", "mapped"):
        payload = opik.rule_payload(spec, replace(settings, judge_mode=mode), PROJECT_PLACEHOLDER)
        out[f"opik-rule.{mode}.json"] = json.dumps(payload, indent=2) + "\n"
    return out


def _langfuse(spec: Spec, settings: Settings) -> dict[str, str]:
    # Langfuse custom evaluators: mustache prompt, one numeric score + reasoning per evaluator.
    system, user = spec.messages(mode="mapped", output="json", profile_file=settings.agent_profile_file)
    incident = next(s for s in spec.scores if s.get("primary"))
    evaluator = {
        "name": incident["name"],
        "version": spec.version,
        "prompt": f"{system.content}\n\n{user.content}",
        "variables": spec.variables("mapped"),
        "variable_mapping_hint": {
            "input": "Trace > Input",
            "output": "Trace > Output",
            "trajectory": "Trace > Observations (all tool/generation observations, JSON)",
        },
        "output": {
            "score": "1 if the verdict's `incident` is true, else 0",
            "reasoning": "the verdict's `reason` line (OWASP/ATLAS/ATT&CK mapping + evidence)",
        },
        "recommended_model": settings.judge_model,
    }
    return {"langfuse-evaluator.json": json.dumps(evaluator, indent=2) + "\n"}


def _phoenix(spec: Spec, settings: Settings) -> dict[str, str]:
    system, user = spec.messages(mode="mapped", output="json", profile_file=settings.agent_profile_file)
    return {
        "phoenix-template.txt": to_fstring(f"{system.content}\n\n{user.content}") + "\n",
    }


def _openai(spec: Spec, settings: Settings) -> dict[str, str]:
    schema = json.loads((spec.root / spec.data["verdict_schema"]).read_text())
    messages = spec.messages(mode="mapped", output="json", profile_file=settings.agent_profile_file)
    body = {
        "model": settings.judge_model,
        "temperature": 0,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "response_format": {"type": "json_schema", "json_schema": {"name": "aoa_ids_verdict", "strict": True, "schema": schema}},
        "_template_variables": spec.variables("mapped"),
    }
    return {"openai-chat-request.json": json.dumps(body, indent=2) + "\n"}


TARGETS = {"opik": _opik_rules, "langfuse": _langfuse, "phoenix": _phoenix, "openai": _openai}


def export(spec: Spec, settings: Settings, targets: list[str], out_dir: Path = DIST_DIR) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for target in targets:
        for filename, content in TARGETS[target](spec, settings).items():
            path = out_dir / filename
            path.write_text(content)
            written.append(path)
    return written
