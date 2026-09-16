"""Observer in an argue (`argue` p1): a contribution when named, no watch.

Observer had no mention route at all until now, and for a reason recorded
in `pj-agdev/.local/devenv.md`: Front's ordinary replies name the last
speaker, so a mention route that answered every mention would be a loop the
day Front thanked Observer for a notification. The route added here answers
**only** an argue invitation (`agag.argue`), in the argue topic, and leaves
every other mention where it is. A watch is still asked for in Observer's
own channel; nothing here opens one.
"""

from __future__ import annotations

from agag.argue import ROLE as ARGUE_ROLE, is_argue_topic, participate, role_context_path
from agag.zulip import ZulipClient, log

from .intake import is_ack
from .listener import ROOT, SPEC

__all__ = ["ARGUE_ROLE", "handle_mention", "role_context"]


def role_context() -> str:
    return role_context_path(ROOT, ARGUE_ROLE).read_text(encoding="utf-8")


def handle_mention(client: ZulipClient, channel: str, topic: str) -> None:
    if not is_argue_topic(channel, topic):
        log(f"mention in {channel!r}/{topic!r} is not an argue; ignoring")
        return
    log(f"argue invitation in {channel!r}/{topic!r}")
    participate(client, channel, topic, spec=SPEC, role_context=role_context(), drop=is_ack, log=log)
