"""Delivering Observer's posts: owed, sent once, looked for before a repeat.

observer p3. Every post — an incident note in Observer's channel, a message
to the realm's owners, a recovery request — is an outbox row first
(`wfstore`). It is set `sending` *before* the call, so a crash in the middle
leaves it `sending`, never forgotten; anything that may have been posted
(an answer lost, a timeout, a crash) is **looked for by its marker** in
the place it was sent before anything is posted again. Zulip's own "no"
(4xx) fails the row with backoff; an uncertain lookup stays uncertain.
Delivery failure never stops observation and never erases an assignment.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Protocol

from .wfstore import Store

BACKOFF = (15, 60, 300, 900)
LOOKBACK = 100


class Client(Protocol):  # the slice of agag.zulip.ZulipClient used here
    def send_to_channel(self, channel: str, topic: str, content: str) -> int: ...
    def send_dm(self, user_ids: list[int], content: str) -> int: ...
    def topic_history(self, channel: str, topic: str, num_before: int = 50) -> list[dict]: ...
    def dm_history(self, user_ids: list[int], num_before: int = 50) -> list[dict]: ...
    def realm_owners(self) -> list[int]: ...


def with_marker(text: str, marker: str) -> str:
    return f"{text.rstrip()}\n\n`{marker}`"


class Poster:
    def __init__(self, store: Store, client: Callable[[], Client], log: Callable[[str], None] = print):
        self.store = store
        self.client = client
        self.log = log
        self.owners: list[int] | None = None

    def owner_ids(self) -> list[int]:
        if self.owners is None:
            self.owners = sorted(int(u) for u in self.client().realm_owners())
        return self.owners

    def _found(self, row) -> int | None:
        """The id of our post carrying this marker, None when absent; raises when the look fails."""
        c = self.client()
        if row["kind"] == "dm":
            history = c.dm_history(json.loads(row["recipients"] or "[]"), num_before=LOOKBACK)
        else:
            history = []
            for topic in (row["topic"], f"✔ {row['topic']}"):
                history += c.topic_history(row["channel"], topic, num_before=LOOKBACK)
        for m in history:
            if row["marker"] in str(m.get("content") or ""):
                return int(m["id"])
        return None

    def _retry(self, row, now: float, state: str, error: str) -> None:
        tries = int(row["tries"]) + 1
        self.store.set_outbox(row["id"], state=state, tries=tries, error=error[:500], next_try=now + BACKOFF[min(tries - 1, len(BACKOFF) - 1)])

    def deliver(self, row, now: float | None = None) -> str:
        from agag.zulip import ZulipRejected

        now = now or time.time()
        if row["state"] in ("sending", "uncertain"):
            try:
                found = self._found(row)
            except Exception as error:  # noqa: BLE001 - a failed look concludes nothing
                self._retry(row, now, "uncertain", f"looking for the post failed: {error}")
                return "uncertain"
            if found is not None:
                self.store.set_outbox(row["id"], state="sent", message_id=found, sent=now, error=None)
                self.store.event(row["incident"], "post-found", {"outbox": row["id"], "message": found})
                return "sent"
            self.store.event(row["incident"], "post-absent", {"outbox": row["id"]})
        self.store.set_outbox(row["id"], state="sending", tries=int(row["tries"]) + 1)
        text = with_marker(row["text"], row["marker"])
        try:
            c = self.client()
            if row["kind"] == "dm":
                recipients = json.loads(row["recipients"] or "null") or self.owner_ids()
                if row["recipients"] is None:
                    self.store.set_outbox(row["id"], recipients=json.dumps(recipients))
                message = c.send_dm(recipients, text)
            else:
                message = c.send_to_channel(row["channel"], row["topic"], text)
        except ZulipRejected as error:
            self._retry(row, now, "failed", f"Zulip refused: {error}")
            self.log(f"post {row['id']} refused: {error}")
            return "failed"
        except Exception as error:  # noqa: BLE001 - may have been posted: look before repeating
            self._retry(row, now, "uncertain", f"may have been posted: {error}")
            self.log(f"post {row['id']} uncertain: {error}")
            return "uncertain"
        self.store.set_outbox(row["id"], state="sent", message_id=message, sent=now, error=None)
        self.store.event(row["incident"], "posted", {"outbox": row["id"], "message": message, "kind": row["kind"]})
        return "sent"

    def flush(self, now: float | None = None) -> dict[str, int]:
        now = now or time.time()
        done: dict[str, int] = {}
        for row in self.store.outbox_due(now):
            state = self.deliver(row, now)
            done[state] = done.get(state, 0) + 1
        return done


def outbox_summary(store: Store) -> dict[str, Any]:
    counts = store.outbox_counts()
    oldest = store.db.execute("SELECT min(created) FROM outbox WHERE state != 'sent'").fetchone()[0]
    return {"counts": counts, "oldest_unsent": oldest}
