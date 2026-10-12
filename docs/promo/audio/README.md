# Soundtrack

| Stem | Source | How it was made |
|---|---|---|
| `../assets/audio/music.m4a` | **Google Lyria 3** (`google/lyria-3-clip-preview` via OpenRouter, $0.04 per 30 s take) | `lyria_take.py` with the prompt in `lyria_req.json`; best of 3 takes by loudness envelope (quiet tension → phrase drops on an 8 s grid). Trimmed to 28.5 s, faded, normalised to about −17 LUFS. Mounted at **2.5 s** so its drop lands on the 10.5 s reveal. |
| `../assets/audio/vo-1.m4a` … `vo-7.m4a` | **ElevenLabs** text-to-speech (`eleven_v4`, premade voice "Brian") | `gen_vo.py brian` makes one clip per scene line (request stitching keeps the tone continuous); silence trimmed, all lines given one shared gain to about −16 LUFS, then placed at their scene times in `index.html` (group `voiceover`). Verified by transcribing the final mix with ElevenLabs Scribe. |
| `../assets/audio/sfx.m4a` | **ElevenLabs** sound effects (`eleven_text_to_sound_v2`) | `gen_sfx.py` generates 18 effects; `mix_sfx.py` places 122 events on the frames of the animations they belong to (scene start + tween time) and mixes one stem, about −21 LUFS. |

The music bed is carved against the `voiceover` group with HyperFrames' voiceover carve
(`hyperframes-audio/scripts/carve.mjs --comp index.html --bed music`): six voice-following EQ dips
(160 Hz–2.5 kHz) plus a level envelope, so the music keeps its body while the narration stays clear.

Final mix in the rendered MP4: about −17 LUFS integrated, peaks below −1 dBFS, AAC 48 kHz stereo.

```bash
python3 lyria_take.py take.mp3                 # needs OPENROUTER_API_KEY and >= $0.50 credit (audio output requires streaming)
python3 gen_sfx.py sfx/                        # needs an ElevenLabs key in ~/.elevenlabs
python3 gen_vo.py vo/ brian                     # voice-over lines (eleven_v4)
python3 mix_sfx.py sfx/ sfx_stem.wav           # standard library only
ffmpeg -i take.mp3 -af "atrim=0:28.5,afade=t=out:st=26.9:d=1.6,loudnorm=I=-19:TP=-3" -c:a aac -b:a 256k ../assets/audio/music.m4a
ffmpeg -i sfx_stem.wav -af "loudnorm=I=-21:TP=-3" -c:a aac -b:a 256k ../assets/audio/sfx.m4a
```

Generative output differs on every run, so re-running produces a different (not identical) soundtrack;
the committed stems are the ones in the video. Lyria output carries Google's SynthID watermark.

Credits: music generated with Google Lyria 3; voice-over and sound effects generated with [ElevenLabs](https://elevenlabs.io).
