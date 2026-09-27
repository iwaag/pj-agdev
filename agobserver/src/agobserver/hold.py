"""Hold a request out of the monitor's hands: a person has taken it over.

`python -m agobserver.hold <why> o<id>…` — the request stays tracked and
traced (its obligations and holder are still written at every look), but
no incident is opened for it and nobody is asked about it until
`python -m agobserver.hold --release o<id>…`. For work whose recovery a
person has kept for themselves — failsafe p1 held m11741 (o11711) this way,
because how to resume it was the Developer's open question.

`python -m agobserver.hold --retire <why> o<id>…` records the other kind
of decision (failsafe p3): a person checked the request and nothing is owed
in it, though its conversations cannot say so — typically residue from
before `end=` markers, a finished run that still reads "open". It leaves
tracking and no incident is opened for it. The retirement lapses by itself
the moment anything new is posted in the request: then the ordinary rules
apply again. `--release` undoes either.

Held and retired requests are separate files (`held.json`, `retired.json`)
the monitor only reads, so this can run while the monitor is looking.
"""

from __future__ import annotations

import json
import sys
import time

from . import monitor as monitoring
from .listener import SPEC


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    release = bool(argv) and argv[0] == "--release"
    retire = bool(argv) and argv[0] == "--retire"
    if retire:
        argv = argv[1:]
    keys = argv[1:]
    if (release and not keys) or (not release and len(argv) < 2):
        print(__doc__, file=sys.stderr)
        return 2
    store = SPEC.local / "incidents"
    files = {name: _load(store / name) for name in (monitoring.HELD_FILE, monitoring.RETIRED_FILE)}
    target = files[monitoring.RETIRED_FILE if retire else monitoring.HELD_FILE]
    for key in keys:
        if not key.startswith("o") or not key[1:].isdigit():
            print(f"{key}: not a request key (o<origin id>)", file=sys.stderr)
            return 2
        if release:
            gone = [name for name, entries in files.items() if entries.pop(key, None)]
            print(f"{key}: {'released from ' + ', '.join(gone) if gone else 'was neither held nor retired'}")
        else:
            target[key] = {"why": argv[0], "at": time.time()}
            print(f"{key}: {'retired' if retire else 'held'}")
    for name, entries in files.items():
        path = store / name
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(entries, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    return 0


def _load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


if __name__ == "__main__":
    raise SystemExit(main())
