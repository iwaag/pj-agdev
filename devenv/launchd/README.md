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
`:8094` on every interface). Since workflow_editor p15 it serves only the
Usage view's windows (`/budget`) and history (`/cost`) and holds no
credential; the Zulip mirror (`OPSROOM_ZULIP_ENV`) and the Developer's write
credential (`AGENTROOM_CHAT_ZULIP_ENV`) left with the Front Desk's panels and
the Arguing Room. An installed copy still setting them is told so at startup.

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

`com.agdev.wfe-service.plist.in` is the workflow editor service of the agdev
area: it runs the installed release `.local/agdev/service/current`, on
127.0.0.1:8098, which agdevworld's loopback origin proxies at
`http://localhost:8093/wfe/`. Since `workflow_editor` p4/ex1 the editor is
agdevworld system code (`agdevworld/workflow_editor/`); releases are built and
switched by `agdevworld/scripts/wfe-release.sh`, which restarts this job with
`kickstart -k`. The plist itself does not change between releases.

`com.agdev.agautolab-wfexec.plist.in` is autolab as the executor of workflow
runs (`agautolab.wfexec`, one execution slot). It needs
`agautolab/.local/wfexec.toml` with `wfe = ["<projects>/pj-agdev/.local/agdev/bin/wfe"]`.

`com.agdev.agautolab-zulip` and `com.agdev.agautolab-gateway` are gone
(`retire/old_autolab`): the old autolab listener and its `:8791` window were
the entrance of the retired mission system. The executor above is the whole
of autolab now. Boot out any installed copy of those two labels; nothing
replaces them.
