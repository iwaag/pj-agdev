# Step 4 report — exercise the director window

All three tests went through the running `POST /director` route. HTTP
responses were saved under the ignored direction-workspace path
`.local/tests/`, and the gateway independently saved matching records as
`.local/agent/director/run-0001.json` through `run-0003.json`.

## Test 1 — project identity

Input: `What is this project?`

The director described a minimal sci-fi game workspace, cited both
`GUIDE.md` and `concept.md`, and repeated the requirement that all images use
futuristic aesthetics. It also correctly observed that the workspace had no
substantive game design or assets yet. This is direct evidence that the agent
read the unmentioned `concept.md` itself; its answer was not available from
the fixed prompt prefix or `GUIDE.md` alone.

Run facts: HTTP 200, 5 turns, 11.632 seconds, USD 0.1090561.

## Test 2 — background prompt

Input: `Suggest prompt to generate background image of this game.`

The director again cited `GUIDE.md` and `concept.md`, then proposed a wide
cinematic background with futuristic megastructures, starships, holographic
elements, nebula atmosphere, blue/cyan light, and warm neon accents. It kept
the suggestion general because the workspace did not specify a concrete
setting.

Run facts: HTTP 200, 6 turns, 17.286 seconds, USD 0.0958761.

The suggested creative prompt was submitted to agforge as request
`fe592977a3d0476bb4a6b91078225c9f`. Agforge returned a verified 1024×576 JPEG
showing a large luminous spacecraft against a star field and blue nebula. To
honor the planned workspace filename, the downloaded image was converted to
an actual PNG and saved as `.local/image/background.png`. Its SHA-256 is
`556c1bd9ca80000026328e3e51ccea5b021a7a02f02e2d6513f5187623839962`.
Git confirms that both the image and saved HTTP evidence are ignored by the
direction repository's `.gitignore`.

## Test 3 — image review

Input: `review .local/image/background.png`

The director opened the image, gave an **Approved** verdict, and explicitly
said it strongly matched the sci-fi direction in `concept.md`. Its evidence
included the futuristic hard-surface spacecraft, blue/orange lighting,
nebula, scale, atmosphere, and background-friendly composition. It also
offered a non-blocking criticism: the underside detail is busy and visibly
symmetrical. The explicit `concept.md` citation and futuristic criteria show
that the workspace direction became the review standard without harness-side
content injection.

Run facts: HTTP 200, 5 turns, 14.197 seconds, USD 0.0951783.

## Totals and observations

The director tests used 16 Claude turns, 43.115 seconds of backend time, and
USD 0.3001105 in total. Every saved HTTP response matched its independently
written gateway record after removing the response-only `kind` and `type`
envelope fields.

The experiment's central observation is positive: a prompt that only told the
agent to read `GUIDE.md` was enough for Claude to discover `concept.md` on its
own in all three tasks, and it applied that unprompted project context both to
generation advice and image review.
