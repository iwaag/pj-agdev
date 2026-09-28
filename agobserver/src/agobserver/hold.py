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

A decision about the request's standing — monitoring suppressed, or the
request ended as completed, cancelled or withdrawn — is a disposition, the
same kind of record (`agag.dispositions`): `python -m agobserver.disposition`.
failsafe p3's `--retire`/`--unretire` (a private `retired.json`) are gone.
"""

from __future__ import annotations

import argparse
import sys

from agag import holds as holding
from agag.zulip import ZulipClient

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
        print("--retire/--unretire are gone (failsafe p6 ex1): record the decision with "
              "`python -m agobserver.disposition`", file=sys.stderr)
        return 2
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
    args = parser.parse_intermixed_args(argv)
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


if __name__ == "__main__":
    raise SystemExit(main())
