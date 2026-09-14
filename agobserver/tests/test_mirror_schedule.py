"""The worker's schedule off the listener's mirror (`better_zulip_call` p1
step 6): an unchanged watch costs no Zulip call per tick; a ✔ still cancels
— confirmed by one targeted read — before a look and before a notification;
a rename is followed at no cost; a lost store is rebuilt from the index."""

from __future__ import annotations

import shutil
import time

from agag.mirror import Mirror
from agag.mirror.testing import SELF, FakeRealm

from agobserver import anchor, observe, store, worker
from test_lifecycle import ACCEPTED, CHANNEL, spec  # noqa: F401 - the spec fixture

BOT = SELF["user_id"]


def wait_until(predicate, timeout=5.0, what="condition"):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for {what}")


def realm_with_watch(topic: str, *, state: str = anchor.ACTIVE):
    realm = FakeRealm()
    realm.add_channel(35, "agents")
    realm.add_channel(9, CHANNEL)
    realm.post(CHANNEL, topic, "please watch this", sender_id=8, sender_name="Dev", quiet=True)
    watch_id = realm.post(CHANNEL, topic, anchor.watch_note(topic), sender_id=BOT, sender_name=SELF["full_name"], quiet=True)
    realm.post(CHANNEL, topic, anchor.accepted_note(ACCEPTED), sender_id=BOT, sender_name=SELF["full_name"], quiet=True)
    realm.post(CHANNEL, topic, anchor.state_note(state), sender_id=BOT, sender_name=SELF["full_name"], quiet=True)
    return realm, watch_id


def mirrored(realm: FakeRealm, tmp_path) -> Mirror:
    mirror = Mirror.open(tmp_path / "zulip.env", tmp_path / "mirror", client_factory=realm.facet,
                         log=lambda line: None, start=True)
    wait_until(lambda: mirror.live, what="the mirror")
    return mirror


def settle(mirror: Mirror, revision: int) -> None:
    wait_until(lambda: mirror.revision() > revision, what="the mirror to apply the change")


def make(spec, realm, mirror, verdict="not_met", *, deliver=None, on_look=None):
    client = realm.facet()
    looked = []

    def evaluate(_spec, watch, previous):
        looked.append(watch.name)
        if on_look is not None:
            on_look()
        return observe.Observation(verdict, evidence="stub")

    made = worker.Worker(spec, client, interval=60, evaluate=evaluate, mirror=mirror, deliver=deliver)
    made.looked = looked
    made.facet = client
    return made


def test_an_unchanged_watch_costs_no_zulip_call_per_tick(spec, tmp_path):
    realm, watch_id = realm_with_watch("watch-a")
    mirror = mirrored(realm, tmp_path)
    made = make(spec, realm, mirror)
    for _ in range(3):
        made.tick()
    assert made.looked == [f"w{watch_id}"] * 3
    assert made.facet.calls == 1, "whoami, and nothing per tick: the schedule and the location are the index's"
    record = store.load(made.watches_dir, f"w{watch_id}")
    assert record["state"] == anchor.ACTIVE and record["evaluations"] == 3
    mirror.stop()


def test_a_resolve_cancels_before_the_next_look_with_one_confirming_read(spec, tmp_path):
    realm, watch_id = realm_with_watch("watch-a")
    mirror = mirrored(realm, tmp_path)
    made = make(spec, realm, mirror)
    made.tick()
    revision = mirror.revision()
    realm.resolve(CHANNEL, "watch-a")
    settle(mirror, revision)
    made.tick()
    assert made.looked == [f"w{watch_id}"], "no look after the ✔"
    assert store.load(made.watches_dir, f"w{watch_id}")["state"] == worker.CANCELLED
    assert made.facet.calls == 2, "whoami, and one read of the anchor to confirm the terminal answer"
    mirror.stop()


def test_a_resolve_during_the_look_still_cancels_before_the_notification(spec, tmp_path):
    realm, watch_id = realm_with_watch("watch-a")
    mirror = mirrored(realm, tmp_path)
    delivered = []

    def resolve_meanwhile():
        revision = mirror.revision()
        realm.resolve(CHANNEL, "watch-a")
        settle(mirror, revision)

    made = make(spec, realm, mirror, verdict="met", deliver=lambda *a: delivered.append(a) or True,
                on_look=resolve_meanwhile)
    made.tick()
    assert made.looked == [f"w{watch_id}"] and delivered == []
    assert store.load(made.watches_dir, f"w{watch_id}")["state"] == worker.CANCELLED
    mirror.stop()


def test_a_notification_is_preceded_by_a_verifying_read_of_the_anchor(spec, tmp_path):
    realm, watch_id = realm_with_watch("watch-a")
    mirror = mirrored(realm, tmp_path)
    delivered = []
    made = make(spec, realm, mirror, verdict="met", deliver=lambda *a: delivered.append(a) or True)
    made.tick()
    assert len(delivered) == 1
    assert made.facet.calls == 2, "whoami, and the one read right before notifying"
    mirror.stop()


def test_a_rename_is_followed_off_the_index(spec, tmp_path):
    realm, watch_id = realm_with_watch("watch-a")
    mirror = mirrored(realm, tmp_path)
    made = make(spec, realm, mirror)
    made.tick()
    revision = mirror.revision()
    realm.move(realm._topic_ids(CHANNEL, "watch-a"), "watch-a-renamed")
    settle(mirror, revision)
    made.tick()
    record = store.load(made.watches_dir, f"w{watch_id}")
    assert record["topic"] == "watch-a-renamed" and record["state"] == anchor.ACTIVE
    assert made.facet.calls == 1
    mirror.stop()


def test_a_lost_store_is_rebuilt_from_the_index(spec, tmp_path):
    realm, watch_id = realm_with_watch("watch-a")
    mirror = mirrored(realm, tmp_path)
    made = make(spec, realm, mirror)
    made.tick()
    shutil.rmtree(made.watches_dir)
    made.tick()
    assert store.load(made.watches_dir, f"w{watch_id}")["state"] == anchor.ACTIVE
    assert made.looked == [f"w{watch_id}"] * 2 and made.facet.calls == 1
    mirror.stop()
