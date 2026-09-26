"""Hold a request out of the monitor's hands: a person has taken it over.

`python -m agobserver.hold <why> o<id>…` — the request stays tracked and
traced (its obligations and holder are still written at every look), but
no incident is opened for it and nobody is asked about it until
`python -m agobserver.hold --release o<id>…`. For work whose recovery a
person has kept for themselves — failsafe p1 held m11741 (o11711) this way,
because how to resume it was the Developer's open question.

Held requests are a separate file (`held.json`) the monitor only reads, so
this can run while the monitor is looking.
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
    keys = argv[1:]
    if (release and not keys) or (not release and len(argv) < 2):
        print(__doc__, file=sys.stderr)
        return 2
    path = SPEC.local / "incidents" / monitoring.HELD_FILE
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        held = {}
    for key in keys:
        if not key.startswith("o") or not key[1:].isdigit():
            print(f"{key}: not a request key (o<origin id>)", file=sys.stderr)
            return 2
        if release:
            print(f"{key}: {'released' if held.pop(key, None) else 'was not held'}")
        else:
            held[key] = {"why": argv[0], "at": time.time()}
            print(f"{key}: held")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(held, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
