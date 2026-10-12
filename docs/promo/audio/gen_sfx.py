"""Generate the promo's sound effects with ElevenLabs (official sound-generation API, v2 model).

    python3 gen_sfx.py <out_dir>        # key read from ~/.elevenlabs (or edit KEY below)

Generative output differs per run; the stems used in the video are committed in ../assets/audio/.
"""
import json, os, subprocess, sys, urllib.request, concurrent.futures as cf

OUT = sys.argv[1]
KEY = open(os.path.expanduser("~/.elevenlabs")).read().strip().split()[0].strip("\"'")
SFX = {
    "title_slam":   ("Deep cinematic impact hit, short punchy low boom with a tight transient, dark modern trailer", 1.0, 0.6),
    "swoosh":       ("Quick clean airy whoosh, short and subtle", 0.6, 0.6),
    "key_click":    ("Single soft mechanical keyboard key press, close-mic, clean, no room", 0.5, 0.8),
    "enter_key":    ("Heavy satisfying enter key press on a mechanical keyboard, close-mic", 0.5, 0.8),
    "data_blip":    ("Tiny soft digital data blip, subtle high pitched UI tick", 0.5, 0.8),
    "danger_stab":  ("Ominous dissonant synth stab with a distorted low hit, cyber threat warning", 1.6, 0.6),
    "error_buzz":   ("Harsh short digital error buzz, glitchy, system compromised", 0.8, 0.7),
    "ironic_ding":  ("Gentle pleasant friendly notification ding, soft and calm", 1.0, 0.7),
    "riser2":       ("Reverse cymbal swell rising into a hit, gradually getting louder, building tension, cinematic, ends at its loudest point", 1.5, 0.7),
    "lock":         ("Crisp digital lock-on click, short metallic UI confirmation tick, clean, modern interface sound", 0.6, 0.7),
    "reveal_braam": ("Massive cinematic braam impact with sub drop, epic reveal hit, modern trailer", 2.5, 0.6),
    "scan_sweep":   ("Futuristic laser scanner sweep moving across a screen, smooth sci-fi scan", 1.6, 0.6),
    "card_whoosh":  ("Fast smooth swipe whoosh, UI panel sliding in", 0.6, 0.6),
    "chip_pop":     ("Short bright digital pop, UI badge appearing, pleasant and clean", 0.5, 0.8),
    "alert_ping":   ("Urgent but clean two-tone security alert notification ping, modern app alert", 1.2, 0.7),
    "ok_blip":      ("Soft positive confirmation blip, checkmark UI sound", 0.5, 0.8),
    "success":      ("Bright positive success chime, three quick ascending notes, confident clean UI", 1.5, 0.7),
    "logo_impact":  ("Deep cinematic logo reveal impact with a shimmering sparkle tail, premium final hit", 3.0, 0.6),
}

def gen(name, spec):
    text, dur, infl = spec
    body = {"text": text, "duration_seconds": dur, "prompt_influence": infl, "model_id": "eleven_text_to_sound_v2"}
    req = urllib.request.Request("https://api.elevenlabs.io/v1/sound-generation?output_format=mp3_44100_192",
                                 data=json.dumps(body).encode(),
                                 headers={"xi-api-key": KEY, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        mp3 = os.path.join(OUT, f"{name}.mp3")
        open(mp3, "wb").write(r.read())
    wav = os.path.join(OUT, f"{name}.wav")  # decode to 48 kHz stereo for mixing
    shaping = ["-af", "afade=t=in:st=0:d=1.2:curve=exp"] if name == "riser2" else []  # make sure it rises
    subprocess.run(["ffmpeg", "-v", "error", "-i", mp3, *shaping, "-ar", "48000", "-ac", "2", "-y", wav], check=True)
    return name

with cf.ThreadPoolExecutor(4) as pool:
    for f in cf.as_completed([pool.submit(gen, n, s) for n, s in SFX.items()]):
        try:
            print("ok", f.result())
        except Exception as e:
            print("FAILED", e)
