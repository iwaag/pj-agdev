"""A person's hold on a request, from the operator's terminal.

Since failsafe p6 a hold is a record in the request's own conversation
(`agag.holds`): the same one `agentchat hold` writes on a person's post, read
by the trace, the progress panel and this monitor alike, and settled by the
path its purpose names (an acceptance, the work served again, a
cancellation) without anybody editing a file. This command writes those
records with Observer's credential, for a person recording a decision in
person:

    python -m agobserver.hold --list o<id>
    python -m agobserver.hold o<id> --for acceptance|resume|decision|indefinite \\
        [--unit <any message of the work>] --by <user id> [--evidence <their post>] <why>
    python -m agobserver.hold --release <hold id> --by <user id> [--evidence <their post>] <why>

`--retire` is the other kind of decision (failsafe p3): a person checked the
request and nothing is owed in it, though its conversations cannot say so.
It leaves tracking and no incident is opened for it; the retirement lapses
by itself the moment anything new is posted in the request. It stays a file
(`retired.json`) the monitor only reads:

    python -m agobserver.hold --retire <why> o<id>…
    python -m agobserver.hold --unretire o<id>…
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from agag import holds as holding
from agag.zulip import ZulipClient

from . import monitor as monitoring
from .listener import SPEC


def _okey(value: str) -> int:
    if not value.startswith("o") or not value[1:].isdigit():
        raise SystemExit(f"{value}: not a request key (o<origin id>)")
    return int(value[1:])


def _name(client, user_id: int) -> str:
    try:
        return str(client.call("GET", f"users/{int(user_id)}").get("user", {}).get("full_name") or "")
    except Exception:  # noqa: BLE001 - the id alone still says who
        return ""


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] in (["--retire"], ["--unretire"]):
        return _retire(argv)
    parser = argparse.ArgumentParser(prog="agobserver.hold", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("request", nargs="?", help="o<origin id>")
    parser.add_argument("--list", dest="listing", metavar="o<id>")
    parser.add_argument("--for", dest="purpose", choices=holding.PURPOSES)
    parser.add_argument("--unit", type=int, default=0)
    parser.add_argument("--release", type=int, default=0, metavar="HOLD_ID")
    parser.add_argument("--by", type=int, default=0, help="the person holding it (user id)")
    parser.add_argument("--evidence", type=int, default=0)
    parser.add_argument("why", nargs="*")
    args = parser.parse_args(argv)
    client = ZulipClient.from_env(SPEC.zulip_env)
    why = " ".join(args.why)
    try:
        if args.listing:
            found, _, where = holding.read_holds(client, _okey(args.listing))
            print("\n".join(holding.hold_lines(found, where)))
            return 0
        if args.release:
            if not args.by and not args.evidence:
                raise holding.HoldRefused("--by <the holder's user id> (in person) or --evidence <their post>")
            written, hold = holding.release(client, args.release, args.evidence, why,
                                            in_person=args.by or None)
            print(f"#{hold.id}: " + (f"released at #{written}" if written else f"already {hold.state}"))
            return 0
        if not args.request or not args.purpose or not (args.by or args.evidence):
            parser.print_help(sys.stderr)
            return 2
        origin = _okey(args.request)
        found, result, where = holding.read_holds(client, origin)
        written = holding.place(client, where, result, args.purpose, args.unit or origin, args.evidence, why, found,
                                in_person=(args.by, _name(client, args.by)) if args.by else None)
        print(f"o{origin}: held at #{written} in {where[0]}/{where[1]}")
        return 0
    except holding.HoldRefused as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 1


def _retire(argv: list[str]) -> int:
    store = SPEC.local / "incidents"
    path = store / monitoring.RETIRED_FILE
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        entries = {}
    if argv[0] == "--unretire":
        for key in argv[1:]:
            _okey(key)
            print(f"{key}: {'unretired' if entries.pop(key, None) else 'was not retired'}")
    else:
        if len(argv) < 3:
            print(__doc__, file=sys.stderr)
            return 2
        for key in argv[2:]:
            _okey(key)
            entries[key] = {"why": argv[1], "at": time.time()}
            print(f"{key}: retired")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
