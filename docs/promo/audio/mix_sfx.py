"""Place the ElevenLabs sound effects on the promo's timeline and mix them into one 48 kHz stereo stem.

Event times are the composition's own: scene start (index.html data-start) + the tween's local time.
Pure standard library (wave/array) so it runs anywhere; ffmpeg is used only to make pitch variants.

    python3 mix_sfx.py <sfx_dir> <out.wav>
"""

import array
import math
import os
import subprocess
import sys
import wave

SR = 48000
DURATION = 39.0
BLIND = 8.0  # length of the 'who noticed' scene inserted at 10.5s; every later scene starts this much later
SFX_DIR, OUT = sys.argv[1], sys.argv[2]

# Sounds whose main transient sits late in the file: trigger them early so the hit lands on the frame.
LEAD = {"key_click": 0.23, "enter_key": 0.23, "logo_impact": 0.5, "riser2": 1.45}

_cache: dict[tuple[str, float], array.array] = {}


def load(name: str, rate: float = 1.0) -> array.array:
    """Load a sound as interleaved float stereo; rate != 1 makes a pitch/speed variant via ffmpeg."""
    key = (name, rate)
    if key in _cache:
        return _cache[key]
    path = os.path.join(SFX_DIR, f"{name}.wav")
    if rate != 1.0:
        variant = os.path.join(SFX_DIR, f"{name}@{rate:.3f}.wav")
        if not os.path.exists(variant):
            subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-af",
                            f"asetrate={SR}*{rate},aresample={SR}", "-ac", "2", "-y", variant], check=True)
        path = variant
    with wave.open(path) as w:
        assert w.getframerate() == SR and w.getnchannels() == 2 and w.getsampwidth() == 2, path
        pcm = array.array("h", w.readframes(w.getnframes()))
    data = array.array("f", (s / 32768.0 for s in pcm))
    _cache[key] = data
    return data


events: list[tuple[float, str, float, float, float]] = []  # (time, sound, gain_dB, rate, fade_out_s)


def add(t: float, name: str, gain_db: float, rate: float = 1.0, fade_out: float = 0.0, shift: bool = True) -> None:
    """Times are written on the original 31 s cut; events from the reveal on move by BLIND."""
    if shift and t >= 10.0:
        t += BLIND
    events.append((t - LEAD.get(name, 0.0), name, gain_db, rate, fade_out))


def typing(start: float, end: float, step: float, gain_db: float) -> None:
    rates = (0.94, 1.0, 1.07, 0.97, 1.04)
    n = int((end - start) / step)
    for i in range(n):
        add(start + i * step, "key_click", gain_db - (2 if i % 3 == 1 else 0), rates[i % len(rates)])


# --- Scene 1: hook (0–4s) ---------------------------------------------------------------
add(0.30, "title_slam", -8)                 # "YOUR AGENT"
add(0.55, "title_slam", -10, 0.92)          # "HAS ROOT."
add(0.90, "swoosh", -14)                    # amber underline draws
typing(1.45, 2.80, 0.075, +4)               # "…and it reads untrusted text all day."

# --- Scene 2: attack (4–10.5s) ----------------------------------------------------------
for t in (4.35, 4.75, 4.95, 5.10, 5.25, 5.40, 5.60, 7.00):
    add(t, "data_blip", -23)                # trace rows stream in (kept low: they sit under "poisoned")
add(6.00, "danger_stab", -11)               # red band marks the injected instruction
typing(7.20, 8.10, 0.07, +4)                # agent types the backdoor command
add(8.15, "error_buzz", -12)                # "exit 0 · key appended"
add(8.85, "ironic_ding", -14)               # "web-01 logs look normal."

# --- Scene 2b: who noticed? (10.5–18.5s, absolute times) -----------------------------------
add(10.60, "swoosh", -14, shift=False)              # "Every check passed."
for i, t in enumerate((10.65, 12.85, 15.50)):       # guardrail · SIEM · traces rows slide in
    add(t, "card_whoosh", -13, shift=False)
    add(t + 0.62, "ok_blip", -11, (1.0, 1.06, 1.12)[i], shift=False)   # green verdict chips
add(17.22, "error_buzz", -15, shift=False)          # trace row turns amber: UNREAD
add(17.40, "danger_stab", -12, shift=False)         # "The agent is backdoored."
add(10.50, "riser2", -8)                            # builds into the reveal (peak lands on the cut); under the VO

# --- Scene 3: detection (10.5–17.5s) ----------------------------------------------------
add(10.52, "reveal_braam", -15, fade_out=1.0)   # "ANOTHER AGENT"
add(10.85, "title_slam", -13)                   # "IS WATCHING."
add(11.40, "scan_sweep", -9)                    # amber beam scans the trace
add(11.85, "lock", +1)                          # box locks on the injection
add(12.45, "lock", +1, 0.85)                    # box locks on the harmful action
add(12.70, "card_whoosh", -9)                   # verdict card slides in
add(12.85, "data_blip", -17)                    # status line
for i, t in enumerate((13.10, 13.38, 13.66, 13.94)):
    add(t, "data_blip", -14, 0.8 if i == 2 else 1.0)   # verdict rows (severity row lower)
for i, t in enumerate((14.40, 14.60, 14.80, 15.00)):
    add(t, "chip_pop", -12, (1.0, 1.122, 1.26, 1.498)[i])   # mapping badges, rising A–C#–E–A

# --- Scene 4: alert (17.5–21s) ----------------------------------------------------------
add(17.60, "swoosh", -15)                   # "THEN IT PAGES YOU."
add(18.00, "card_whoosh", -11)              # alert card slides in
add(18.02, "alert_ping", -9)
for i, t in enumerate((18.85, 19.01, 19.17)):
    add(t, "chip_pop", -14, (1.0, 1.122, 1.26)[i])   # Webhook · Slack · PagerDuty

# --- Scene 5: proof (21–25.5s) ----------------------------------------------------------
add(21.15, "title_slam", -18)
add(21.35, "title_slam", -20, 1.05)
add(21.55, "title_slam", -20, 1.1)
for k in range(1, 21):                      # count-up 0→20, power2.out over 1.0s from 21.25
    add(21.25 + 1.0 * (1 - math.sqrt(1 - k / 20)), "data_blip", -19, 1.2)
for i in range(4):
    add(22.40 + i * 0.12, "chip_pop", -18)
    add(23.00 + i * 0.12, "chip_pop", -18, 0.9)

# --- Scene 6: install + lockup (25.5–31s) -----------------------------------------------
add(25.50, "card_whoosh", -12)              # terminal appears
typing(25.80, 26.75, 0.07, +4)              # aoa-ids install opik --smoke-test
add(26.80, "enter_key", +2)
add(26.95, "data_blip", -16)                # "rule … created"
for t in (27.17, 27.39, 27.61, 27.83, 28.05):
    add(t, "ok_blip", -14)                  # ✓ smoke rows
add(28.35, "success", +2)                   # PASSED
add(29.05, "swoosh", -13)                   # terminal clears
add(29.35, "logo_impact", -8, fade_out=1.2) # agent-on-agent-ids lockup
add(29.80, "chip_pop", -15)                 # URL pill

# --- Mix --------------------------------------------------------------------------------
total = int(DURATION * SR) * 2
mix = array.array("f", bytes(4 * total))
for t, name, gain_db, rate, fade_out in events:
    src = load(name, rate)
    g = 10 ** (gain_db / 20)
    start = int(max(t, 0) * SR) * 2
    n = min(len(src), total - start)
    fade_n = int(fade_out * SR) * 2
    for i in range(0, n):
        k = g
        if fade_n and i > n - fade_n:
            k *= (n - i) / fade_n
        mix[start + i] += src[i] * k

# Gentle limiter (tanh above the knee) and a 50 ms fade at the very end.
knee = 0.7
end_fade = int(0.05 * SR) * 2
out = array.array("h", bytes(2 * total))
for i, x in enumerate(mix):
    a = abs(x)
    if a > knee:
        x = math.copysign(knee + (1 - knee) * math.tanh((a - knee) / (1 - knee)), x)
    if i > total - end_fade:
        x *= (total - i) / end_fade
    out[i] = int(max(-1.0, min(1.0, x)) * 32767)

with wave.open(OUT, "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(out.tobytes())
print(f"{len(events)} events -> {OUT}")
