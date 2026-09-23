"""Withdraw incidents the request monitor should not have opened.

`python -m agobserver.withdraw <why> <incident topic or key>…` — an operator's
correction, said in each incident's own topic and recorded as `withdrawn`,
which is neither a recovery nor a decision about the work. Run it while the
monitor is between looks (or stopped): it writes the same records.
"""

from __future__ import annotations

import sys
import time

from agag.zulip import ZulipClient

from . import monitor as monitoring
from .listener import SPEC


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    why, names = argv[0], set(argv[1:])

    class Offline:
        """The monitor's writes need no mirror; where a topic is, is its name."""

        def message(self, message_id):
            return None

        def health(self):
            return {"state": "live"}

    watcher = monitoring.Monitor(SPEC, ZulipClient.from_env(SPEC.zulip_env), Offline())
    done = 0
    for record in watcher.records():
        if record.get("topic") in names or record.get("key") in names:
            if record.get("state") in monitoring.CLOSED:
                print(f"{record['topic']}: already {record['state']}")
                continue
            watcher.close(record, time.time(), monitoring.WITHDRAWN, why)
            print(f"{record['topic']}: withdrawn")
            done += 1
    return 0 if done else 1


if __name__ == "__main__":
    raise SystemExit(main())
