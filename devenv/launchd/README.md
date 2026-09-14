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
exist that the others do not: its boards are a *running* reconstruction of
the realm — since `better_zulip_call` p1 a persisted mirror on the relay's
own credential (`OPSROOM_ZULIP_ENV`), whose event queue is delivered only
while somebody polls it. A restart within Zulip's queue lifetime resumes the
queue and reads nothing; a longer outage costs one paged read of the realm
(62 calls on this realm). `ThrottleInterval` is 30 s rather than launchd's
default 10 all the same, so a crash loop cannot spend the quota at speed.
`AGENTROOM_ZULIP_ENV`, the former per-request read credential, is gone from
the template; an installed copy that still sets it is told so at startup.

Since `operation_room` p3 it also carries `AGENTROOM_CHAT_ZULIP_ENV`, the
relay's **write** credential — the Developer's, because a post from the
operation room is the Developer speaking and buys a Front run — and it is a
separate variable from the two read ones so that a relay without it is
read-only rather than quietly posting as its observer.

`com.agdev.agobserver-zulip.plist.in` is the Observer agent (`observer` p1).
One job holds two things: the ordinary agag listener, and the due-watch
worker thread it starts. That is why `AGOBSERVER_INTERVAL_SECONDS` is in the
`EnvironmentVariables` block and why changing it needs a `bootout`/
`bootstrap` rather than a `kickstart -k` — the interval is the one setting
this job has, and `kickstart -k` does not re-read the block. Its evaluations
run on the host's own local model, so a short interval costs no account;
what it costs is Zulip calls, one topic listing per tick plus one run per
active watch.

`com.agdev.routine-dispatch` and `com.agdev.routine-gui` are gone
(`refine_routine` p1): a routine is no longer fired from a schedule. Its
guide lives in Zulip (channel folder `routine`, one channel per routine, the
`guide` topic) and a run is a request to Front. Boot out any installed copy
of those two labels; nothing replaces them.

Since `gauge_panel` ex1 the same template carries a third placeholder,
`__HOME__` (the user's home directory), because the budget read spawns
`codex` and `agy` from `~/.local/bin`, which the job's PATH does not carry.
`AGENTROOM_CODEX_BIN` and `AGENTROOM_AGY_BIN` are those absolute paths. The
relay reads the CLIs' own stores and never writes them, so nothing else is
needed — and remember that `kickstart -k` does not re-read a changed
`EnvironmentVariables` block: `bootout`, wait, `bootstrap`.

`AGENTROOM_PLANE_ENV` is **gone** (`refactor` p2 step 4). It carried the
completion button's one non-Zulip credential — closing a conversation also
closed the Plane Work its delegation had opened — and forge was its last
consumer: since p2 forge's plan, outcome and result references live in its
own `assetplan-`/`assetrun-` conversations, as autolab's have since p1. The
relay now holds three credentials, all Zulip. An installed copy still
carrying the variable is harmless (nothing reads it) until the next
`bootout`/`bootstrap`.
