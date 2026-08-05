# Step 1 Report: Scaffold Phaser + TS + Vite

## What happened

- Tried the official Phaser installer (`npm create @phaserjs/game@latest -- --template vite-ts`) first: it ignores the template flag and drops into an interactive arrow-key menu, unusable non-interactively. Abandoned as anticipated by the plan's fallback clause.
- Fallback path used: `npm create vite@latest agdevworld-scaffold -- --template vanilla-ts` in a scratch dir, copied into `agdevworld/` (avoids the non-empty-dir prompt; LICENSE and `.git` preserved), then `npm install phaser`.
- Renamed package to `agdevworld`; removed scaffold demo files (`counter.ts`, `style.css`, `src/assets/`, `public/icons.svg`).

## Resulting stack

- phaser **4.2.1**, typescript 6.0.3, vite 8.2.0, Node v26.6.0.
- Plan deviation, deliberate: the plan suggested Phaser 3 "unless 4 is still beta" — npm's `latest` is now Phaser 4 stable (4.2.1), so 4 was kept. The APIs used (text, interactive, tweens, camera shake, Scale.RESIZE) are unchanged from Phaser 3.
- Template `.gitignore` already covers `node_modules/` and `dist/`.

## Layout

- `index.html` — full-viewport dark `#app` container.
- `src/main.ts` — Phaser.Game config (`Scale.RESIZE` for the screen-filling "immersive" head start per plan notes).
- `src/scenes/MainScene.ts` — single scene holding steps 2–3 content.
