"""agobserver's chat entrance: one channel, one topic per watch.

Every topic in this instance's own channel is a watch — that is the whole
routing rule, and it is why there is no separate "ask a question" door. The
channel description and the introduction say the same thing, so a requester
never has to guess whether their topic name was the magic one. `watch-` is
the recommended name and the prefix swept in any other subscribed channel,
which is where a watch requested from somewhere else would arrive.

Waiting is *not* here, and cannot be. `agag.listen` reacts to posts, and
its recovery runs at startup and after a resync — neither is a timer, and
nothing posts when a file finishes downloading. So a watch that only ever
ran on the listener's triggers would be evaluated once and then never again.
The due-watch trigger is a separate periodic worker; this module is only the
door a watch comes in through.
"""

from __future__ import annotations

from pathlib import Path

from agag.agent import listener_main

from . import notify, worker
from .intake import handle_watch

from .spec import ROOT, SPEC  # noqa: F401 - the spec lives in agobserver.spec (observer p3)


def main() -> None:
    from agag.mirror import Mirror
    from agag.zulip import log

    # One mirror for both: the listener's intake and the worker's schedule
    # read the same copy of the realm (`better_zulip_call` p1 step 6).
    mirror = Mirror.open(SPEC.zulip_env, SPEC.local / "mirror", log=log)
    # The clock first: it recovers the schedule from the index by itself, so
    # a restart resumes every active watch without waiting for anybody to post.
    worker.start(
        SPEC,
        deliver=lambda client, watch, record: notify.deliver(SPEC, client, watch, record),
        mirror=mirror,
    )
    # The second clock (`robust_workflow` p1 step 4): every active request,
    # looked at without anybody registering a watch for it.
    from . import monitor

    monitor.start(SPEC, mirror)
    from .argue import handle_mention

    # The mention route answers argue invitations only (`agobserver.argue`);
    # every other mention of this bot is logged and left, which is what kept
    # Front's thank-you for a notification from buying a run here.
    listener_main(SPEC, {}, entrance=lambda client, channel, topic: handle_watch(SPEC, client, channel, topic),
                  on_mention=handle_mention, mirror=mirror)


if __name__ == "__main__":
    main()
