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
