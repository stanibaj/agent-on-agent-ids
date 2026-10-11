---
name: aoa-ids-readme
colors:
  bg: "#0A0F0D"
  panel: "#111A16"
  panel-2: "#16211C"
  hairline: "#26362F"
  fg: "#E7EEE9"
  muted: "#93A79D"
  accent: "#FFB21E"      # the watching agent: detection, verdicts, CTA
  danger: "#FF5B47"      # attack payload / harmful action (semantic state only)
  ok: "#71D6A0"          # passed / benign (semantic state only)
fonts:
  display: "Archivo Black"   # 400 only — human verdict voice
  mono: "JetBrains Mono"     # 400 / 700 — machine voice: traces, data, commands
radius: 14px
---

Concept: two registers in conflict — the machine's trace (mono, dense, scrolling) and the watcher's verdict
(heavy display type, amber, decisive). Amber belongs to the watching agent only; red marks the attacker's text
and the harmful action; green only for "clean"/"passed". Dark ink background tinted green, never pure black.
Layouts anchor left/top with a right-hand verdict column; no centered floating stacks except the final lockup.
Background: faint trace-grid, slow amber radial glow behind the active panel, oversized ghost words.
