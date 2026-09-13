"""The due-watch trigger: the only thing in this agent that is a clock.

Nothing posts when a file finishes downloading. `sweep_serve` reacts to
posts and `on_sweep` fires on startup and queue re-registration, so a watch
served only by the listener's triggers is evaluated once and then never
again. This is the missing trigger, and it is a thread beside the listener
rather than a launchd change — a plist restarts a process, it does not make
one wake up.

Three properties the loop is built around:

- **An empty queue costs nothing.** No active watches means one cheap topic
  listing and no model call at all. Waiting is supposed to be free.
- **A restart does not need a fresh post.** The schedule is rebuilt by
  reading the channel, so an active watch nobody has spoken to since it was
  accepted is picked up again.
- **A watch is found by its own anchor id, twice per tick** — once before
  evaluating and once again immediately before notifying, because the ✔ may
  land during the evaluation it is meant to cancel. Asking the id rather than
  the remembered name is what makes a renamed watch continue, a renamed and
  then resolved one cancel, and an outage conclude nothing at all.

Evaluation is sequential. One watch at a time, each bounded, is enough for
this phase and it makes "why did nothing happen for two minutes" answerable
by reading one log.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

from agag.agent import AgentSpec
from agag.zulip import RESOLVED_TOPIC_PREFIX, ZulipClient, log

from . import anchor, destination as dest, observe, store

#: How often the queue is looked at. A watch's resolution is this interval.
INTERVAL_ENV = "AGOBSERVER_INTERVAL_SECONDS"
DEFAULT_INTERVAL_SECONDS = 60.0
#: Every Nth tick re-reads the whole channel, so a watch this process never
#: saw accepted (another process, a lost store) joins the schedule anyway.
RECONCILE_EVERY = 10
#: Consecutive failed looks before the watch topic is told. One transient
#: failure is not news; three in a row is.
UNABLE_STREAK_REPORT = 3

#: Local-only lifecycle words. `cancelled` is the ✔; `removed` is an anchor
#: Zulip says is gone, which cannot be written into a topic that no longer
#: holds it, so it lives in the store alone.
CANCELLED = "cancelled"
REMOVED = "removed"

#: Set by the store when a watch is met and not yet delivered. It is a field
#: rather than a state because delivery is a separate, retryable step: a met
#: watch whose notification failed is still met, and must not be re-judged.
PENDING = "pending_notification"

__all__ = ["CANCELLED", "REMOVED", "Worker", "interval_seconds", "start"]


def interval_seconds() -> float:
    """The configured interval. A nonsense value is the default, not a crash."""
    try:
        value = float(os.environ.get(INTERVAL_ENV, "") or DEFAULT_INTERVAL_SECONDS)
    except ValueError:
        return DEFAULT_INTERVAL_SECONDS
    return value if value > 0 else DEFAULT_INTERVAL_SECONDS


class Worker:
    """The periodic evaluator. One instance, one thread, one watch at a time."""

    def __init__(
        self,
        spec: AgentSpec,
        client: ZulipClient,
        *,
        interval: float | None = None,
        deliver: Callable[[ZulipClient, anchor.Watch, dict[str, Any]], bool] | None = None,
        evaluate=observe.evaluate,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.spec = spec
        self.client = client
        self.interval = interval if interval is not None else interval_seconds()
        #: Step 3 plugs delivery in here. Without one a met watch is recorded
        #: and held `pending_notification`; nothing is lost and nothing is sent.
        self.deliver = deliver
        self.evaluate = evaluate
        self.clock = clock
        self.watches_dir: Path = spec.local / "watches"
        self.self_id = int(client.whoami()["user_id"])
        self.ticks = 0

    # --- the schedule ---------------------------------------------------

    def scheduled(self) -> list[dict[str, Any]]:
        """The store records this loop is responsible for, oldest first."""
        records = store.load_all(self.watches_dir)
        due = [
            record for record in records.values()
            if record.get("state") in anchor.SCHEDULED or record.get(PENDING)
        ]
        return sorted(due, key=lambda record: str(record.get("accepted_at", "")))

    def reconcile(self) -> int:
        """Rebuild the schedule from Zulip, which is the record.

        Called at start and every `RECONCILE_EVERY` ticks. The store is
        progress; this is what makes losing it lose only memory. A watch the
        channel says is active and the store has never heard of joins the
        schedule with no previous observation, which is exactly right.
        """
        channel = self.spec.instance_name()
        try:
            topics = self.client.channel_topics(self.client.stream_id(channel))
        except Exception as error:  # noqa: BLE001 - a failed read is not a cancelled watch
            log(f"reconcile skipped: cannot list {channel!r}: {error}")
            return 0
        found = 0
        for topic in topics:
            if topic.startswith(RESOLVED_TOPIC_PREFIX):
                continue
            try:
                watch = anchor.read_watch(self.client, channel, topic, self.self_id)
            except Exception as error:  # noqa: BLE001
                log(f"reconcile skipped {channel!r}/{topic!r}: {error}")
                continue
            if not watch.scheduled or watch.watch_id is None:
                continue
            record = store.load(self.watches_dir, watch.name)
            fields = {
                "watch": watch.name, "channel": channel, "topic": topic,
                "state": watch.state, "accepted": dict(watch.accepted),
            }
            # Compared field by field rather than on state alone. The old
            # test — state matches and an acceptance is present — was true of
            # a watch whose topic had just been renamed, so the stale name
            # stayed in the record and everything the watch said went to it.
            if all(record.get(key) == value for key, value in fields.items()):
                continue
            store.update(
                self.watches_dir, watch.name, **fields,
                accepted_at=record.get("accepted_at") or store.now(),
                evaluations=int(record.get("evaluations", 0)),
                recovered_at=store.now(),
            )
            log(f"recovered watch {watch.name} from {channel!r}/{topic!r}")
            found += 1
        return found

    def locate(self, record: dict[str, Any]) -> dest.Resolved:
        """Where this watch is now, asked of the watch's **own anchor id**.

        The one question that answers cancellation, renaming and removal at
        once, because all three are facts about the anchor message:

        - `OPEN` — the conversation it is in now, under whatever name that
          conversation currently has. That name is what everything this watch
          says must be addressed to;
        - `CLOSED` — the anchor sits in a `✔ ` topic. Resolving the topic is
          the cancellation gesture, and this is what recognizes it;
        - `ABSENT` — Zulip says the anchor is gone. The watch has been
          removed; it ends, locally and quietly, because there is no longer a
          conversation to say so in;
        - `FAILED` — the lookup got no answer. Nothing is concluded and the
          attempt is skipped, because a Zulip hiccup read as a ✔ would
          silently drop every watch in the realm.

        What this replaces compared cached topic *names* against the channel
        listing, so a watch renamed for any other reason looked cancelled to
        nobody and kept posting into a name that had moved on.
        """
        watch_id = self.watch_of(record).watch_id
        if watch_id is None:
            return dest.Resolved(
                dest.FAILED, reason=f"{record.get('watch')!r} carries no anchor id"
            )
        return dest.at_message(self.client, watch_id)

    def relocated(self, record: dict[str, Any], located: dest.Resolved) -> dict[str, Any]:
        """The record with its cached conversation refreshed from `located`.

        A name is a cache and this is the write-back. Doing it here rather
        than leaving it to `reconcile` matters: reconcile runs every tenth
        tick, and between two of them everything the watch says would be
        addressed to where it used to be.
        """
        conversation = located.conversation
        if conversation is None:
            return record
        if (record.get("channel"), record.get("topic")) == conversation.as_pair():
            return record
        log(
            f"{record.get('watch')} is now {conversation} "
            f"(was {record.get('channel')}/{record.get('topic')})"
        )
        return store.update(
            self.watches_dir, str(record.get("watch")),
            channel=conversation.channel, topic=conversation.topic,
            renamed_at=store.now(),
        )

    # --- one watch ------------------------------------------------------

    def watch_of(self, record: dict[str, Any]) -> anchor.Watch:
        accepted = record.get("accepted") or {}
        return anchor.Watch(
            channel=str(record.get("channel", "")),
            topic=str(record.get("topic", "")),
            watch_id=int(str(record.get("watch", "w0")).lstrip("w") or 0) or None,
            state=str(record.get("state", "")),
            accepted=accepted if isinstance(accepted, dict) else {},
        )

    def evaluate_one(self, record: dict[str, Any]) -> None:
        name = str(record.get("watch"))
        record = self.stand_down(record)
        if record is None:
            return
        watch = self.watch_of(record)
        observation = self.evaluate(self.spec, watch, record.get("last_result"))
        at = store.now()
        fields: dict[str, Any] = {
            "last_result": observation.as_record(at),
            "last_evaluated_at": at,
            "evaluations": int(record.get("evaluations", 0)) + 1,
        }
        if observation.looked:
            fields["unable_streak"] = 0
        else:
            fields["unable_streak"] = int(record.get("unable_streak", 0)) + 1
        if observation.met:
            fields[PENDING] = True
            fields["met_at"] = at
        record = store.update(self.watches_dir, name, **fields)
        log(
            f"{name} {observation.verdict} in {observation.duration_ms} ms "
            f"(look {record['evaluations']}): {observation.evidence[:160]}"
        )
        if not observation.looked:
            self._report_failure(watch, record, observation)
            return
        if observation.met:
            self._hand_over(watch, record)

    def _report_failure(self, watch: anchor.Watch, record: dict[str, Any], observation) -> None:
        """Say once, in the watch topic, that the target cannot be read.

        Once — at the third consecutive failure — because a transient blip is
        not news and a line per interval would make the topic unreadable. The
        watch keeps its schedule either way: an unreadable target is a reason
        to look again, never a reason to answer the requester.
        """
        streak = int(record.get("unable_streak", 0))
        if streak != UNABLE_STREAK_REPORT:
            return
        try:
            self.client.send_to_channel(
                watch.channel, watch.topic,
                f"I have not been able to look at this {streak} times in a row: "
                f"{observation.evidence}\n\nStill watching — I will keep trying, "
                f"and this is not an answer about the condition.",
            )
        except Exception as error:  # noqa: BLE001
            log(f"could not report the failure streak of {watch.name}: {error}")

    def stand_down(self, record: dict[str, Any]) -> dict[str, Any] | None:
        """`record`, refreshed, or `None` when this watch must not go on.

        Both of the moments the plan names — before observing and again
        before notifying — are this call, because they are the same question.
        Three ways to stop, and they are not the same stop:

        - a ✔ **cancels**: somebody said so, and it is recorded and said
          nowhere, because the gesture was made in the topic itself;
        - a deleted anchor **removes**: the record ends locally, and nothing
          is posted, since the conversation that would have been told is gone;
        - a failed lookup stops **nothing**. The attempt is skipped and the
          watch keeps its state and its pending notification.
        """
        name = str(record.get("watch"))
        located = self.locate(record)
        if located.closed:
            store.update(
                self.watches_dir, name,
                state=CANCELLED, cancelled_at=store.now(), **{PENDING: False},
            )
            log(f"{name} cancelled: its topic is resolved")
            return None
        if located.outcome == dest.ABSENT:
            store.update(
                self.watches_dir, name,
                state=REMOVED, removed_at=store.now(), removed_reason=located.reason,
                **{PENDING: False},
            )
            log(f"{name} removed: {located.reason}")
            return None
        if located.failed:
            log(f"{name} skipped this tick: {located.reason}")
            return None
        return self.relocated(record, located)

    def _hand_over(self, watch: anchor.Watch, record: dict[str, Any]) -> None:
        """Deliver, if there is a delivery route, having re-checked the anchor.

        The second check is here rather than in the delivery code because the
        window it closes is *this* one: the evaluation took real seconds, and
        a ✔ that landed inside them means nobody wants the notification any
        more. It re-reads the location too — everything delivery says about
        this watch goes into the watch's own topic, and that topic may have
        been renamed while the model was looking.
        """
        record = self.stand_down(record)
        if record is None:
            return
        watch = self.watch_of(record)
        if self.deliver is None:
            log(f"{watch.name} met and held pending: no delivery route is configured")
            return
        self.deliver(self.client, watch, record)

    # --- the loop -------------------------------------------------------

    def tick(self) -> int:
        """One pass. Returns how many watches were evaluated."""
        if self.ticks % RECONCILE_EVERY == 0:
            self.reconcile()
        self.ticks += 1
        due = self.scheduled()
        if not due:
            return 0
        evaluated = 0
        for record in due:
            if record.get(PENDING):
                # Met already; it owes a notification, not another judgment.
                self._hand_over(self.watch_of(record), record)
                continue
            try:
                self.evaluate_one(record)
            except Exception as error:  # noqa: BLE001 - one watch never ends the loop
                log(f"evaluating {record.get('watch')} failed: {error!r}")
            evaluated += 1
        return evaluated

    def run(self, stop: threading.Event | None = None) -> None:
        stop = stop or threading.Event()
        log(f"observer worker starting (every {self.interval:g}s)")
        while not stop.is_set():
            started = self.clock()
            try:
                self.tick()
            except Exception as error:  # noqa: BLE001 - the loop outlives its ticks
                log(f"worker tick failed: {error!r}")
            # A fixed cadence: the wait is what is left of the interval, so a
            # look that took 15 s does not push the next one 75 s out. The 1 s
            # floor is the other half of it — an evaluation that overran the
            # whole interval must not produce back-to-back ticks.
            stop.wait(max(1.0, self.interval - max(0.0, self.clock() - started)))


def start(spec: AgentSpec, **kwargs) -> Worker:
    """Run the worker on its own daemon thread, with its own Zulip client.

    Its own client because the listener's is being polled on another thread;
    the skeleton already does the same for its DM route.
    """
    worker = Worker(spec, ZulipClient.from_env(spec.zulip_env), **kwargs)
    threading.Thread(target=worker.run, name="observer-worker", daemon=True).start()
    return worker
