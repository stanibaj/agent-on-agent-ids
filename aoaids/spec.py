"""Load the portable judge spec and render its prompt for a target template dialect."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

JUDGE_DIR = Path(__file__).resolve().parent.parent / "judge"
VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


@dataclass(frozen=True)
class Message:
    role: str  # "system" | "user"
    content: str


class Spec:
    def __init__(self, path: Path = JUDGE_DIR / "aoa-ids.judge.yaml"):
        self.path = Path(path)
        self.root = self.path.parent
        self.data = yaml.safe_load(self.path.read_text())

    @property
    def name(self) -> str:
        return self.data["name"]

    @property
    def version(self) -> str:
        return self.data["version"]

    @property
    def scores(self) -> list[dict]:
        return self.data["scores"]

    @property
    def alerting(self) -> list[dict]:
        return self.data["alerting"]

    def _read(self, rel: str) -> str:
        return (self.root / rel).read_text().strip()

    def profile_text(self, profile_file: str | None = None) -> str:
        if profile_file:
            text = Path(profile_file).read_text().strip()
        else:
            text = self._read(self.data["variables"]["agent_profile"]["default"])
        if "{{" in text or "}}" in text:
            raise ValueError("agent profile must not contain '{{' or '}}' (template syntax)")
        return text

    def variables(self, mode: str) -> list[str]:
        return list(self.data["prompt"]["modes"][mode]["variables"])

    def messages(self, mode: str = "agent", output: str = "scores", profile_file: str | None = None) -> list[Message]:
        """Canonical messages: mustache `{{var}}` placeholders, agent profile already inlined."""
        prompt = self.data["prompt"]
        system = self._read(prompt["system"]).replace("{{agent_profile}}", self.profile_text(profile_file))
        system = f"{system}\n\n{self._read(prompt['output'][output])}"
        user = self._read(prompt["modes"][mode]["user"])
        return [Message("system", system), Message("user", user)]


def rename_variables(text: str, mapping: dict[str, str]) -> str:
    """Rename mustache placeholders, e.g. {"trajectory": "spans"} for Opik's built-in."""
    return VAR_PATTERN.sub(lambda m: "{{" + mapping.get(m.group(1), m.group(1)) + "}}", text)


def to_fstring(text: str) -> str:
    """Mustache -> Python str.format style (Phoenix): escape literal braces, then convert placeholders."""
    names: list[str] = []

    def stash(m: re.Match) -> str:
        names.append(m.group(1))
        return f"\x00{len(names) - 1}\x00"

    stashed = VAR_PATTERN.sub(stash, text)
    escaped = stashed.replace("{", "{{").replace("}", "}}")
    return re.sub(r"\x00(\d+)\x00", lambda m: "{" + names[int(m.group(1))] + "}", escaped)


def placeholders(text: str) -> set[str]:
    return set(VAR_PATTERN.findall(text))
