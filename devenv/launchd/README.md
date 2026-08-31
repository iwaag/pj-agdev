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
