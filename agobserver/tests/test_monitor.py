"""The request monitor (`robust_workflow` p1 step 4) over a fake realm and a
real mirror: a stall nobody registered a watch for is found, the requester's
side is asked — at most twice, and never twice in one retry interval — the
incident is closed as rescued only when a later look no longer finds it, and
a restart neither re-opens it nor asks again.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from agag.mirror import Mirror
from agag.mirror.testing import FakeRealm

from agobserver import monitor as monitoring
from agobserver.intake import handle_watch

DEV, FRONT, AUTOLAB, OBS = 8, 15, 11, 23
ACK = "Message received. Please wait for the reply."
CHANNEL = "agobserver-agstudio1"


class Client:
    """What the monitor posts with: into the fake realm, as Observer."""

    def __init__(self, realm):
        self.realm = realm
        self.sent = []

    def whoami(self):
        return {"user_id": OBS, "full_name": "agobserver-agstudio1"}

    def send_to_channel(self, channel, topic, content):
        self.sent.append((channel, topic, content))
        return self.realm.post(channel, topic, content, sender_id=OBS, sender_name="agobserver-agstudio1")

    def subscriptions(self):
        return [{"name": name} for name in ("front", "pj-x", "work-m1", CHANNEL)]

    def subscribe_channels(self, names):
        self.sent.append(("subscribe", tuple(names)))

    def realm_owners(self):
        return [DEV]

    def users(self):
        return [{"user_id": DEV, "full_name": "Developer"}]


def spec(tmp_path):
    return SimpleNamespace(
        local=tmp_path / "local", topics_root=tmp_path / "topics", records_root=tmp_path / "records",
        instance_name=lambda: CHANNEL,
    )


def post(realm, channel, topic, text, sender):
    names = {DEV: "Developer", FRONT: "Front", AUTOLAB: "autolab-agstudio1", OBS: "agobserver-agstudio1"}
    return realm.post(channel, topic, text, sender_id=sender, sender_name=names[sender])


def stalled_realm():
    """p3's F2 in miniature: task 1 closed, the mission started, task 2 with
    its spec only — autolab did not start it and nobody posted."""
    realm = FakeRealm()
    realm.add_channel(3, "front")
    realm.add_channel(6, "pj-x")
    realm.add_channel(7, "work-m1")
    realm.add_channel(9, CHANNEL)
    ask = post(realm, "front", "front-a", "Build the locations.", DEV)
    post(realm, "front", "front-a", ACK, FRONT)
    post(realm, "pj-x", "workplan-a", "[selfnote][rootchat] front/front-a", FRONT)
    post(realm, "pj-x", "workplan-a", "Mission: build the locations.", FRONT)
    mission = post(realm, "pj-x", "workplan-a", "[selfnote][mission] x", AUTOLAB)
    post(realm, "pj-x", "workplan-a", "# Plan\n\nTwo tasks.", AUTOLAB)
    post(realm, "pj-x", "workplan-a", "[selfnote][state] started", AUTOLAB)
    for serial in (1, 2):
        topic = f"workrun-task{serial}-m{mission}"
        post(realm, "work-m1", topic, f"[selfnote][task] {mission}#{serial}", AUTOLAB)
        post(realm, "work-m1", topic, "[selfnote][rootchat] pj-x/workplan-a", AUTOLAB)
        post(realm, "work-m1", topic, f"# Task {serial}", AUTOLAB)
    task1 = f"workrun-task1-m{mission}"
    post(realm, "work-m1", task1, "[selfnote][rootchat] front/front-a", FRONT)
    post(realm, "work-m1", task1, "Start task 1.", FRONT)
    post(realm, "work-m1", task1, ACK, AUTOLAB)
    post(realm, "work-m1", task1, "@**Front** task 1 done", AUTOLAB)
    post(realm, "work-m1", task1, "Accepted.", FRONT)
    post(realm, "work-m1", task1, "[selfnote][state] completed", AUTOLAB)
    post(realm, "front", "front-a", "@**Developer** task 1 is accepted; task 2 is next.", FRONT)
    return realm, ask, mission


@pytest.fixture
def world(tmp_path):
    realm, ask, mission = stalled_realm()
    mirror = Mirror.open(tmp_path / "zulip.env", tmp_path / "mirror", client_factory=realm.facet,
                         log=lambda line: None, start=True, resync_backoff=0.05)
    deadline = time.time() + 5
    while time.time() < deadline and not mirror.topics("work-m1"):
        time.sleep(0.05)
    # The fake realm's clock: its timestamps are small integers, so the
    # monitor's clock follows them — ten minutes after the last post.
    clock = SimpleNamespace(now=max(m["timestamp"] for m in realm.messages.values()) + 600)
    judged = []

    def judge(spec, candidate, trace_text, tail, incident):
        judged.append(candidate.kind)
        return {"verdict": "legit", "evidence": "a deliberate close"}

    def make():
        return monitoring.Monitor(spec(tmp_path), Client(realm), mirror, judge=judge, clock=lambda: clock.now,
                                  interval=60, window_hours=12)

    yield SimpleNamespace(realm=realm, mirror=mirror, clock=clock, make=make, mission=mission, judged=judged)
    mirror.stop()


def settle(world, predicate=lambda: True):
    deadline = time.time() + 5
    while time.time() < deadline and not predicate():
        time.sleep(0.05)
    time.sleep(0.2)


def incident_posts(world):
    return [m["content"] for m in world.realm.messages.values() if m["display_recipient"] == CHANNEL]


def requests(world):
    return [m for m in world.realm.messages.values()
            if m["display_recipient"] == "front" and m["sender_id"] == OBS]


def test_a_stall_nobody_registered_is_found_and_the_requester_side_asked(world):
    watcher = world.make()
    touched = watcher.tick()
    assert [record["kind"] for record in touched] == ["unstarted"]
    record = touched[0]
    assert record["state"] == monitoring.RECOVERING
    assert record["topic"].startswith("incident-unstarted-")
    settle(world, lambda: requests(world))
    asked = requests(world)
    assert len(asked) == 1 and "task2" in asked[0]["content"] and "@**" not in asked[0]["content"]
    posts = incident_posts(world)
    assert any("Incident: unstarted" in text for text in posts)
    assert any(text.startswith("[selfnote][incident]") for text in posts)
    assert watcher.judgments == 0, "a mechanical fact needs no model"


def test_a_second_look_inside_the_retry_interval_asks_nothing(world):
    watcher = world.make()
    watcher.tick()
    settle(world, lambda: requests(world))
    world.clock.now += 60
    watcher.tick()
    settle(world)
    assert len(requests(world)) == 1


def test_recovery_is_verified_by_a_later_look_and_recorded_as_a_rescue(world):
    watcher = world.make()
    watcher.tick()
    settle(world, lambda: requests(world))
    task2 = f"workrun-task2-m{world.mission}"
    post(world.realm, "work-m1", task2, "[selfnote][rootchat] front/front-a", FRONT)
    post(world.realm, "work-m1", task2, "Start task 2.", FRONT)
    acked = post(world.realm, "work-m1", task2, ACK, AUTOLAB)
    settle(world, lambda: world.mirror.message(acked) is not None)
    world.clock.now += 120
    touched = watcher.tick()
    assert [record["state"] for record in touched] == [monitoring.RESCUED]
    settle(world)
    assert any("**Rescued** after 1 request(s)" in text and "cause is not removed" in text
               for text in incident_posts(world))


def test_requests_are_bounded_and_then_the_owners_are_told(world):
    watcher = world.make()
    for _ in range(4):
        watcher.tick()
        settle(world)
        world.clock.now += monitoring.RETRY_SECONDS + 5
    assert len(requests(world)) == monitoring.MAX_REQUESTS
    reported = [text for text in incident_posts(world) if "Stopped: I could not get this moving" in text]
    assert len(reported) == 1 and reported[0].startswith("@**Developer**")
    world.clock.now += monitoring.RETRY_SECONDS + 5
    watcher.tick()
    settle(world)
    assert len(requests(world)) == monitoring.MAX_REQUESTS, "a reported incident is not asked about again"


def test_a_restart_with_the_store_neither_reopens_nor_asks_again(world):
    world.make().tick()
    settle(world, lambda: requests(world))
    again = world.make()
    again.tick()
    settle(world)
    assert len(requests(world)) == 1
    assert sum("Incident: unstarted" in text for text in incident_posts(world)) == 1


def test_a_lost_store_adopts_the_incident_topic_instead_of_opening_a_second(world, tmp_path):
    first = world.make()
    first.tick()
    settle(world, lambda: requests(world))
    settle(world, lambda: world.mirror.topics(CHANNEL))
    for path in (tmp_path / "local" / "incidents").glob("*.json"):
        path.unlink()
    again = world.make()
    again.tick()
    settle(world)
    assert sum("Incident: unstarted" in text for text in incident_posts(world)) == 1
    assert len(requests(world)) == 1


def test_a_request_whose_own_conversation_is_closed_is_reported_not_asked(world):
    world.realm.resolve("front", "front-a")
    settle(world, lambda: any(t.live_name.startswith("✔") for t in world.mirror.topics("front")))
    watcher = world.make()
    # A ✔ conversation is not an active request: nothing is looked at.
    assert watcher.tick() == []
    assert not requests(world)


def test_an_incident_topic_is_not_a_watch():
    calls = []
    client = SimpleNamespace(whoami=lambda: calls.append("whoami"))
    handle_watch(SimpleNamespace(), client, CHANNEL, "incident-unstarted-5")
    assert calls == []


def test_a_channel_the_bot_has_not_joined_is_joined_and_the_realm_re_read(world):
    """A ✔ in a channel the bot is not in never reaches its mirror."""
    watcher = world.make()
    resyncs = []
    watcher.client.subscriptions = lambda: [{"name": "front"}]
    world.mirror.resync = lambda: resyncs.append(True)
    added = watcher.ensure_subscribed()
    assert "pj-x" in added and "work-m1" in added and "front" not in added
    assert ("subscribe", tuple(added)) in watcher.client.sent and resyncs == [True]


def test_a_post_nobody_acknowledged_at_the_entrance_is_reported_naming_its_owner(world):
    """Trial S1: Front's listener was down; the stop report could only say
    'the agent that owns this conversation'."""
    asked = post(world.realm, "front", "front-b", "A question.", DEV)
    settle(world, lambda: world.mirror.message(asked) is not None)
    world.clock.now = world.realm.messages[asked]["timestamp"] + 400
    watcher = world.make()
    touched = [r for r in watcher.tick() if r["kind"] == "unacknowledged"]
    assert touched and touched[0]["state"] == monitoring.REPORTED
    assert touched[0]["responsible"].startswith("Front")
    settle(world)
    assert not [m for m in requests(world) if m["subject"] == "front-b"], "nobody to ask: no request"
