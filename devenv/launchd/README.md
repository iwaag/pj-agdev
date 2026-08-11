# Local launchd services

The `*.plist.in` templates are the reproducible definitions for agstudio's
native always-on services. Replace `__PROJECTS_ROOT__` with the directory
containing `pj-agdev`, install under `~/Library/LaunchAgents/`, then bootstrap
the jobs in the current GUI launchd domain.

Runtime state and logs remain below each project's ignored `.local/` tree.
