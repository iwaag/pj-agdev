#!/usr/bin/env python3
"""Count Zulip API requests per caller from the server's own request log.

The ground truth for "how many calls did X make": Zulip's `server.log`
records every request with its method, status, path, and the user id that
made it (`(<id>@root via <client>)`). Long polls (`/api/v1/events`, logged
with `lp:`) are counted separately from ordinary calls, because one per
queue per ~90 s is the floor every listener pays and never the problem.

    docker exec <zulip container> cat /var/log/zulip/server.log \
        | python3 callcount.py --since "2026-09-14 02:00" --until "2026-09-14 03:00" \
                               --users users.json

`users.json` is `{"<user id>": "<label>"}` (from `GET /users`; keep it
ignored, it is realm-local). Without it callers are shown by id.

Nothing here is specific to a machine: the container name is the caller's,
and the log format is Zulip 12's.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime

LINE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d+ INFO \[zr(?::\d+)?\] \S+\s+"
    r"(?P<method>[A-Z]+)\s+(?P<status>\d{3})\s+(?P<ms>\d+)ms\s+(?P<detail>\([^)]*\))?\s*"
    r"(?P<path>\S+)(?: \[(?P<bracket>[^\]]*)\])? \((?P<user>[^@]+)@(?P<realm>[^ ]+) via (?P<client>[^)]*)\)"
)
ID_SEGMENT = re.compile(r"/\d+(?=/|$)")


def normalize(path: str) -> str:
    """`/api/v1/messages/6931` -> `/api/v1/messages/<id>`; query strings dropped."""
    path = path.split("?", 1)[0]
    return ID_SEGMENT.sub("/<id>", path)


def parse(line: str):
    found = LINE.match(line)
    if not found:
        return None
    row = found.groupdict()
    row["ts"] = datetime.strptime(row["ts"], "%Y-%m-%d %H:%M:%S")
    row["long_poll"] = bool(row["detail"] and "lp:" in row["detail"])
    row["endpoint"] = normalize(row["path"])
    row["status"] = int(row["status"])
    return row


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", help="YYYY-MM-DD HH:MM (server local time, UTC on this deployment)")
    parser.add_argument("--until", help="YYYY-MM-DD HH:MM")
    parser.add_argument("--users", help="JSON file mapping user id to a label")
    parser.add_argument("--api-only", action="store_true", help="only /api/ paths (skip the web app's /json/ calls)")
    parser.add_argument("--by-endpoint", action="store_true", help="also print the per-caller endpoint breakdown")
    parser.add_argument("--bracket", action="store_true", help="key endpoints by their bracketed detail (narrow) too")
    parser.add_argument("--json", action="store_true", help="print the aggregate as JSON instead of a table")
    args = parser.parse_args(argv)
    since = datetime.strptime(args.since, "%Y-%m-%d %H:%M") if args.since else None
    until = datetime.strptime(args.until, "%Y-%m-%d %H:%M") if args.until else None
    labels = {}
    if args.users:
        with open(args.users, encoding="utf-8") as handle:
            labels = {str(k): str(v) for k, v in json.load(handle).items()}

    calls: Counter = Counter()
    polls: Counter = Counter()
    statuses: dict = defaultdict(Counter)
    endpoints: dict = defaultdict(Counter)
    first = last = None
    for line in sys.stdin:
        row = parse(line)
        if row is None:
            continue
        if since and row["ts"] < since:
            continue
        if until and row["ts"] >= until:
            continue
        if args.api_only and not row["path"].startswith("/api/"):
            continue
        first = row["ts"] if first is None else min(first, row["ts"])
        last = row["ts"] if last is None else max(last, row["ts"])
        who = labels.get(row["user"], row["user"])
        if row["long_poll"]:
            polls[who] += 1
            continue
        calls[who] += 1
        statuses[who][row["status"]] += 1
        key = row["endpoint"]
        if args.bracket and row["bracket"]:
            key = f"{key} [{row['bracket'][:40]}]"
        endpoints[who][f"{row['method']} {key}"] += 1

    if args.json:
        json.dump({"first": str(first), "last": str(last),
                   "calls": dict(calls), "long_polls": dict(polls),
                   "statuses": {k: dict(v) for k, v in statuses.items()},
                   "endpoints": {k: dict(v) for k, v in endpoints.items()}}, sys.stdout, indent=2, sort_keys=True)
        return 0
    span = ((last - first).total_seconds() / 60) if first and last else 0
    print(f"window {first} .. {last} ({span:.1f} min)")
    print()
    print("| caller | calls | 429 | other non-2xx | long polls |")
    print("|---|---:|---:|---:|---:|")
    for who in sorted(set(calls) | set(polls), key=lambda w: (-calls[w], w)):
        bad = sum(n for s, n in statuses[who].items() if s != 429 and not 200 <= s < 300)
        print(f"| {who} | {calls[who]} | {statuses[who][429]} | {bad} | {polls[who]} |")
    print(f"| **total** | {sum(calls.values())} | {sum(s[429] for s in statuses.values())} | | {sum(polls.values())} |")
    if args.by_endpoint:
        for who in sorted(endpoints, key=lambda w: (-calls[w], w)):
            print()
            print(f"**{who}**")
            print()
            print("| endpoint | calls |")
            print("|---|---:|")
            for endpoint, n in endpoints[who].most_common():
                print(f"| `{endpoint}` | {n} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
