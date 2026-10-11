import re
import string
from pathlib import Path

import yaml

from aoaids.spec import Spec, placeholders, rename_variables, to_fstring

ROOT = Path(__file__).resolve().parent.parent


def test_modes_expose_only_their_variables():
    spec = Spec()
    for mode in ("agent", "mapped"):
        for output in ("scores", "json"):
            text = "\n".join(m.content for m in spec.messages(mode=mode, output=output))
            assert placeholders(text) == set(spec.variables(mode)), (mode, output)


def test_profile_is_inlined():
    system = Spec().messages(profile_file=str(ROOT / "profiles/hermes-sysadmin.md"))[0].content
    assert "{{agent_profile}}" not in system and "Hermes Agent" in system


def test_rename_variables_for_opik_spans():
    assert rename_variables("a {{trajectory}} b {{ input }}", {"trajectory": "spans"}) == "a {{spans}} b {{input}}"


def test_fstring_dialect_escapes_literal_braces():
    text = '{"score": true} {{input}}'
    rendered = to_fstring(text)
    fields = {f for _, f, _, _ in string.Formatter().parse(rendered) if f}
    assert fields == {"input"}
    assert rendered.format(input="X") == '{"score": true} X'


def test_prompt_mapping_ids_exist_in_taxonomies():
    known = set()
    for path in (ROOT / "taxonomy").glob("*.yaml"):
        known |= {item["id"] for item in yaml.safe_load(path.read_text())["items"]}
    system = (ROOT / "judge/prompt/system.md").read_text()
    cited = set(re.findall(r"\b(?:LLM\d{2}|ASI\d{2}|AML\.T\d{4}(?:\.\d{3})?|T\d{4}(?:\.\d{3})?)\b", system))
    assert cited and cited <= known, cited - known


def test_score_names_are_oql_safe():
    for score in Spec().scores:
        assert re.fullmatch(r"[a-z0-9_]+", score["name"])


def test_fixtures_are_well_formed():
    cases = yaml.safe_load((ROOT / "tests/fixtures/sysadmin_traces.yaml").read_text())
    assert len({c["id"] for c in cases}) == len(cases)
    for case in cases:
        assert case["label"] in ("incident", "benign")
        assert {"input", "output", "trajectory"} <= case.keys()
