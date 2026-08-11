# Step 2 report — Plane passthrough and prime-agent guide

agdevworld commit `7e21dfe` adds a same-origin, project-scoped Plane boundary
to the assistant service.

## HTTP boundary

The assistant receives `PLANE_URL`, `PLANE_API_KEY`,
`PLANE_WORKSPACE_SLUG`, and `PLANE_PROJECT_ID` from runtime-only Compose
environment. `/api/plane/...` injects `X-API-Key` server-side and fixes every
request to that configured workspace/project. Only `issues` and `states`
subpaths are reachable, with GET/POST/PATCH; it is not an open relay to the
rest of Plane or the LAN.

POST/PATCH bodies may use `state_name`. The boundary reads the running
project's state list, resolves the name case-insensitively, replaces it with
Plane's UUID-shaped `state` field, and forwards the request. Thus neither the
browser nor `GUIDE.md` contains state IDs. Configuration absence, unsupported
paths/methods, unknown state names, and an unreachable Plane service have
distinct JSON errors; none include the key.

## Tool Giving

`assistant/GUIDE.md` now tells the prime agent how and when to:

- inspect the live states and existing issues;
- turn one concrete complaint into one outcome-oriented issue;
- choose visibly between Backlog (triage remains) and Ready (dispatchable);
- create an issue with a useful HTML description and `state_name`;
- recognize the equivalent PATCH transition for callers that support it;
- report passthrough evidence instead of inventing success.

The role prompt also names the two Plane paths. The guide explicitly notes
that the front agent's existing `fetch` tool supports GET/POST, while PATCH is
available to the browser/task UI added in Step 3.

## Verification

- `node --check assistant/server.mjs`
- `npm test`: 33 passed, including five new Plane boundary tests
- `npm run build`: passed; only the existing Phaser bundle-size advisory
- rebuilt the live assistant container with ignored Plane environment values
- live `healthz`, states, issue creation, and issue retrieval returned
  200/200/201/200
- live `state_name: Ready` PATCH returned 200 and the expected live Ready ID
- the temporary probe issue was deleted directly through Plane (HTTP 204)
- the rebuilt `/api/guide` served the new Plane section

The first rebuilt container exposed a syntax error: Markdown backticks added
inside the JavaScript role-prompt template closed the template early. No
Plane request ran in that failed container. Replacing the backticks and adding
the explicit syntax check fixed it; the second container stayed up and passed
the live checks.
