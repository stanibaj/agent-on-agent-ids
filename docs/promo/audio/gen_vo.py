"""Generate the promo voice-over with ElevenLabs text-to-speech (eleven_v4), one clip per line.

Lines are generated separately so each can start exactly on its scene, with request stitching
(previous_text / next_text) so tone and pacing flow across clips.

    python3 gen_vo.py <out_dir> <voice_name> [<voice_name> ...]
"""

import json
import os
import subprocess
import sys
import urllib.request

KEY = open(os.path.expanduser("~/.elevenlabs")).read().strip().split()[0].strip("\"'")
VOICES = {  # ElevenLabs premade voices (library voices need a paid plan via the API)
    "brian": "nPczCjzI2devNBz1zQrb",
    "adam": "pNInz6obpgDQGcFmaJgB",
}
# (clip name, start time in the video, text). Clip names match assets/audio/<name>.m4a.
# vo-3a…vo-3c were sped up 7% (ffmpeg atempo=1.07) so the "who noticed" scene ends before the 18.5 s drop.
LINES = [
    ("vo-1", 0.15, "Your AI agent has root. It reads untrusted text."),
    ("vo-2", 4.60, "One poisoned log line... and it plants a backdoor. Silently."),
    ("vo-3a", 10.50, "Your guardrail saw a harmless task."),
    ("vo-3b", 12.90, "Your SIEM saw a routine command."),
    ("vo-3c", 15.75, "The trace had it all... and nobody read it."),
    ("vo-3", 18.75, "Another agent reads every trace. It catches the attack, and maps it to OWASP and MITRE."),
    ("vo-4", 25.70, "Then it pages you."),
    ("vo-5", 29.20, "Every attack caught. Zero false alarms."),
    ("vo-6", 33.90, "One command to install."),
    ("vo-7", 36.60, "Agent on agent, I.D.S."),
]


def tts(voice_id: str, text: str, prev: str, nxt: str, out_mp3: str) -> int:
    body = {
        "text": text,
        "model_id": "eleven_v4",
        "voice_settings": {"stability": 0.4, "similarity_boost": 0.8},
        "previous_text": prev or None,
        "next_text": nxt or None,
    }
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128",
        data=json.dumps(body).encode(),
        headers={"xi-api-key": KEY, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        open(out_mp3, "wb").write(r.read())
        return int(r.headers.get("x-character-count") or 0)


def main() -> None:
    out_dir, names = sys.argv[1], sys.argv[2:]
    for name in names:
        chars = 0
        os.makedirs(os.path.join(out_dir, name), exist_ok=True)
        for i, (clip, _, text) in enumerate(LINES):
            prev = LINES[i - 1][2] if i else ""
            nxt = LINES[i + 1][2] if i + 1 < len(LINES) else ""
            mp3 = os.path.join(out_dir, name, f"{clip}.mp3")
            chars += tts(VOICES[name], text, prev, nxt, mp3)
            wav = mp3[:-4] + ".wav"
            subprocess.run(["ffmpeg", "-v", "error", "-i", mp3, "-ar", "48000", "-ac", "2", "-y", wav], check=True)
        print(f"{name}: {len(LINES)} lines, {chars} characters billed")


if __name__ == "__main__":
    main()
