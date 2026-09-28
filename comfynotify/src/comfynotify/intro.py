"""The notifier's introduction on the `#agents` board (`agent_guide` p2 ex1).

Until this, the `watch` command was described in one agent's guide only
(autolab's worker): nobody else could learn it from the board. Now the
notifier posts `params/intro.md` through `agag.intro.post_intro` like every
agent, so it is in every run's `tools/agents.md` and in `agentchat intro`.
Its roster block declares no channel and no prefixes: the notifier serves
no conversation. The operation room lists every `intro-` topic as an
instance, and one without a roster is shown as an agent whose work cannot be
read; with this block it is an instance with nothing to serve.

The daemon posts it at start-up when the newest post in its `intro-` topic
says something else (its stamp aside), so a restart does not stack identical
posts; `comfynotify intro` posts it unconditionally.
"""

from __future__ import annotations

from pathlib import Path

from agag.instance import instance_name as read_instance_name
from agag.intro import AGENTS_CHANNEL, Roster, intro_text, intro_topic, post_intro

ROOT = Path(__file__).resolve().parents[2]
INTRO_PATH = ROOT / "params" / "intro.md"
INSTANCE_ENV = "COMFYNOTIFY_INSTANCE_NAME"
STAMP = "\n\n---\nPosted: "


def instance_name() -> str:
    return read_instance_name(ROOT / ".local" / "instance.toml", fallback="comfynotify", env_var=INSTANCE_ENV)


def _body(text: str) -> str:
    return (text or "").split(STAMP, 1)[0].strip()


def current(client, instance: str) -> str:
    """The newest introduction posted for `instance`, or ""."""
    history = client.topic_history(AGENTS_CHANNEL, intro_topic(instance), num_before=1)
    return str(history[-1].get("content") or "") if history else ""


def post(client, *, force: bool = False, instance: str | None = None) -> str | None:
    """Post the introduction; unless `force`, only when the board's newest
    one says something else. Returns what was posted, or None."""
    instance = instance or instance_name()
    me = client.whoami()
    roster = Roster(instance=instance, agent="comfynotify", bot=str(me.get("full_name") or "Comfy Notifier"),
                    bot_id=int(me["user_id"]), channel="", prefixes=())
    if not force and _body(current(client, instance)) == _body(intro_text(INTRO_PATH, ROOT, instance, roster=roster)):
        return None
    return post_intro(client, instance=instance, intro_path=INTRO_PATH, root=ROOT, roster=roster)
