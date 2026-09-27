"""Record a follow-up decision on developer-review occurrences.

`python -m agobserver.review_status <review topic> <occurrence number>…|all
<status> --note <text> [--ref <commit or link>] [--by <who>]`

`status` is one of `reviewed`, `fix-planned`, `fixed`,
`accepted-limitation` (failsafe p3). The decision is posted in the review
topic itself, naming the occurrences it is about, with one
`[selfnote][occurrence-status] <occurrence> <status>` per occurrence. That
post is the record, and there is no other tracker.

A status is not the review's ✔ (the developer's "looked at"). It accepts
nothing about the original work, and "fixed" says a change was made, not
that the change has been proven in operation. Whoever records it says so
with `--by`. A status already recorded for an occurrence is not posted
again.
"""

from __future__ import annotations

import argparse
import sys

from agag.selfnote import Conversation, note, parse_note
from agag.zulip import ZulipClient, locate

from .listener import SPEC
from .review import REVIEWS_FILE, STATUS_TAG, STATUSES, Reviews

SLUGS = {status.replace(" ", "-"): status for status in STATUSES}


def main(argv: list[str] | None = None, *, client=None, reviews: dict | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agobserver.review_status", description=__doc__.split("\n\n")[0])
    parser.add_argument("topic", help="the review topic (review-<owner>-<kind>[-N])")
    parser.add_argument("occurrences", nargs="+", help="occurrence numbers, or `all`, then the status")
    parser.add_argument("--note", required=True, help="the decision, in words")
    parser.add_argument("--ref", default="", help="a commit, a report or a link")
    parser.add_argument("--by", default="", help="who decided it")
    args = parser.parse_args(argv)
    *which, status = args.occurrences
    if status not in SLUGS or not which:
        parser.error(f"the last word must be one of {', '.join(SLUGS)}, after the occurrence numbers or `all`")
    if reviews is None:
        store = Reviews.__new__(Reviews)
        store.path = SPEC.local / "incidents" / REVIEWS_FILE
        reviews = store.load()
    entry = next((e for e in reviews.values() if e.get("topic") == args.topic.removeprefix("✔ ")), None)
    if entry is None:
        print(f"no review topic {args.topic!r} in the store", file=sys.stderr)
        return 1
    occurrences = list(entry.get("occurrences") or [])
    numbers = range(1, len(occurrences) + 1) if which == ["all"] else [int(n) for n in which]
    chosen = [(n, occurrences[n - 1]) for n in numbers if 1 <= n <= len(occurrences)]
    if len(chosen) != len(list(numbers)):
        print(f"{args.topic} has {len(occurrences)} occurrence(s)", file=sys.stderr)
        return 1
    client = client or ZulipClient.from_env(SPEC.zulip_env)
    channel = SPEC.instance_name()
    found = locate(client, Conversation(channel, entry["topic"], int(entry.get("anchor") or 0) or None))
    topic = found.topic if found is not None else entry["topic"]
    history = client.topic_history(channel, topic, num_before=1000)
    recorded = {parse_note(m.get("content"), STATUS_TAG) for m in history}
    fresh = [(n, oid) for n, oid in chosen if f"{oid} {status}" not in recorded]
    if not fresh:
        print(f"{args.topic}: already recorded as {SLUGS[status]}")
        return 0
    label = ", ".join(str(n) for n, _ in fresh)
    by = f" Recorded by {args.by}." if args.by else ""
    ref = f" ({args.ref})" if args.ref else ""
    client.send_to_channel(channel, topic, (
        f"**Occurrence{'s' if len(fresh) > 1 else ''} {label}: {SLUGS[status]}** — {args.note}{ref}.{by} "
        "This records a follow-up decision. It is not the review's ✔, it accepts nothing about the original "
        "work, and it does not make the incidents' own records other than they were."))
    for _, oid in fresh:
        client.send_to_channel(channel, topic, note(STATUS_TAG, f"{oid} {status}"))
    print(f"{args.topic}: occurrence(s) {label} recorded as {SLUGS[status]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
