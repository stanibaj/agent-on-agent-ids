---
workflow: general-video
flow: automation
storyboard: no
message: "Your AI agent can be hijacked by one line of text — agent-on-agent-ids is another agent that catches it, maps it to OWASP/MITRE and fires the alert."
destination: github-readme-gif
aspect: "16:9"
language: en
audience: platform / security engineers running AI agents with tools
length: "~30s, silent, loops"
---

## Intent

Promote the GitHub repo stanibaj/agent-on-agent-ids as the animated GIF at the top of its README.
Chosen telling (internal pitch round, autonomous run): **attack → detection → alert → proof → install**.
Show a real indirect prompt injection hijacking a sysadmin agent (a poisoned log line makes it add an SSH key),
then the AOA-IDS judge catching it with the exact verdict format the repo produces, the Opik alert firing,
measured results, and the one-command install with its smoke test. Typical direction left behind: abstract
"radar over traces" sizzle (pretty, proves nothing).

## Customizations

- Silent (GIF). No narration, no music. Every beat must read without sound.
- All claims come from the repo's real outputs (smoke test, validation runs, verdict reason format).

## Notes

- Output: render MP4 1920x1080, convert to GIF ~960px wide for the README; keep the GIF small (< ~8 MB).
- Type must survive downscaling to ~880px README width: mono ≥ 34px, statements ≥ 88px at 1920.
