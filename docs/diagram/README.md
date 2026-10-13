# Architecture diagram

Source of [`docs/assets/aoa-ids-architecture.png`](../assets/aoa-ids-architecture.png), the diagram near the top of the repository README. It uses the design tokens from [`../promo/frame.md`](../promo/frame.md): amber for AOA-IDS, and a dashed block and arrow for what is in the pipeline. Keep it to four blocks and short labels.

Render it at 2x with any headless Chrome (fonts load from Google Fonts):

```bash
chrome-headless-shell --headless --hide-scrollbars --force-device-scale-factor=2 --window-size=1200,480 \
  --default-background-color=00000000 --virtual-time-budget=8000 \
  --screenshot=docs/assets/aoa-ids-architecture.png "file://$PWD/docs/diagram/architecture.html"
```

Update it when SIEM and log support ships (drop the SOON tag and the dashes).
