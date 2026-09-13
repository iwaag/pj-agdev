"""A Zulip stand-in, so the failure cases can be *made* rather than waited for.

Delivery failure, a destination that has been deleted, and an ambiguous send
are all real and all rare. Reproducing them against the realm would mean
breaking something that other agents use; reproducing them here costs a
dictionary. The fake speaks only the handful of calls this agent makes, and
every one of them is a real method name on `agag.zulip.ZulipClient` — a fake
that answers a call the client does not have would let a test pass over code
that cannot run.
"""

from __future__ import annotations

import pytest

SELF_ID = 23


class FakeZulip:
    def __init__(self, self_id: int = SELF_ID) -> None:
        self.self_id = self_id
        #: (channel, topic) -> list of {id, sender_id, content}
        self.topics: dict[tuple[str, str], list[dict]] = {}
        self.next_id = 1000
        self.deleted: set[int] = set()
        #: Raised by the next send, then cleared. One ordinary outage.
        self.fail_next_send: Exception | None = None
        #: Accept the send, then raise — the ambiguous case: the post landed
        #: and the caller never learned that it did.
        self.swallow_next_send = False
        self.sent: list[tuple[str, str, str]] = []

    # --- the calls this agent makes ---------------------------------------
    def whoami(self, refresh: bool = False) -> dict:
        return {"user_id": self.self_id, "full_name": "agobserver-agstudio1"}

    def stream_id(self, name: str) -> int:
        return abs(hash(name)) % 1000

    def channel_topics(self, stream_id: int) -> list[str]:
        return [topic for (channel, topic) in self.topics if self.stream_id(channel) == stream_id]

    def topic_history(self, channel: str, topic: str, num_before: int = 50) -> list[dict]:
        return list(self.topics.get((channel, topic), []))[-num_before:]

    def message(self, message_id: int) -> dict | None:
        if message_id in self.deleted:
            return None
        for (channel, topic), messages in self.topics.items():
            for entry in messages:
                if entry["id"] == message_id:
                    return {**entry, "display_recipient": channel, "subject": topic}
        return None

    def send_to_channel(self, channel: str, topic: str, content: str) -> int:
        if self.fail_next_send is not None:
            error, self.fail_next_send = self.fail_next_send, None
            raise error
        message_id = self.post(channel, topic, content, sender_id=self.self_id)
        self.sent.append((channel, topic, content))
        if self.swallow_next_send:
            self.swallow_next_send = False
            raise ConnectionError("the answer never came back")
        return message_id

    def resolve_topic(self, message_id: int, topic: str) -> None:
        for key in list(self.topics):
            if key[1] == topic:
                self.topics[(key[0], f"✔ {topic}")] = self.topics.pop(key)
                return

    # --- fixture helpers ---------------------------------------------------
    def post(self, channel: str, topic: str, content: str, sender_id: int = 1) -> int:
        self.next_id += 1
        self.topics.setdefault((channel, topic), []).append(
            {"id": self.next_id, "sender_id": sender_id, "content": content}
        )
        return self.next_id


@pytest.fixture
def zulip() -> FakeZulip:
    return FakeZulip()
