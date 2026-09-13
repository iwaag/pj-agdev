"""agobserver's chat entrance: one channel, one topic per watch.

Every topic in this instance's own channel is a watch — that is the whole
routing rule, and it is why there is no separate "ask a question" door. The
channel description and the introduction say the same thing, so a requester
never has to guess whether their topic name was the magic one. `watch-` is
the recommended name and the prefix swept in any other subscribed channel,
which is where a watch requested from somewhere else would arrive.

Waiting is *not* here, and cannot be. `sweep_serve` reacts to posts, and
`on_sweep` fires on startup and queue re-registration — neither is a timer,
and nothing posts when a file finishes downloading. So a watch that only ever
ran on the listener's triggers would be evaluated once and then never again.
The due-watch trigger is a separate periodic worker; this module is only the
door a watch comes in through.
"""

from __future__ import annotations

from pathlib import Path

from agag.agent import AgentSpec, listener_main
from agag.execopt import Option

from . import notify, worker
from .intake import handle_watch

ROOT = Path(__file__).resolve().parents[2]

SPEC = AgentSpec(
    "agobserver",
    ROOT,
    plan_prefix="watch-",
    run_prefix="",
    # `ag.exec-options.v1`. Observing is deliberately not on this menu: an
    # evaluation runs every interval for as long as a watch waits, and the
    # local model is the reason that is affordable. What can be asked for is
    # a harder *reading* of a request, once.
    exec_options=(
        # Declared rather than left to be prepended, because the pool has to
        # be said out loud: the local harness spends no shared account, so
        # `agag.execpool` derives `unknown` — which is the honest answer for
        # "there is no usage window to judge a threshold against", not a gap.
        Option(
            "default",
            pool="unknown",
            covers="everything",
            summary="the local model on this host; no shared account is spent",
        ),
        Option(
            "sonnet",
            pool="anthropic",
            covers="reading a watch request",
            summary="for a request the local model keeps asking questions about",
        ),
    ),
    exec_roles=("front",),
)


def main() -> None:
    # The clock first: it recovers the schedule from the channel by itself, so
    # a restart resumes every active watch without waiting for anybody to post.
    worker.start(
        SPEC,
        deliver=lambda client, watch, record: notify.deliver(SPEC, client, watch, record),
    )
    listener_main(SPEC, {}, entrance=lambda client, channel, topic: handle_watch(SPEC, client, channel, topic))


if __name__ == "__main__":
    main()
