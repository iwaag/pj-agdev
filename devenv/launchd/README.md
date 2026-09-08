# Local launchd services

The `*.plist.in` templates are the reproducible definitions for agstudio's
native always-on services. Replace `__PROJECTS_ROOT__` with the directory
containing `pj-agdev`, install under `~/Library/LaunchAgents/`, then bootstrap
the jobs in the current GUI launchd domain.

Runtime state and logs remain below each project's ignored `.local/` tree.

`com.agdev.comfy-notifier.plist.in` carries a second placeholder,
`__COMFYUI_URL__`: the notifier now accepts `watch` commands posted as Zulip
mentions, and such a command carries only a `prompt_id`, so the daemon must
know which ComfyUI to poll. The host lives in the installed copy only.

`com.agdev.agentroom.plist.in` is the agdevworld relay (`agdevworld/agentroom`,
loopback `:8094`). It has no extra placeholder, but it does have a reason to
exist that the others do not: its `/ops` half is a *running* reconstruction of
the realm, so every restart costs a full sweep and a stretch of `unknown` rows.
`ThrottleInterval` is therefore 30 s rather than launchd's default 10, so a
crash loop cannot spend the agents' Zulip quota at full speed.

Since `operation_room` p3 it also carries `AGENTROOM_CHAT_ZULIP_ENV` and
`AGENTROOM_SCHEDULE_JSON`. The first is the relay's **write** credential — the
Developer's, because a post from the operation room is the Developer speaking
and buys a Front run — and it is a separate variable from the two read ones so
that a relay without it is read-only rather than quietly posting as its
observer. The second is the routine dispatcher's `schedule.json`, read as a
local file because the routine GUI on `:8093` answers no CORS header.

Since `gauge_panel` ex1 the same template carries a third placeholder,
`__HOME__` (the user's home directory), because the budget read spawns
`codex` and `agy` from `~/.local/bin`, which the job's PATH does not carry.
`AGENTROOM_CODEX_BIN` and `AGENTROOM_AGY_BIN` are those absolute paths. The
relay reads the CLIs' own stores and never writes them, so nothing else is
needed — and remember that `kickstart -k` does not re-read a changed
`EnvironmentVariables` block: `bootout`, wait, `bootstrap`.

Since `front_desk` p3 it carries `AGENTROOM_PLANE_ENV`, a path to an ignored
Plane credentials file. It is the Front Desk's completion button's one
non-Zulip credential: closing a conversation also closes the Plane Work its
delegation opened, and nothing else in this relay touches Plane. The key must
be able to *transition* the projects those conversations reach — a per-agent
key was measured reading one project and refused another (HTTP 403), so the
installed copy points at the admin key rather than at an agent identity.
Unset, the button still closes the chat half and the preview says which Works
it could not see. This is another `EnvironmentVariables` change: `bootout`,
wait, `bootstrap` — `kickstart -k` will not pick it up.
