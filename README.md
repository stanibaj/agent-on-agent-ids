# agent-on-agent-ids

<p align="center">
  <img src="docs/assets/aoa-ids-demo.gif" alt="A poisoned log line makes an AI sysadmin agent append an SSH key; the AOA-IDS judge flags it as an indirect prompt injection (OWASP LLM01, ASI01, MITRE ATLAS AML.T0051.001, ATT&CK T1098.004), Comet Opik fires an alert, and the installer's smoke test passes." width="100%">
  <br>
  <sub>▶ <a href="https://cdn.jsdelivr.net/gh/stanibaj/agent-on-agent-ids@052b04cb661d6785317e119ce51a89857716940e/docs/assets/aoa-ids-demo.mp4">Watch in full quality with voice-over (MP4, 1080p · 60 fps · 39 s)</a></sub>
</p>

**Know within minutes when one of your AI agents gets hijacked.**

agent-on-agent-ids (AOA-IDS) is intrusion detection for AI agents that use tools. A second AI agent reads the traces your agents already send to your AI observability tool, flags prompt injection and the attacks it leads to, and alerts you when an agent acts on one.

The judge is a portable spec built to run in any AI observability tool. Comet Opik is supported today with a one-command installer. Native support for other observability tools is in the pipeline, as are integrations that forward findings to SIEM and log management tools.

<p align="center">
  <img src="docs/assets/aoa-ids-architecture.png" alt="Where AOA-IDS sits: untrusted text (logs, web pages, tickets, PR comments) reaches your AI agents inside the agent runtime, where AOA-IDS adds nothing. The agents send traces to your AI observability tool (Comet Opik available; Langfuse and Arize Phoenix in the pipeline). The AOA-IDS judge agent reads every trace, links injected text to the action it caused, writes verdicts back, and sends alerts to PagerDuty, Slack, Telegram or a webhook; SIEM and log management (Splunk, Microsoft Sentinel, Elastic, Datadog) are in the pipeline." width="100%">
</p>

## Why you need it

Agents with tools read untrusted text all day: logs, web pages, tickets, PR comments. An instruction hidden in that text can make your agent run a command for an attacker, with your agent's permissions. The video above shows one such attack: a single line in a log file gets a sysadmin agent to add an attacker's SSH key to root.

The tools you already run won't flag it:

| Layer | What it sees |
|---|---|
| Prompt guardrail | The task the agent was given, "summarize the web-01 logs". Harmless. |
| EDR / SIEM | The agent's own trusted account appending to `authorized_keys`. A routine admin command. |
| Observability (Opik, Langfuse, Phoenix) | The whole attack, recorded in a trace that nobody reads until the postmortem. |

The trace is the one place where the injected instruction and the command it caused appear together. AOA-IDS reads every trace and connects the two.

## What you get

- **An alert when an agent acts on an attack.** It goes to PagerDuty, Slack, Telegram or any webhook. The `aoa_ids_alert` score fires only when the agent did something harmful. Attempts the agent ignored are still recorded as incidents, but they don't wake anyone up.
- **Findings your security team can triage.** Each verdict names the OWASP LLM Top 10, OWASP Agentic Top 10, MITRE ATLAS and ATT&CK techniques, and quotes the evidence from the trace.
- **Nothing added to your agent.** It runs as an online-evaluation rule on the traces you already collect, so the agent needs no code change and gets no extra latency.
- **A warning when it stops watching.** `aoa-ids coverage` reports which traces the judge never scored and why, and can notify you when coverage drops.
- **Small, cheap judges, on the model you choose.** Claude Haiku and TypeSafe Jev each caught 20 of 20 attacks in the bundled test traces, with 0 false alarms on 10 hard benign cases. The Jev run cost $0.002. You can also run the judge on your own provider account or a self-hosted model.

## Install on Comet Opik

You need an Opik project that already receives your agent's traces, and an AI provider in Opik for the judge model (OpenRouter serves the defaults).

```bash
git clone https://github.com/stanibaj/agent-on-agent-ids && cd agent-on-agent-ids
python -m venv .venv && . .venv/bin/activate && pip install -e .
cp .env.example .env   # OPIK_API_KEY, OPIK_WORKSPACE, OPIK_PROJECT_NAME, and an alert destination (PagerDuty, Slack, …)
aoa-ids install opik --smoke-test
```

This creates the judge rule and the alert. `--smoke-test` then logs 5 test traces to your project (3 attacks, 2 benign), checks every verdict and deletes the traces:

```
smoke test PASSED: detected 3/3 attacks, 2/2 benign traces clean.
```

## Works with

| Platform | Support |
|---|---|
| Comet Opik | One-command installer, smoke test, alerts and coverage check |
| Langfuse, Arize Phoenix | In the pipeline. Ready-to-paste judge exports today (not yet tested end to end) |
| SIEM and log management | In the pipeline: forwarding findings with their OWASP and MITRE mappings |
| Your own pipeline | OpenAI-compatible request, OpenRouter Decisions API request, Python runner |

## Documentation

- [Comet Opik guide](docs/opik.md): install options, smoke test, setup in the Opik UI, alerting, coverage
- [Judge models](docs/models.md): choosing a model, validation results, bring your own model, agent and mapped modes
- [Detection](docs/detection.md): what it flags, verdict format, agent profiles, taxonomies, limitations
- [Other platforms](docs/other-platforms.md): Langfuse, Phoenix, Decisions API, Python
- [Contributing](CONTRIBUTING.md): add a platform or a detection rule

## Limitations

AOA-IDS detects an attack after the run; it does not block it. The judge is an LLM reading attacker-controlled text, so run it alongside guardrails, least privilege and approval gates. Details in [docs/detection.md](docs/detection.md#limitations).

## License

Apache-2.0
