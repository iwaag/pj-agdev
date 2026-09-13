"""Reading a destination out of what a requester wrote.

This is the deterministic guard that caught the local model filling the
field from the nearest phrase ("Tell me") in step 1. It is a parser rather
than a judgment on purpose: where a notification goes is not a thing to be
inferred.
"""

from __future__ import annotations

import pytest

from agobserver.destination import parse

LINK = "https://example.invalid/#narrow/channel/26-ops/topic/some-topic/near/6673"


@pytest.mark.parametrize("text", [LINK, f"Notify: {LINK}", f"<{LINK}>"])
def test_a_message_link_gives_the_id(text):
    assert parse(text).message_id == 6673


@pytest.mark.parametrize("text", ["msg:6673", "message:6673", "#6673", "6673"])
def test_the_bare_spellings_give_the_id(text):
    assert parse(text).message_id == 6673


def test_a_channel_and_topic_are_accepted():
    parsed = parse("front/front-desk-20260913")
    assert parsed.message_id is None
    assert parsed.conversation.as_pair() == ("front", "front-desk-20260913")


def test_a_topic_may_contain_slashes():
    assert parse("front/a/b").conversation.as_pair() == ("front", "a/b")


@pytest.mark.parametrize("text", ["", "   ", "Tell me", "here", "let me know", "@Front"])
def test_a_phrase_is_not_a_destination(text):
    assert parse(text) is None


def test_a_link_wins_over_the_channel_it_also_contains():
    """The link names a channel and a topic too; the id is the better half."""
    assert parse(LINK).conversation is None
