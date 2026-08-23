#!/bin/sh
# Fire one run of a scheduled routine (scheduled_routine p1).
#
# Posts a single message, as the Developer, into #front > front-routine-<name>.
# That is all the scheduler does: Front is served because the last real
# poster in a front- topic is not Front, and everything after that is the
# ordinary Front -> forge/autolab -> Front path.
#
#   trigger.sh <name>          e.g. trigger.sh imgprompt
#
# The standing request itself lives in #front > routine-<name> (no front-
# prefix, so Front never serves it as a request); the Developer edits it there.
# Env overrides: AGENTCHAT (binary), AGENTCHAT_ZULIP_ENV (credentials).
set -eu
name="${1:?usage: trigger.sh <name>}"
root="$(cd "$(dirname "$0")/../.." && pwd)"
: "${AGENTCHAT:=$root/agfront/.venv/bin/agentchat}"
: "${AGENTCHAT_ZULIP_ENV:=$root/.local/zulip/developer.env}"
export AGENTCHAT_ZULIP_ENV
unset AGENTCHAT_HOME   # a scheduler has no home conversation; write no [rootchat] note
stamp="$(date -u +%Y-%m-%dT%H:%MZ)"
text="Routine \`$name\`, run of $stamp. The standing request is the latest post in #front › \`routine-$name\`; this topic holds the earlier runs and my comments on them. Do it."
echo "$stamp trigger $name -> #front/front-routine-$name"
"$AGENTCHAT" send front "front-routine-$name" "$text"
