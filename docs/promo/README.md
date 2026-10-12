# README promo video

Source of the animated GIF at the top of the repository README, built with
[HyperFrames](https://github.com/heygen-com/hyperframes) (HTML + GSAP → deterministic video).

```bash
cd docs/promo
npx hyperframes@0.8.149 preview          # live Studio preview
npx hyperframes@0.8.149 check            # lint + layout + contrast gate
npx hyperframes@0.8.149 render --output renders/aoa-ids-promo.mp4 --fps 30 --quality delivery

# Full-quality MP4 linked from the README (1080p, 60 fps, web-streamable)
npx hyperframes@0.8.149 render --output renders/aoa-ids-promo-1080p60.mp4 --fps 60 --quality delivery
ffmpeg -i renders/aoa-ids-promo-1080p60.mp4 -c copy -movflags +faststart -y ../assets/aoa-ids-demo.mp4

# GIF for the README (two-pass palette, 960px, 15 fps, no dither: the design is flat colour) -> ~8 MB
ffmpeg -i renders/aoa-ids-promo.mp4 -vf "fps=15,scale=960:-1:flags=lanczos,palettegen=max_colors=96:stats_mode=diff" -y /tmp/palette.png
ffmpeg -i renders/aoa-ids-promo.mp4 -i /tmp/palette.png \
  -lavfi "fps=15,scale=960:-1:flags=lanczos [x]; [x][1:v] paletteuse=dither=none:diff_mode=rectangle" \
  -loop 0 -y ../assets/aoa-ids-demo.gif
```

`index.html` mounts the soundtrack (music + sound effects, see [`audio/README.md`](audio/README.md)), the background, seven scene sub-compositions (`compositions/s1-hook.html`, `s2-attack.html`, `s2b-blind.html`, … `s6-cta.html`) and the HUD.
Design tokens live in `frame.md`; the storyboard and brief document the intent. Every claim in the video comes from the
repo's real outputs (verdict format, smoke test, `scripts/validate_judge.py` results).

Keep the background static: a full-frame drift changes every pixel each frame and triples the GIF size.
