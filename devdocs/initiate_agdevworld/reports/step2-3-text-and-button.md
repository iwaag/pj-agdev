# Steps 2–3 Report: "agdev" text + interactive button

Both implemented in a single scene, [src/scenes/MainScene.ts](../../../agdevworld/src/scenes/MainScene.ts), wired up from `src/main.ts`.

## Step 2 — text

- `this.add.text(...)` with 64px bold white "agdev", `setOrigin(0.5)` centered.
- Instead of hardcoded coordinates, a `layout()` method repositions on the scale manager's `resize` event — the game uses `Phaser.Scale.RESIZE` so the canvas fills the viewport (the "immersive head start" suggested in the plan notes).

## Step 3 — button

- Interactive Phaser text object (the plan's recommended minimal approach): "Push" label, dark background, `setInteractive({ useHandCursor: true })`, hover highlight.
- Reaction on click (implementer's-choice clause exercised): label becomes `Pushed xN` counter, background flips to pink `#e91e63`, the title does a Back-ease scale tween, and the camera shakes briefly.
