"""agent_guide p2 ex1 step 4: the notifier introduces itself on the board."""

from __future__ import annotations

import re

from comfynotify import intro
from comfynotify.commands import parse_command


class Board:
    def __init__(self):
        self.posts: list[tuple[str, str, str]] = []

    def topic_history(self, channel, topic, num_before=50):
        return [{"content": text} for c, t, text in self.posts if (c, t) == (channel, topic)][-num_before:]

    def send_to_channel(self, channel, topic, text):
        self.posts.append((channel, topic, text))
        return len(self.posts)


def test_posted_once_and_again_only_when_changed():
    board = Board()
    assert intro.post(board, instance="comfynotify-test") is not None
    assert board.posts[0][:2] == ("agents", "intro-comfynotify-test")
    assert intro.post(board, instance="comfynotify-test") is None  # the stamp aside, unchanged
    assert intro.post(board, instance="comfynotify-test", force=True) is not None
    assert len(board.posts) == 2


def test_the_quoted_command_is_one_the_notifier_reads():
    text = intro.INTRO_PATH.read_text(encoding="utf-8")
    fenced = re.findall(r"```\n(.*?)\n```", text, flags=re.S)
    assert len(fenced) == 1 and parse_command(fenced[0].replace("<prompt_id>", "abc-123"))[0] == "abc-123"
    # Every other mention of the bot is inside backticks or a fence: the post itself names nobody.
    outside = re.sub(r"```.*?```", "", text, flags=re.S)
    assert "@**" not in re.sub(r"`[^`]*`", "", outside)
    assert "not an agent" in text
