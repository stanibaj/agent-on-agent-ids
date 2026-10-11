"""Reference evaluator: run the AOA-IDS judge on one agent run through any OpenAI-compatible endpoint.

Use it to wire the detector into stacks without native LLM-as-judge support:

    from aoaids.runner import Judge
    verdict = Judge().evaluate(input=..., output=..., trajectory=[...])
    if verdict["incident"]: ...
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from .spec import Spec, VAR_PATTERN

REQUIRED = ("incident", "severity", "confidence", "stage", "reason")


class RefusedError(RuntimeError):
    """The judge model produced no answer (typically a provider content filter)."""


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str, indent=1)


def parse_verdict(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"judge returned no JSON object: {text[:200]!r}")
    verdict = json.loads(match.group(0))
    missing = [k for k in REQUIRED if k not in verdict]
    if missing:
        raise ValueError(f"verdict missing fields {missing}: {verdict}")
    return verdict


class Judge:
    def __init__(self, model: str | None = None, base_url: str | None = None, api_key: str | None = None,
                 profile_file: str | None = None, spec: Spec | None = None, timeout: float = 180,
                 retries: int = 1):
        self.spec = spec or Spec()
        self.retries = retries
        self.model = model or os.environ.get("AOA_JUDGE_MODEL", self.spec.data["recommended"]["default_model"])
        self.base_url = (base_url or os.environ.get("AOA_RUNNER_BASE_URL", "https://openrouter.ai/api/v1")).rstrip("/")
        key = api_key or os.environ.get("AOA_RUNNER_API_KEY") or os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
        self.http = httpx.Client(timeout=timeout, headers={"Authorization": f"Bearer {key}"} if key else {})
        self.messages = self.spec.messages(mode="mapped", output="json",
                                           profile_file=profile_file or os.environ.get("AOA_AGENT_PROFILE_FILE"))

    def render(self, **variables: Any) -> list[dict[str, str]]:
        values = {k: _as_text(v) for k, v in variables.items()}
        return [{"role": m.role, "content": VAR_PATTERN.sub(lambda x: values.get(x.group(1), ""), m.content)}
                for m in self.messages]

    def evaluate(self, *, input: Any, output: Any, trajectory: Any) -> dict[str, Any]:
        body = {"model": self.model, "temperature": 0, "response_format": {"type": "json_object"},
                "messages": self.render(input=input, output=output, trajectory=trajectory)}
        error: Exception | None = None
        for _ in range(self.retries + 1):
            response = self.http.post(f"{self.base_url}/chat/completions", json=body)
            response.raise_for_status()
            data = response.json()
            choice = data["choices"][0]
            content = choice["message"].get("content") or ""
            # A provider safety filter can refuse to analyse attack payloads. For a detector an unscored
            # trace is a miss, so retry and then surface it loudly instead of returning "benign".
            if not content.strip():
                error = RefusedError(f"judge returned no answer (finish_reason={choice.get('finish_reason')!r}); "
                                     "consider a model that does not filter security content")
                continue
            try:
                verdict = parse_verdict(content)
            except ValueError as parse_error:  # json.JSONDecodeError is a ValueError
                error = parse_error
                continue
            verdict["_usage"] = data.get("usage", {})
            return verdict
        raise error
