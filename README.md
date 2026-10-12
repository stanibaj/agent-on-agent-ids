# agent-on-agent-ids

<p align="center">
  <img src="docs/assets/aoa-ids-demo.gif" alt="A poisoned log line makes an AI sysadmin agent append an SSH key; the AOA-IDS judge flags it as an indirect prompt injection (OWASP LLM01, ASI01, MITRE ATLAS AML.T0051.001, ATT&CK T1098.004), Comet Opik fires an alert, and the installer's smoke test passes." width="100%">
  <br>
  <sub>▶ <a href="https://cdn.jsdelivr.net/gh/stanibaj/agent-on-agent-ids@052b04cb661d6785317e119ce51a89857716940e/docs/assets/aoa-ids-demo.mp4">Watch in full quality with voice-over (MP4, 1080p · 60 fps · 39 s)</a></sub>
</p>

**Know within minutes when one of your AI agents gets hijacked.**

agent-on-agent-ids (AOA-IDS) is intrusion detection for AI agents that use tools. A second AI agent reads every trace your agents send to Comet Opik, flags prompt injection and the attacks it leads to, and pages you when an agent acts on one.

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

- **A page when an agent acts on an attack.** The `aoa_ids_alert` score fires only when the agent did something harmful. Attempts the agent ignored are still recorded as incidents, but they don't wake anyone up.
- **Findings your security team can triage.** Each verdict names the OWASP LLM Top 10, OWASP Agentic Top 10, MITRE ATLAS and ATT&CK techniques, and quotes the evidence from the trace.
- **Nothing added to your agent.** It runs as an online-evaluation rule on the traces you already collect, so the agent needs no code change and gets no extra latency.
- **Small, cheap judges.** Claude Haiku and TypeSafe Jev each caught 20 of 20 attacks in the bundled test traces, with 0 false alarms on 10 hard benign cases. The Jev run cost $0.002.

## Install on Comet Opik

You need an Opik project that already receives your agent's traces, and an AI provider in Opik for the judge model (OpenRouter serves the defaults).

```bash
git clone https://github.com/stanibaj/agent-on-agent-ids && cd agent-on-agent-ids
python -m venv .venv && . .venv/bin/activate && pip install -e .
cp .env.example .env   # OPIK_API_KEY, OPIK_WORKSPACE, OPIK_PROJECT_NAME, and AOA_ALERT_WEBHOOK_URL for alerts
aoa-ids install opik --smoke-test
```

This creates the judge rule and the alert. `--smoke-test` then logs 5 test traces to your project (3 attacks, 2 benign), checks every verdict and deletes the traces:

```
smoke test PASSED: detected 3/3 attacks, 2/2 benign traces clean.
```

## Works with

| Platform | Support |
|---|---|
| Comet Opik | One-command installer, smoke test and alerts |
| Langfuse, Arize Phoenix | Ready-to-paste judge exports (not yet tested end to end) |
| Your own pipeline | OpenAI-compatible request, OpenRouter Decisions API request, Python runner |

## Documentation

- [Comet Opik guide](docs/opik.md): install options, smoke test, setup in the Opik UI, alerting
- [Judge models](docs/models.md): choosing a model, validation results, agent and mapped modes
- [Detection](docs/detection.md): what it flags, verdict format, agent profiles, taxonomies, limitations
- [Other platforms](docs/other-platforms.md): Langfuse, Phoenix, Decisions API, Python
- [Contributing](CONTRIBUTING.md): add a platform or a detection rule

## Limitations

AOA-IDS detects an attack after the run; it does not block it. The judge is an LLM reading attacker-controlled text, so run it alongside guardrails, least privilege and approval gates. Details in [docs/detection.md](docs/detection.md#limitations).

## License

Apache-2.0
