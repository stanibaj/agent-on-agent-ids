# Architecture diagram

Source of [`docs/assets/aoa-ids-architecture.png`](../assets/aoa-ids-architecture.png), the diagram near the top of the repository README. It uses the design tokens from [`../promo/frame.md`](../promo/frame.md): amber for the watching agent, red for attacker text, green for what is available today, and dashed lines for what is in the pipeline.

Render it at 2x with any headless Chrome (fonts load from Google Fonts):

```bash
chrome-headless-shell --headless --hide-scrollbars --force-device-scale-factor=2 --window-size=1200,680 \
  --default-background-color=00000000 --virtual-time-budget=8000 \
  --screenshot=docs/assets/aoa-ids-architecture.png "file://$PWD/docs/diagram/architecture.html"
```

Update it when a platform moves from the pipeline to available.
