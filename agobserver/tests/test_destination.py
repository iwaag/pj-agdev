"""Reading a destination out of what a requester wrote.

This is the deterministic guard that caught the local model filling the
field from the nearest phrase ("Tell me") in step 1. It is a parser rather
than a judgment on purpose: where a notification goes is not a thing to be
inferred.
"""

from __future__ import annotations

import pytest

from agag.zulip import ZulipRejected, ZulipTimeout

from agobserver.destination import ABSENT, CLOSED, FAILED, OPEN, parse, resolve

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


# --- resolution, which is three-valued (ex1 step 1) ------------------------


def test_a_name_resolves_to_an_anchor_in_that_conversation(zulip):
    """The normalization: a name is read once and becomes an id."""
    anchor_id = zulip.post("front", "front-x", "the request")
    resolved = resolve(zulip, parse("front/front-x"))
    assert resolved.outcome == OPEN
    assert resolved.message_id == anchor_id
    assert resolved.conversation.as_pair() == ("front", "front-x")


def test_a_name_is_found_under_its_resolved_spelling_and_is_closed(zulip):
    zulip.post("front", "✔ front-x", "finished work")
    resolved = resolve(zulip, parse("front/front-x"))
    assert resolved.outcome == CLOSED
    assert resolved.terminal and not resolved.deliverable


def test_a_name_nobody_has_ever_posted_under_is_absent(zulip):
    assert resolve(zulip, parse("front/never-existed")).outcome == ABSENT


def test_an_unanswered_lookup_is_not_an_absent_destination(zulip):
    """The defect, as one assertion: a read that failed said "it is gone"."""
    anchor_id = zulip.post("front", "front-x", "the request")

    zulip.fail_next_message = ZulipTimeout("timed out")
    resolved = resolve(zulip, parse(f"msg:{anchor_id}"))
    assert resolved.outcome == FAILED and not resolved.terminal

    zulip.fail_next_history = ZulipTimeout("timed out")
    assert resolve(zulip, parse("front/front-x")).outcome == FAILED

    # And the outage passing is all it takes.
    assert resolve(zulip, parse("front/front-x")).outcome == OPEN


def test_a_refused_lookup_is_an_answer_and_stays_absent(zulip):
    """Zulip saying no is a fact; only silence is retried."""
    anchor_id = zulip.post("front", "front-x", "the request")
    zulip.fail_next_message = ZulipRejected("GET messages/1 -> HTTP 400: Invalid message(s)")
    assert resolve(zulip, parse(f"msg:{anchor_id}")).outcome == ABSENT


def test_a_deleted_anchor_is_absent_and_terminal(zulip):
    anchor_id = zulip.post("front", "front-x", "the request")
    zulip.deleted.add(anchor_id)
    resolved = resolve(zulip, parse(f"msg:{anchor_id}"))
    assert resolved.outcome == ABSENT and resolved.terminal
