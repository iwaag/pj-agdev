"""Intake: what a request becomes, and what the record then holds.

The boundary these cover is the one the p1 tests left open. `test_notify`'s
rename case starts from an accepted record that already holds a message id,
so it proves delivery follows an id — not that a destination *written as a
name* ever becomes one. That is exactly where the defect was: the name
reached the accepted record untouched and every later lookup asked Zulip
which conversation is called that today.

Only the model run is stubbed. Everything else is the real intake path,
including what it writes into the Zulip record, because the record is what a
restart and a lost store are rebuilt from.
"""

from __future__ import annotations

import json

import pytest

from agag.agent import AgentSpec
from agag.selfnote import Conversation
from agag.topics import TopicContext
from agag.zulip import ZulipTimeout

from agobserver import anchor, intake, notify, store, worker

CHANNEL = "agobserver-agstudio1"


@pytest.fixture
def spec(tmp_path) -> AgentSpec:
    (tmp_path / ".local").mkdir()
    (tmp_path / ".local" / "instance.toml").write_text(f'name = "{CHANNEL}"\n')
    return AgentSpec("agobserver", tmp_path)


def decides(monkeypatch, **decision):
    """Stand in for the local model: write the decision it would have made.

    The run is the only thing faked. Reading the file back, the destination
    parse, the Zulip record and the store all run for real.
    """
    def run_role(_spec, _role, _prompt, *, cwd, **_kwargs):
        (cwd / intake.DECISION_FILE).write_text(json.dumps(decision), encoding="utf-8")
        return "", {}, 0

    monkeypatch.setattr(intake, "run_role", run_role)


def ask(spec, zulip, topic: str, text: str = "please watch this", *, before=None):
    """Post a request and serve the topic, as the listener would.

    `before` runs once the context is built and immediately before serving —
    which is where an injected outage has to be armed, or the test's own
    reading of the topic consumes it.
    """
    zulip.post(CHANNEL, topic, text, sender_id=8)
    context = TopicContext(
        client=zulip, channel=CHANNEL, topic=topic, self_id=zulip.self_id,
        bot_name=CHANNEL, history=zulip.topic_history(CHANNEL, topic, 100),
    )
    if before is not None:
        before()
    return intake.serve_intake(spec, context)


def request(**overrides):
    return {
        "accepted": True,
        "condition": "the file is there",
        "target": "/tmp/thing",
        "destination": "front/front-x",
        "question": "",
        **overrides,
    }


def accepted_in(zulip, topic: str) -> dict:
    """The accepted record as Zulip holds it — not as the store cached it."""
    return anchor.read_watch(zulip, CHANNEL, topic, zulip.self_id).accepted


def notifications(zulip, channel, topic, name):
    return [
        entry for entry in zulip.topic_history(channel, topic, 100)
        if f"Watch `{name}` met" in entry["content"]
    ]


# --- what a name becomes ---------------------------------------------------


def test_a_named_destination_is_stored_as_a_message_id(spec, zulip, monkeypatch):
    """The fix, at its narrowest: a name is resolved once, at intake."""
    anchor_id = zulip.post("front", "front-x", "the request")
    decides(monkeypatch, **request())

    result = ask(spec, zulip, "watch-a")

    stored = accepted_in(zulip, "watch-a")
    assert stored["destination_id"] == anchor_id
    # The words are kept: the topic explains what it was told, not what it
    # inferred.
    assert stored["destination"] == "front/front-x"
    assert "front/front-x" in result.sections[0]


def test_a_message_link_is_stored_the_same_way(spec, zulip, monkeypatch):
    """One stored representation, so one lookup path afterwards."""
    anchor_id = zulip.post("front", "front-x", "the request")
    link = f"https://zulip.invalid/#narrow/channel/9-front/topic/front-x/near/{anchor_id}"
    decides(monkeypatch, **request(destination=link))

    ask(spec, zulip, "watch-a")

    assert accepted_in(zulip, "watch-a")["destination_id"] == anchor_id


def test_the_notification_follows_a_named_destination_through_a_rename(spec, zulip, monkeypatch):
    """Accept a name, rename that conversation, let somebody else take the
    freed name, and deliver. The original conversation is the one told."""
    zulip.post("front", "front-x", "the request")
    decides(monkeypatch, **request())
    ask(spec, zulip, "watch-a")
    name = anchor.read_watch(zulip, CHANNEL, "watch-a", zulip.self_id).name

    zulip.topics[("front", "front-renamed")] = zulip.topics.pop(("front", "front-x"))
    zulip.post("front", "front-x", "unrelated work under the reused name")

    watch = anchor.read_watch(zulip, CHANNEL, "watch-a", zulip.self_id)
    record = store.update(
        spec.local / "watches", name,
        last_result={"verdict": "met", "evidence": "there"}, pending_notification=True,
    )
    assert notify.deliver(spec, zulip, watch, record) is True
    assert len(notifications(zulip, "front", "front-renamed", name)) == 1
    assert notifications(zulip, "front", "front-x", name) == []


def test_the_anchor_survives_rebuilding_the_store_from_zulip(spec, zulip, monkeypatch):
    """A lost store loses memory, and must not lose the destination's id.

    The id is in the Zulip record precisely so that `reconcile` puts it back;
    a normalization that only reached the local cache would deliver correctly
    until the first restart and then quietly stop.
    """
    zulip.post("front", "front-x", "the request")
    decides(monkeypatch, **request())
    ask(spec, zulip, "watch-a")
    name = anchor.read_watch(zulip, CHANNEL, "watch-a", zulip.self_id).name
    anchor_id = accepted_in(zulip, "watch-a")["destination_id"]

    for path in (spec.local / "watches").glob("*.json"):
        path.unlink()
    revived = worker.Worker(spec, zulip, interval=60, evaluate=lambda *a: None)
    assert revived.reconcile() == 1
    record = store.load(spec.local / "watches", name)
    assert record["accepted"]["destination_id"] == anchor_id

    zulip.topics[("front", "front-renamed")] = zulip.topics.pop(("front", "front-x"))
    zulip.post("front", "front-x", "unrelated work under the reused name")
    record = store.update(
        spec.local / "watches", name,
        last_result={"verdict": "met", "evidence": "there"}, pending_notification=True,
    )
    assert notify.deliver(spec, zulip, revived.watch_of(record), record) is True
    assert len(notifications(zulip, "front", "front-renamed", name)) == 1


# --- what is not accepted --------------------------------------------------


def test_a_destination_that_cannot_be_checked_is_not_accepted_and_not_reassigned(
    spec, zulip, monkeypatch
):
    """An outage is not the requester's problem to route around.

    The request stays unaccepted — nothing is scheduled against a destination
    nobody has seen — and the reply explains the lookup rather than asking
    for a different conversation, which would be asking them to work around
    a network blip.
    """
    zulip.post("front", "front-x", "the request")
    decides(monkeypatch, **request())

    def outage():
        zulip.fail_next_history = ZulipTimeout("GET messages timed out after 30s")

    result = ask(spec, zulip, "watch-a", before=outage)

    said = result.sections[0]
    assert "could not check" in said.lower()
    assert "instead" not in said                      # not asked to pick another
    watch = anchor.read_watch(zulip, CHANNEL, "watch-a", zulip.self_id)
    assert watch.state == anchor.NEEDS_INPUT
    assert not watch.scheduled


def test_a_destination_that_is_confirmed_gone_asks_for_another(spec, zulip, monkeypatch):
    """A conversation Zulip says is not there is the case where asking the
    requester is the only thing left to do."""
    decides(monkeypatch, **request(destination="front/never-existed"))

    result = ask(spec, zulip, "watch-a")

    assert "instead" in result.sections[0]
    assert anchor.read_watch(zulip, CHANNEL, "watch-a", zulip.self_id).state == anchor.NEEDS_INPUT


def test_a_phrase_is_still_not_a_destination(spec, zulip, monkeypatch):
    decides(monkeypatch, **request(destination="tell me"))
    result = ask(spec, zulip, "watch-a")
    assert "message link" in result.sections[0]


# --- an old record still delivers -----------------------------------------


def test_a_watch_accepted_before_the_fix_still_resolves_by_name(spec, zulip):
    """No migration: a record from p1 carries a name and nothing else, and
    routing falls back to it rather than refusing to deliver."""
    zulip.post("front", "front-x", "the request")
    watch = anchor.Watch(
        channel=CHANNEL, topic="watch-old", watch_id=6676, state=anchor.ACTIVE,
        accepted={"condition": "c", "target": "t", "destination": "front/front-x"},
    )
    assert watch.destination_id is None
    resolved = notify.route(zulip, watch)
    assert resolved.deliverable
    assert resolved.conversation == Conversation("front", "front-x")
