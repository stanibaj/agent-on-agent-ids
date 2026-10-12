# Other observability stacks

Everything platform-neutral lives in [`judge/`](../judge):

| File | Purpose |
|---|---|
| [`aoa-ids.judge.yaml`](../judge/aoa-ids.judge.yaml) | The spec: variables, modes, scores, reason format, taxonomies, alert policies |
| [`prompt/`](../judge/prompt) | System prompt, user templates for agent and mapped modes, and output instructions (per-score or single JSON) |
| [`verdict.schema.json`](../judge/verdict.schema.json) | JSON Schema of the single-object verdict, for structured-output pipelines |
| [`prompt/decision.state.md`](../judge/prompt/decision.state.md) + `decision:` in the spec | Decision-model variant: data-only state plus yes/no questions with taxonomy mapping |
| [`smoke/smoke_traces.yaml`](../judge/smoke/smoke_traces.yaml) | The 5-trace smoke set (3 attacks, 2 benign); replay it into any stack to check an install |

`aoa-ids export` renders these into [`dist/`](../dist):

- **Langfuse**: [`dist/langfuse-evaluator.json`](../dist/langfuse-evaluator.json). Create a custom LLM-as-a-judge evaluator, paste `prompt`, and map `{{input}}` → trace input, `{{output}}` → trace output, `{{trajectory}}` → the trace's observations. Store `incident` as the score (1/0) and `reason` as the reasoning. Alert with your Langfuse score monitors.
- **Arize Phoenix**: [`dist/phoenix-template.txt`](../dist/phoenix-template.txt). The same prompt in Phoenix's `{variable}` syntax, with literal braces escaped. Fill `input`, `output` and `trajectory` from the root span and its child spans, run it with your Phoenix evals model, parse the JSON verdict, and log `incident`, `alert` and `severity` as span annotations.
- **Decision models anywhere**: [`dist/decision-request.json`](../dist/decision-request.json) is a ready OpenRouter Decisions API body (`POST https://openrouter.ai/api/alpha/decisions`) with the state template, the 14 questions, and the taxonomy behind each category question. `aoaids.runner.DecisionJudge` runs it for you.
- **Anything else**: [`dist/openai-chat-request.json`](../dist/openai-chat-request.json) (messages plus a strict JSON schema), or call the reference runners directly:

```python
from aoaids.runner import DecisionJudge, Judge   # OpenRouter by default (OPENROUTER_API_KEY)

judge = Judge(model="~anthropic/claude-haiku-latest", profile_file="profiles/generic.md")  # chat engine
# judge = DecisionJudge(model="typesafe/jev-1.13", profile_file="profiles/generic.md")    # decision engine
verdict = judge.evaluate(input=user_request, output=final_answer, trajectory=tool_calls)
if verdict["alert"]:
    page_someone(verdict["reason"], verdict["atlas"], verdict["attack"])
```

Status: the Opik installer and smoke test are tested against Opik Cloud with both engines, and both runners are tested through OpenRouter. The Langfuse and Phoenix exports are rendered and syntax-checked, but have **not yet been tested end to end on those platforms**. Contributions of native installers are welcome.
