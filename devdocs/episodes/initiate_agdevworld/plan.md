# Plan: Initialize agdevworld (Phaser + TypeScript + Vite)

Goal: get the `agdevworld` submodule from an empty repo (LICENSE only) to a running Phaser app that shows the text "agdev" and one interactive button.

## 0. Resolve blocker: Node.js is not installed

This machine has Homebrew but no Node.js, npm, or any version manager.

```sh
brew install node
```

- Plain `brew install node` (current release) is fine for this experimental environment; a version manager (fnm/volta) is optional and only worth it if you expect to juggle Node versions later.
- Verify with `node -v && npm -v`. Vite requires Node 18+; anything brew installs today satisfies this.
- Network access to registry.npmjs.org is confirmed working.

## 1. Scaffold the project

Work inside `/Users/eiji/projects/pj-agdev/agdevworld` (already a proper submodule; `.git` file points to `../.git/modules/agdevworld`).

Recommended: official Phaser template, which is exactly this stack.

```sh
cd /Users/eiji/projects/pj-agdev/agdevworld
npm create @phaserjs/game@latest . -- --template vite-ts
```

Hints / fallbacks:
- The creator may balk at a non-empty directory (LICENSE, .git are present). If so, scaffold into a temp dir and move files in, or use plain `npm create vite@latest . -- --template vanilla-ts` then `npm install phaser`. Either path is fine — don't fight the tool.
- If the scaffolder generated its own LICENSE or README, keep the existing LICENSE; everything else is yours to overwrite. No backward compatibility concerns — this is a greenfield destructive phase.
- Add a `.gitignore` with at least `node_modules/` and `dist/` if the template didn't.

## 2. Display "agdev" text

In the main scene (e.g. `src/scenes/MainScene.ts` or whatever the template provides):

```ts
this.add.text(512, 300, 'agdev', { fontSize: '64px', color: '#ffffff' }).setOrigin(0.5);
```

- Adjust coordinates to the game config's width/height; `setOrigin(0.5)` centers it.
- Trim the template's demo assets/scenes freely — a single scene is enough.

## 3. Add a button with a reaction

Phaser has no built-in button widget; the idiomatic minimal approach is an interactive text or rectangle:

```ts
const btn = this.add.text(512, 400, 'Push', { fontSize: '32px', backgroundColor: '#444', padding: { x: 16, y: 8 } })
  .setOrigin(0.5)
  .setInteractive({ useHandCursor: true });
btn.on('pointerdown', () => {
  btn.setStyle({ backgroundColor: '#e91e63' });
  this.cameras.main.shake(100, 0.005); // any visible reaction is acceptable
});
```

The reaction is intentionally unspecified ("anything"): color change, tween, sound, counter — implementer's choice. A DOM overlay button is also acceptable if preferred.

## 4. Verify

```sh
npm run dev
```

Open the printed localhost URL (Vite defaults to 5173; the Phaser template may use another port). Confirm: "agdev" renders, button reacts on click. A quick `npm run build` to confirm the TypeScript compiles cleanly is a nice-to-have, not required.

## 5. Commit

Commit inside the submodule first, then record the new submodule pointer in the parent:

```sh
cd agdevworld && git add -A && git commit -m "Initialize Phaser + TS + Vite app with agdev text and button"
cd .. && git add agdevworld && git commit -m "Point agdevworld submodule to initial app"
```

Push only if remote credentials are set up; local commits are sufficient for this phase.

## Notes for the implementer

- Only hard constraints: keep the existing LICENSE file, and stay inside the submodule directory for app code (devdocs live in the parent repo). Everything else — file layout, scene structure, styling, extra polish — is at your discretion.
- Context for taste decisions: per `devdocs/overview.md`, agdevworld will grow into an immersive audiovisual dev interface visualizing cluster state (fed by pj-clusterintent, not yet present). Don't build for that now, but a dark, screen-filling canvas with `scale: { mode: Phaser.Scale.RESIZE }` is a cheap head start toward "immersive".
- Phaser 3 vs the newer Phaser 4 beta: use stable Phaser 3 (what the official template ships) unless you have a reason not to.
