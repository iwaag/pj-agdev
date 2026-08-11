# Step 3 report — Plane task list and manual dispatch

agdevworld commit `3c91ced` adds a fourth `tasks / plane` view to the existing
application shell.

## Task view

The view reads the project-scoped Plane passthrough and shows Backlog and Ready
issues only. Ready cards expose **Execute** and **Cancel**; Backlog remains
visible without actions. A node picker is populated from `AUTOLAB_NODES` and
prefers a reachable, idle node. The view reports unreachable, unknown, busy,
dispatching, cancelled, and failed outcomes in its headline.

Execute first moves the issue to In Progress, then posts a mission containing
the issue ID, title, and HTML description to the selected node's existing
`/window` boundary. A definite refusal (including the gateway's busy response)
returns the issue to Ready. A network/offline response is ambiguous because
the remote window may have started after the caller timed out; in that case the
issue stays In Progress to avoid presenting Ready work that may already be
running. Cancel changes Ready to Cancelled and never contacts a node.

The assistant's `switch_view` tool and guide now include the task view. This
does not create another entrance: the view accepts no free text and can only
dispatch or cancel issues already filed through the prime-agent conversation.

## Verification

- `npm test`: 33 passed
- `npm run build`: passed; only the existing Phaser bundle-size advisory
- rebuilt the live web and assistant containers; web and Plane task API both
  returned 200
- exercised the rendered 1280x800 task view in a browser with one temporary
  Backlog issue and one Ready issue
- intercepted a synthetic gateway 409 and observed Execute move to In Progress,
  send the expected issue-bearing mission, then roll back to Ready
- observed Cancel move the Ready issue to Cancelled and remove it from the
  dispatchable list
- deleted both temporary Plane issues after the check (HTTP 204) and confirmed
  no probe issues remained
- `nctl status --json` remained healthy with Nautobot 3.1.3, one worker, and no
  pending intent work

The first browser attempt used a keyboard shortcut that the canvas did not
accept, so it selected node cards instead and made no Plane change. The next
attempt exposed a race in the test itself: it accepted the initial Ready value
before the asynchronous dispatch reached In Progress and closed the browser
mid-operation. Inspection found the issue In Progress; it was restored to
Ready, and the check was reordered to wait for the gateway call before the
rollback assertion. The final run passed. No product change was needed for
either test-harness mistake.
