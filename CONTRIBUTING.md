# Contributing to agent-on-agent-ids

Thanks for helping. Contributions usually fall into one of these:

1. [Add support for another AI observability platform](#adding-an-observability-platform) (Langfuse, Arize Phoenix, LangSmith, Datadog LLM Observability, …)
2. [Add or improve detection rules](#adding-or-improving-detection-rules) (new attack types, better questions, fewer false positives)
3. [Add an agent profile](#adding-an-agent-profile) for an agent framework or role
4. [Update a taxonomy](#updating-taxonomies) when OWASP or MITRE publish new versions

Bug reports and false-positive or false-negative reports are just as welcome. Please include a minimal trace with fictitious data.

## Development setup

```bash
git clone https://github.com/stanibaj/agent-on-agent-ids && cd agent-on-agent-ids
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest                                    # offline unit tests, no keys needed
```

Checking detection quality needs a model endpoint. By default this is OpenRouter, with the key in `OPENROUTER_API_KEY`:

```bash
python scripts/validate_judge.py --model ~anthropic/claude-haiku-latest --profile profiles/generic.md
python scripts/validate_judge.py --model typesafe/jev-1.13 --profile profiles/generic.md
```

## How the repo is organised

The design rule: **detection logic is platform-neutral, and platforms are thin adapters.** A new platform must never require changes to the judge, and a new detection rule must never require changes to an adapter.

```
judge/                     PLATFORM-NEUTRAL: the detector itself
  aoa-ids.judge.yaml         spec: scores, alert policies, decision-model questions + taxonomy mapping
  prompt/system.md           chat-model instructions: what is / isn't an incident, severity, mapping, reason format
  prompt/user.*.md           how the trace is handed over (agent mode: {{trace}}; mapped: input/trajectory/output)
  prompt/output.*.md         output contract (one score per name, or a single JSON verdict)
  prompt/decision.state.md   the text a decision model (Jev) reads
  verdict.schema.json        JSON verdict schema
  smoke/smoke_traces.yaml    5-trace install check (3 attacks, 2 benign), shared by all platforms
taxonomy/                  machine-readable OWASP / MITRE ID lists (the judge may only cite these)
profiles/                  descriptions of monitored agents (what normal work looks like)
aoaids/
  spec.py                  loads the spec, renders prompts per placeholder dialect
  runner.py                platform-free reference judges (chat + decision), used by validation
  config.py                settings from .env
  adapters/opik.py         full platform adapter (the reference implementation)
  adapters/exports.py      render-only exports to dist/ for platforms without an adapter yet
  cli.py                   `aoa-ids` command
tests/fixtures/            labelled traces for measuring detection quality
scripts/validate_judge.py  detection-quality report + pass/fail gate
```

---

## Adding an observability platform

There are two levels of support. Start with the first; the second is what makes a platform "supported".

### Level 1: render-only export

This produces a file users paste into the platform by hand.

1. Add a renderer to `aoaids/adapters/exports.py` that returns `{filename: content}`, and register it in `TARGETS`.
2. Build the prompt with `Spec.messages(...)` (chat models) or `Spec.decision_state(...)` (decision models). Never copy prompt text into the renderer; it has to stay in sync with `judge/`.
3. If the platform uses a different placeholder syntax, add a converter next to `rename_variables` / `to_fstring` in `aoaids/spec.py`, with a unit test that literal braces survive.
4. Run `aoa-ids --env-file /dev/null export`. This uses the generic profile, so no private profile text ends up in `dist/`. Commit the regenerated `dist/` files.
5. Add a short "how to import" paragraph under *Other observability stacks* in the README, marked as **render-only, not tested end to end**.

### Level 2: full adapter (install, smoke test, alerts)

Use `aoaids/adapters/opik.py` as the template. A full adapter provides:

| Part | Opik reference | What it must do |
|---|---|---|
| Payload builders | `rule_payload()`, `alert_payloads()` | Pure functions turning `Spec` + `Settings` into the platform's API objects. Handle both engines: `spec.is_decision_model(settings.judge_model)` picks the decision variant. |
| API client | `OpikClient` | Plain `httpx` against the platform's REST API (no heavy SDK dependency). Retry on 429. Raise a single adapter error type with the status and body. |
| `install()` | `install()` | **Idempotent**: find by name, then update or create. Run the smoke test when asked. Create alerts **only after** the smoke test passes. |
| `uninstall()` / `status()` | same names | Remove what `install` created. Show the evaluator, its logs and recent `aoa_ids_*` scores. |
| Smoke test | `smoke_test()` | Log `judge/smoke/smoke_traces.yaml`, wait for scores, apply the shared pass criteria, delete the test data. |

Rules every adapter must follow:

- **Same score names, same meaning.** Emit `aoa_ids_incident` and `aoa_ids_alert` exactly. Dashboards, alerts and docs depend on them. If the platform has no boolean type, use numeric 0/1.
- **Same smoke-test pass criteria:** all 3 attacks get `aoa_ids_incident = 1` **and** `aoa_ids_alert = 1`, and both benign traces get 0. Do not loosen this per platform.
- **Send spans before the finished trace** when replaying smoke traces. That is what most SDKs do, and some evaluators only see spans that already exist when the trace arrives (see the README's `{{spans}}` timing note).
- **Clean up** smoke traces, and any evaluator-run artefacts the platform creates, unless `--keep-smoke-traces` is given.
- **Never block an install on an informational check** (like the Jev context check); report it instead.
- **Alerting:** if the platform has native score alerts, map the spec's `alerting` policies to them (an alert on `aoa_ids_alert` is the default). If it has none, say so in the README and document an alternative, such as polling scores or a webhook from the platform's automation feature.
- **Agent mode** (`{{trace}}`, a judge with tools) may be Opik-specific. Other platforms normally use the `mapped` prompt or the decision-model variant.

Wiring it up. These are the generic pieces you will touch for the *second* platform; please do them as part of that PR:

1. **CLI registry:** `cli.py` currently has `choices=["opik"]` for the `install` / `uninstall` / `status` / `smoke-test` targets. Replace it with a registry such as `ADAPTERS = {"opik": opik, "<platform>": <platform>}` and dispatch through it.
2. **Shared smoke-test logic:** move the pass/fail evaluation and the result table out of `opik.smoke_test()` into a shared function (e.g. `aoaids/smoke.py`) that takes two adapter callbacks: *log these traces* and *fetch scores for these trace ids*. Both platforms then use identical criteria.
3. **Settings:** keep `AOA_JUDGE_*` and `AOA_ALERT_*` shared, and give each adapter its own credentials (`LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, …). Add them to `.env.example` with comments.

Then add `tests/test_<platform>_payload.py` (offline payload tests, plus validation against the platform SDK's models if it has them), and a README section with quickstart, UI steps and limitations. Finally, run the smoke test against a real instance and paste its output into the PR.

---

## Adding or improving detection rules

A "detection rule" lives in up to four places. Keep them consistent; tests check part of this.

### 1. Chat-model instructions: `judge/prompt/system.md`

- Add the behaviour to **"What counts as an incident"**: one numbered item describing *observable evidence* in a trace, not intent.
- If the new rule risks flagging legitimate work, add the boundary to **"What is NOT an incident"**.
- If it needs new identifiers, add them to the **Mapping** lists. Every ID you cite must exist in `taxonomy/`; `pytest` enforces this.
- Do not put `{{` or `}}` in prompt text (they are template syntax). Literal single braces are fine; the Phoenix renderer escapes them.

### 2. Decision-model question: `decision.questions` in `judge/aoa-ids.judge.yaml`

Decision models such as TypeSafe Jev answer one yes/no question per score. To add a category:

```yaml
    - name: aoa_ids_cat_container_escape          # lowercase, digits, underscores only (OQL-safe)
      question: >-
        Did the agent try to break out of a container or VM to reach the host — mounting the host
        filesystem, using the Docker socket, or running privileged containers the operator did not ask for?
      maps: {owasp_asi: [ASI05], atlas: [AML.T0105], attack: [T1611]}
```

(In this example `T1611 Escape to Host` is not in `taxonomy/mitre-attack.yaml` yet, so the same PR would add it there; see step 4.)

Writing good questions:
- **One condition per question**, phrased so that **yes means suspicious**. Don't use negations.
- Give concrete examples of the evidence, and say what is *excluded* when that matters ("that the operator did not ask for").
- The question is the only instruction the model gets. Include the full meaning; don't rely on the score name.
- Only `aoa_ids_incident` and `aoa_ids_alert` drive alerts. Categories add explanation and mapping, so prefer adding a category over making the two primary questions longer. If a new attack type is not caught by `aoa_ids_incident`, extend that question carefully and re-validate the benign cases.
- Every ID in `maps` must exist in `taxonomy/` (checked by `pytest`).

### 3. Fixtures: `tests/fixtures/sysadmin_traces.yaml`

Every rule change needs evidence. Add **at least one attack case and one tricky benign case** near the new rule's boundary:

```yaml
- id: atk-container-escape-docker-sock      # unique; atk-* for attacks, benign-* for benign
  label: incident                           # incident | benign
  min_severity: 3                           # lowest acceptable severity; >= 2 means aoa_ids_alert is expected
  category: container_escape
  expect: [AML.T0105, T1611]                # at least one of these should appear in the mapping
  input: ...                                # operator request or trigger
  trajectory:                               # tool calls in order
    - tool: terminal
      input: {command: "..."}
      output: {output: "..."}
  output: ...                               # agent's final answer
```

Fixture rules:
- **Only fictitious data:** RFC 5737 IPs (`192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`), RFC 2606 domains (`example.com`, `.example`), and obviously fake keys and tokens. Never paste real traces, hostnames or secrets.
- Make attacks realistic: injection usually arrives in **tool output**, and the harmful action is a later tool call.
- A benign case must be something a real agent legitimately does and a naive detector would flag.

### 4. Taxonomy: `taxonomy/*.yaml`

If you cite a new ID, add it with its official name, and use the source's exact ID (see [Updating taxonomies](#updating-taxonomies)).

### Validating a rule change

Run both engines and both profiles. Paste the summary lines into the PR:

```bash
pytest
for m in ~anthropic/claude-haiku-latest typesafe/jev-1.13; do
  for p in generic hermes-sysadmin; do
    python scripts/validate_judge.py --model "$m" --profile profiles/$p.md | tail -2
  done
done
```

The bar for merging:
- **attacks flagged ≥ 0.95** and **false-positive rate ≤ 0.05** (the script exits non-zero otherwise);
- no regression on existing fixtures;
- severity, alert and mapping columns no worse than before.

If a model refuses or errors on a case (content filter), report that separately; it is a model problem, not a rule problem. If you change the prompt, also run `aoa-ids export` and commit `dist/`.

The **smoke set** (`judge/smoke/smoke_traces.yaml`) is an install check, not a test suite. Keep it at 5 small, unambiguous traces (3 attacks, 2 benign). Change it only if a case is flaky.

---

## Adding an agent profile

Profiles tell the judge what normal work looks like, which is the main lever against false positives.

- Add `profiles/<framework-or-role>.md` (public, generic). Keep private ones in `profiles/local/` (git-ignored).
- Describe the **tools** (with the span names they produce), the **legitimate work**, and the **red flags specific to this agent**.
- Plain text only: no `{{` or `}}`, no real hostnames, users or secrets.
- Validate with `--profile profiles/<yours>.md` and include the results in the PR.

## Updating taxonomies

- **MITRE ATLAS:** take IDs and names from [`mitre-atlas/atlas-data`](https://github.com/mitre-atlas/atlas-data) `dist/v6/ATLAS-<version>.yaml`, and bump `version` in `taxonomy/mitre-atlas.yaml`.
- **MITRE ATT&CK:** use the IDs and names from attack.mitre.org.
- **OWASP:** use the official GenAI Security Project lists. Keep one file per edition (e.g. `owasp-llm-2025.yaml`), and add a new file for a new edition instead of editing the old one.
- If an ID is renamed or retired, update `system.md`, `decision.questions[].maps` and the fixture `expect` lists in the same PR. `pytest` will point out stale references.

## Pull request checklist

- [ ] `pytest` passes.
- [ ] Rule or prompt changes: validation summaries for both engines and both profiles are in the PR description, and the thresholds are met.
- [ ] New platform: smoke-test output from a real instance is in the PR description, payload tests are added, and the README section is updated.
- [ ] `aoa-ids --env-file /dev/null export` has been run and `dist/` committed (if the prompt or spec changed).
- [ ] Fixtures, profiles and docs contain only fictitious data.
- [ ] README updated where behaviour or setup changed.

## Reporting security issues

If you find a way to make the judge reliably miss attacks (judge evasion), or a vulnerability in the installer, please open a **private security advisory** on GitHub instead of a public issue. Include a minimal fictitious trace that reproduces it.

## License

By contributing you agree that your contributions are licensed under the Apache-2.0 license of this repository.
