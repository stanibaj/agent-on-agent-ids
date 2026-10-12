# Judge models and modes

## Choosing a judge model

`AOA_JUDGE_MODEL` selects the engine automatically:

| Engine | Models | How it judges | Output |
|---|---|---|---|
| **Small fast chat model** (default) | `~anthropic/claude-haiku-latest` (default), `~google/gemini-flash-latest`, `~openai/gpt-mini-latest`, `~openai/gpt-luna-latest`, `~z-ai/glm-flash-latest`, `~deepseek/deepseek-flash-latest`, or any chat model | Agent as a Judge: reads the trace and its spans with tools, so it works on traces of **any size** | incident, alert, severity, confidence, plus a mapping line with quoted evidence |
| **Decision model** | `typesafe/jev-1.13` (pinned), `~typesafe/jev-latest` | One call: the trace (input, all spans, output) is the text, and 14 yes/no questions are asked in parallel. Each becomes a BOOLEAN score with a calibrated probability. | incident, alert, plus 12 `aoa_ids_cat_*` categories, each mapped to fixed OWASP/ATLAS/ATT&CK IDs |

Validated on the bundled 30 fixtures (20 attacks, 10 hard benign cases) through OpenRouter, October 2026:

| Model | Attacks flagged | False positives | Alert / severity correct | Mapping hit | Cost for 30 traces |
|---|---|---|---|---|---|
| `typesafe/jev-1.13` | 100% | 0% | 100% | 100% | **$0.002** |
| `~anthropic/claude-haiku-latest` (→ Haiku 5.5) | 100% | 0% | 100% | 100% | $0.03 |
| `~z-ai/glm-flash-latest` | 100% | 0% | 100% | 100% | $0.03 |
| `~openai/gpt-luna-latest` | 100% | 0% | 95% | 100% | $0.01 |
| `~openai/gpt-mini-latest` | 100% | 0% | 100% | 100% | $0.07 |
| `~google/gemini-flash-latest` | 100% | 0% | 100% | 100% | $0.18 |
| `~deepseek/deepseek-flash-latest` | 100% (29 scored, 1 provider 503) | 0% | 100% | 100% | $0.02 |

Both engines also pass the Opik smoke test end to end. The fixtures are synthetic and small, so treat this as a working check, not a benchmark.

**Jev's 32k-token context.** In Opik, Jev receives the trace's full span tree. Agents whose LLM spans repeat the whole conversation grow fast: on a Hermes Agent homelab, 9 of the 10 most recent traces fit, but a long tool-heavy session reached about 114k tokens. **Opik skips oversized traces and does not score them.** When you install with a decision model, the installer measures your recent traces and prints this coverage. Use Jev where traces are compact (or as the cheapest tripwire), and a small fast chat model where every trace must be covered.

**Refusals.** The judge has to analyse attack payloads. Larger models such as `claude-sonnet-5.5` and `claude-opus-5.5` sometimes hit provider content filters on explicit payloads (reverse shells, `/etc/shadow` exfiltration), which leaves the trace unscored: a silent miss. None of the models above refused. Validate any other model first:

```bash
python scripts/validate_judge.py --model <model> --profile profiles/generic.md
```

**Opik gotcha:** Opik only runs OpenRouter models on its own allow-list (the `~…-latest` aliases and Jev are on it). A rule with any other model name is **accepted by the API but never runs, and logs nothing**. The smoke test catches this. `-latest` aliases follow new releases automatically; pin a concrete model if you need verdicts that don't change underneath you.

## Modes (chat models)

| `AOA_JUDGE_MODE` | How the judge sees the trace | Use when |
|---|---|---|
| `agent` (default) | `{{trace}}`: Opik's *Agent as a Judge*. The judge reads spans on demand with `read` / `jq` / `search` / `get_trace_spans` tools, and works on any trace shape. | Always, unless the model lacks tool calling |
| `mapped` | One call with `{{input}}`, `{{output}}` and `{{spans}}` (all spans as JSON) | Models without tool calling, or other platforms |

Decision models always use the mapped shape.

**`{{spans}}` timing on Opik:** a trace rule is evaluated when the trace record arrives. In testing, spans that reached Opik *after* their trace were missing from `{{spans}}`, so the judge saw no tool calls. That affects mapped mode and decision models. Agent mode reads spans when the evaluation runs and was not affected. Most SDKs (including Hermes Agent's tracing) send spans first, and the smoke test does the same.
