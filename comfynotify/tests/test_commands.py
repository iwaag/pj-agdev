"""The mention command: one Zulip line instead of a handed-over CLI."""

from __future__ import annotations

import json

import pytest

from comfynotify.commands import CommandError, CommandIntake, parse_command
from comfynotify.tickets import load_tickets

BOT = "Comfy Notifier"


def mention(message_id: int, content: str, *, channel="work-m-46", topic="workrun-task3-m-46", sender=42):
    return {
        "id": message_id,
        "type": "stream",
        "sender_id": sender,
        "display_recipient": channel,
        "subject": topic,
        "content": content,
    }


class FakeZulip:
    def __init__(self, messages):
        self.messages, self.reactions = messages, []

    def mentions(self, num_before=100):
        return list(self.messages)

    def add_reaction(self, message_id, emoji_name="eyes"):
        self.reactions.append((message_id, emoji_name))


def build(tmp_path, messages, self_id=7):
    client = FakeZulip(messages)
    posts, log = [], []
    intake = CommandIntake(
        client,
        tickets_dir=tmp_path / "tickets",
        state_path=tmp_path / "command-mark.json",
        comfyui_url="http://comfy.invalid",
        bot_name=BOT,
        self_id=self_id,
        send=lambda channel, topic, text: posts.append((channel, topic, text)),
        log=log.append,
    )
    return intake, client, posts, log


def test_a_watch_line_becomes_a_ticket_pointed_at_the_posting_topic(tmp_path):
    intake, client, posts, _ = build(tmp_path, [mention(100, f"@**{BOT}** watch abc-123 a jump cut")])
    intake.catch_up()  # the first read only seeds the mark
    intake.client.messages.append(mention(101, f"@**{BOT}** watch abc-123 a jump cut"))
    assert intake.catch_up() == 1
    (_, ticket), = load_tickets(tmp_path / "tickets")
    assert ticket["prompt_id"] == "abc-123"
    assert (ticket["channel"], ticket["topic"]) == ("work-m-46", "workrun-task3-m-46")
    assert ticket["note"] == "a jump cut"
    assert ticket["comfyui_url"] == "http://comfy.invalid"
    assert client.reactions == [(101, "eyes")]
    assert posts == []  # the ack is a reaction; a post here would re-serve the owner


def test_the_braindumps_spelling_and_a_backticked_id_are_accepted():
    assert parse_command(f"@**{BOT}** watch_comfy `abc-123` note") == ("abc-123", "note")
    assert parse_command(f"@_**{BOT}** WATCH abc-123") == ("abc-123", "")


@pytest.mark.parametrize("content", ["@**Comfy Notifier**", "@**Comfy Notifier** watch",
                                     "@**Comfy Notifier** please watch my job"])
def test_junk_is_refused_rather_than_guessed(content):
    with pytest.raises(CommandError):
        parse_command(content)


def test_the_command_is_a_line_not_a_message(tmp_path):
    """agforge's listener answers its own run topic with a short report whose
    watch line is in the middle. Reading the message as one command would
    miss the verb and swallow the rest of the report into the note."""
    reply = (
        'running "Submit a slow image job"\n\n'
        f"@**{BOT}** watch b09133ad-5f47 slow relay test\n\n"
        "queued as `b09133ad-5f47` and left with the notifier; this Work "
        "stays open and its next run collects the outputs"
    )
    assert parse_command(reply) == ("b09133ad-5f47", "slow relay test")


def test_a_message_whose_only_mention_line_is_prose_is_still_refused(tmp_path):
    """Front's "I can do this. Here's the plan:" under a bare mention must
    stay an error — line-wise parsing must not turn prose into a command."""
    with pytest.raises(CommandError):
        parse_command(f"@**{BOT}**\n\nI can do this. Here's the plan:\nwatch the topic")


def test_a_malformed_command_posts_one_line_and_writes_no_ticket(tmp_path):
    intake, client, posts, _ = build(tmp_path, [])
    intake.catch_up()
    client.messages.append(mention(200, f"@**{BOT}** please watch my job"))
    intake.catch_up()
    assert load_tickets(tmp_path / "tickets") == []
    assert len(posts) == 1 and posts[0][:2] == ("work-m-46", "workrun-task3-m-46")
    assert posts[0][2].startswith("comfy command not understood:")
    assert client.reactions == []


def test_a_topic_is_told_it_is_not_understood_exactly_once(tmp_path):
    """The error post wakes the poster, and a woken agent that answers by
    naming this bot again would be answered again — the loop `zulip_command`
    step 4 watched start between the notifier and Front."""
    intake, client, posts, log = build(tmp_path, [])
    intake.catch_up()
    client.messages += [
        mention(800, f"@**{BOT}** I can do this. Here is the plan:"),
        mention(801, f"@**{BOT}** and here is the next one"),
        mention(802, f"@**{BOT}** junk elsewhere", topic="another-topic"),
    ]
    intake.catch_up()
    assert len(posts) == 2  # one for each topic, not one per junk message
    assert {topic for _channel, topic, _text in posts} == {"workrun-task3-m-46", "another-topic"}
    assert sum("staying quiet" in line for line in log) == 1
    assert json.loads((tmp_path / "command-mark.json").read_text())["errored_topics"] == [
        "work-m-46/workrun-task3-m-46", "work-m-46/another-topic"]


def test_a_told_topic_still_gets_its_watch_commands_served(tmp_path):
    intake, client, posts, _ = build(tmp_path, [])
    intake.catch_up()
    client.messages.append(mention(900, f"@**{BOT}** nonsense"))
    intake.catch_up()
    client.messages.append(mention(901, f"@**{BOT}** watch abc-123"))
    assert intake.catch_up() == 1
    assert len(load_tickets(tmp_path / "tickets")) == 1 and len(posts) == 1


def test_the_same_feed_replayed_does_nothing_the_second_time(tmp_path):
    """A mention is never consumed by answering it, so only the mark stops a
    restart from ticketing — and double-ticketing serves an agent twice."""
    intake, client, posts, _ = build(tmp_path, [])
    intake.catch_up()
    client.messages.append(mention(300, f"@**{BOT}** watch abc-123"))
    assert intake.catch_up() == 1
    assert intake.catch_up() == 0
    assert len(client.reactions) == 1
    assert json.loads((tmp_path / "command-mark.json").read_text())["last_message_id"] == 300


def test_a_restart_resumes_from_the_mark_on_disk(tmp_path):
    intake, client, _, _ = build(tmp_path, [])
    intake.catch_up()
    client.messages.append(mention(400, f"@**{BOT}** watch old-job"))
    intake.catch_up()
    fresh, fresh_client, _, _ = build(tmp_path, list(client.messages))
    assert fresh.catch_up() == 0  # same feed, new process, no second ticket
    fresh_client.messages.append(mention(401, f"@**{BOT}** watch new-job"))
    assert fresh.catch_up() == 1
    assert {t["prompt_id"] for _, t in load_tickets(tmp_path / "tickets")} == {"old-job", "new-job"}


def test_our_own_posts_selfnotes_and_dms_are_not_commands(tmp_path):
    intake, client, posts, _ = build(tmp_path, [])
    intake.catch_up()
    client.messages += [
        mention(500, f"@**{BOT}** watch mine", sender=7),
        {**mention(501, f"@**{BOT}** watch dm"), "type": "private"},
        mention(502, f"[selfnote][rootchat] @**{BOT}** watch note"),
    ]
    assert intake.catch_up() == 0
    assert load_tickets(tmp_path / "tickets") == [] and posts == []


def test_a_command_in_a_resolved_topic_is_still_honoured(tmp_path):
    """Resolving renames the topic; a command posted just before that still
    deserves its callback, and it belongs where the command landed."""
    intake, client, _, _ = build(tmp_path, [])
    intake.catch_up()
    client.messages.append(mention(600, f"@**{BOT}** watch abc-123", topic="✔ workrun-task3-m-46"))
    assert intake.catch_up() == 1
    (_, ticket), = load_tickets(tmp_path / "tickets")
    assert ticket["topic"] == "✔ workrun-task3-m-46"


def test_a_failing_reaction_never_costs_the_ticket(tmp_path):
    intake, client, _, log = build(tmp_path, [])
    intake.catch_up()
    client.add_reaction = lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("403"))
    client.messages.append(mention(700, f"@**{BOT}** watch abc-123"))
    assert intake.catch_up() == 1
    assert len(load_tickets(tmp_path / "tickets")) == 1
    assert any("ack failed" in line for line in log)


def test_the_queue_path_reads_only_mentions_of_this_bot(tmp_path):
    """The narrow used to answer only our mentions; the queue carries every
    public message, and a post that names somebody else is not a command —
    reading one as such posted a refusal into Front's conversation."""
    from comfynotify.commands import CommandIntake

    intake = CommandIntake(
        object(), tickets_dir=tmp_path / "t", state_path=tmp_path / "s.json", comfyui_url="http://c",
        bot_name="Comfy Notifier", self_id=21, send=lambda *a: None, log=lambda *a: None,
    )
    assert intake.addressed({"content": "@**Omni Agent** may I contact the Observer?"}) is False
    assert intake.addressed({"content": "@**Comfy Notifier** watch abc"}) is True
    assert intake.addressed({"content": "@_**Comfy Notifier** watch abc"}) is True
    assert intake.addressed({"content": "nothing"}, flags=["mentioned"]) is True


def test_a_memo_is_never_a_command_on_either_path(tmp_path):
    """`argue` p2: a memo channel is presentation only. Front's re-voicing
    quotes command lines and names this bot; a well-formed command and a
    malformed one are both left alone there — no ticket, no reaction, no
    refusal post — live, on catch-up, and under ✔."""
    intake, client, posts, _ = build(tmp_path, [])
    intake.catch_up()
    memos = [
        mention(800, f"@**{BOT}** watch abc-123", channel="memo", topic="argue-x-s1"),
        mention(801, f"@**{BOT}** this is prose, not a command", channel="memo-frontdesk", topic="desk-s2"),
        mention(802, f"@**{BOT}** watch abc-456", channel="memo", topic="✔ argue-x-s1"),
    ]
    for one in memos:
        assert intake.addressed(one, flags=["mentioned"]) is False
        assert intake.handle_event_message(one) == 0
    client.messages += memos
    assert intake.catch_up() == 0
    assert load_tickets(tmp_path / "tickets") == [] and posts == [] and client.reactions == []
    # The same line anywhere else is still a command.
    client.messages.append(mention(803, f"@**{BOT}** watch abc-123"))
    assert intake.catch_up() == 1
