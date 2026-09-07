#!/bin/sh
# Fire one run of a scheduled routine (scheduled_routine p1, operation_room p7).
#
# Posts a single message, as the Developer, into a topic of its own:
# #front > front-routine-<name>-<stamp>. One topic per run: the topic's ✔ is
# the run's resolution and its history is the run's chat. Front is served
# because the last real poster in a front- topic is not Front, and everything
# after that is the ordinary Front -> forge/autolab -> Front path.
#
#   trigger.sh <name> [stamp] [previous_topic]
#     stamp           UTC minute, YYYY-MM-DDTHH:MMZ; defaults to now. The
#                     dispatcher passes its own so the topic it records and
#                     the topic it posts to are the same string.
#     previous_topic  the routine's previous run topic, named in the text so
#                     Front can read it (agentchat) if it wants the context.
#
# The standing request itself lives in #front > routine-<name> (no front-
# prefix, so Front never serves it; the Developer edits it there). Comments
# on a run go into that run's topic, never into routine-<name>.
# Env overrides: AGENTCHAT (binary), AGENTCHAT_ZULIP_ENV (credentials).
set -eu
name="${1:?usage: trigger.sh <name> [stamp] [previous_topic]}"
stamp="${2:-$(date -u +%Y-%m-%dT%H:%MZ)}"
prev="${3:-}"
root="$(cd "$(dirname "$0")/../.." && pwd)"
: "${AGENTCHAT:=$root/agfront/.venv/bin/agentchat}"
: "${AGENTCHAT_ZULIP_ENV:=$root/.local/zulip/developer.env}"
export AGENTCHAT_ZULIP_ENV
unset AGENTCHAT_HOME   # a scheduler has no home conversation; write no [rootchat] note
topic="front-routine-$name-$stamp"
text="Routine \`$name\`, run of $stamp. The standing request is the latest post in #front › \`routine-$name\`. This topic is this run alone; resolve it (✔) when the run is finished."
if [ -n "$prev" ]; then
  text="$text Previous run: #front › \`$prev\`."
fi
text="$text Do it."
echo "$stamp trigger $name -> #front/$topic"
"$AGENTCHAT" send front "$topic" "$text"
