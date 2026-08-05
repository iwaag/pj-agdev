# Step 6 Report: Dockerize and run

(Extension beyond the original plan, requested after initial completion.)

## Environment

Docker was already available on this machine via OrbStack (client 29.4.0, daemon running with many other containers). Nothing needed installing.

## What was added (in `agdevworld/`)

- `Dockerfile` — multi-stage: `node:26-alpine` runs `npm ci && npm run build`, then `nginx:alpine` serves `dist/`. Final image **63.2MB**.
- `compose.yaml` — two services:
  - `web` (default): the production-style nginx image, host port **8090** → 80. 8090 chosen because 8000/8080/8180/8181/8282 are taken by other containers on this host.
  - `dev` (profile `dev`, opt-in): `node:26-alpine` with the source bind-mounted and a named volume shadowing `node_modules` (keeps Linux binaries separate from the macOS host's), running `vite --host 0.0.0.0` for HMR on port 5173. Start with `docker compose --profile dev up dev`.
- `.dockerignore` — excludes `node_modules`, `dist`, `.git`.

## Verification

- `docker compose up -d --build web` → image built, container `agdevworld-web-1` up on http://localhost:8090/.
- index.html and the JS bundle both return 200 through nginx.
- Headless-Chromium screenshot after clicking the button shows "Pushed x1" in pink — full app works in the container, zero console errors.

## Usage

```sh
docker compose up -d --build web    # serve production build on :8090
docker compose --profile dev up dev # dev server with HMR on :5173
docker compose down                 # stop
```

The container was left running after verification.
