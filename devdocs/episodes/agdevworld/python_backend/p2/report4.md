# Phase 2, step 4 — the nginx split, and the four views

**Done.** `docker compose up --build -d web assistant assistant-py` serves all
four views, and chat comes from Python.

## The split

```nginx
location = /api/chat  { proxy_pass http://assistant-py:8093; proxy_read_timeout 310s; }
location = /api/guide { proxy_pass http://assistant-py:8093; }
location = /api/note  { proxy_pass http://assistant-py:8093; }
location /api/        { proxy_pass http://assistant:8091;    proxy_read_timeout 310s; }
```

Exact-match locations win over the prefix regardless of order, so the ordering
above is documentation. The `/api` contract did not change, so the frontend was
not touched.

**`/guide`: neither.** The alias gets no nginx location at all, which is what
it had before — `location /api/` never matched it, so a browser asking for
`/guide` has always received the SPA through `try_files`, and still does.
Adding a route would have been a new behaviour introduced by a step whose job
is to move existing ones. Both services still answer `/guide` directly on 8091
and 8093 for a caller that wants it.

**`vite.config.ts` cannot express the split**: it has one `ASSISTANT_URL`
target, so the `dev` HMR profile reaches only the JS side for the rest of this
phase — `/api/chat` there is served by `server.mjs`. Accepted and temporary;
phase 3 deletes the split and the question with it. No second dev proxy was
built.

## Proven in a real browser

Headless Chromium, 1280×800, against `http://localhost:8090`.

| View | What the canvas showed | Server behind it |
|---|---|---|
| nodes | `cluster / now` — "6 nodes are present", six node cards with converged/unknown badges | `/cluster/*` static + JS `/api/` |
| workspaces | `workspaces / now` — "2 workspaces are present", both cards ACTIVE DEV with their nodes | static snapshot |
| autolab | `autolab / now` — "4 projects on agstudio", each with its coding/director profiles, plus the projects/jobs and node buttons | JS `/api/autolab/*` |
| tasks | `tasks / plane` — "0 backlog / ready tasks", node chooser and refresh | JS `/api/plane/*` |

No `/api/` response failed during the session (every response was captured and
checked, not just eyeballed).

Then, from the **nodes** view, typed into the chat panel and sent:

> Switch to the autolab view, then reply in one short sentence.

The panel showed the assistant bubble "Switched to the autolab view." and the
tool bubble `switch_view {"view":"autolab"}`, and the canvas became
`autolab / now` — a Phaser scene swap, not a DOM class. The browser's own
`/api/chat` response carried `run.id 2191d6ff-…`; that id appears in
`docker compose logs assistant-py`, and the record it wrote says
`local opencode done ['switch_view'] 16014ms`. The chat the human sees is the
Python service's.

Screenshots stay out of the repository — they show real node and workspace
names.

## One unrelated frontend quirk, noticed while driving it

Pressing **V** advances the view by two, not one: `PanelGridScene` registers a
`keydown-V` handler per scene, and a slept scene keeps its keyboard listener,
so two scenes handle the same press. Clicking the `# <next>` label advances by
one correctly. Pre-existing, unrelated to this phase and untouched by it —
noted here so it is not rediscovered as a port regression.
