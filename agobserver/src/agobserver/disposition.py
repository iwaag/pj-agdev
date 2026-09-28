"""A decision about a request's standing, from the operator's terminal.

Since failsafe p6 ex1 a disposition is a record in the request's own
conversation (`agag.dispositions`), the same one `agentchat disposition`
writes on a decision maker's post, read by the trace, the progress panel and
this monitor alike:

- `suppressed` — monitoring suppressed: the work stays open and visible,
  and this monitor does not chase it;
- `completed` — the request ended with its requested outcome;
- `cancelled` / `withdrawn` — the request ended without it (stopped on a
  decision; taken back by whoever asked). Never read as success.

A disposition covers what had happened when it was recorded: a later post
in its scope (a new request, question or result) is not covered and is
monitored as ever; notes, receipts, ✔ and restarts change nothing. A repeat
of the same decision writes nothing. This command writes with Observer's
credential, for a person recording their own decision in person (`--by`) or
on their post (`--evidence`):

    python -m agobserver.disposition --list o<id>
    python -m agobserver.disposition o<id> suppressed|completed|cancelled|withdrawn \\
        [--unit <anchor>] --by <user id> [--evidence <their post>] <why>
    python -m agobserver.disposition --reverse <disposition id> --by <user id> [--evidence <post>] <why>

It replaces `agobserver.hold --retire`/`--unretire` and `retired.json`.
"""

from __future__ import annotations

import argparse
import sys

from agag import dispositions as disposing
from agag.zulip import ZulipClient

from .hold import _name, _okey
from .listener import SPEC


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="agobserver.disposition", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("request", nargs="?", help="o<origin id>")
    parser.add_argument("kind", nargs="?", choices=disposing.KINDS)
    parser.add_argument("--list", dest="listing", metavar="o<id>")
    parser.add_argument("--unit", type=int, default=0)
    parser.add_argument("--reverse", type=int, default=0, metavar="DISPOSITION_ID")
    parser.add_argument("--by", type=int, default=0, help="the person deciding (user id), in person")
    parser.add_argument("--evidence", type=int, default=0)
    parser.add_argument("why", nargs="*")
    args = parser.parse_intermixed_args(argv)
    client = ZulipClient.from_env(SPEC.zulip_env)
    why = " ".join(args.why)
    person = (args.by, _name(client, args.by)) if args.by else None
    try:
        if args.listing:
            found, _, where = disposing.read_dispositions(client, _okey(args.listing))
            print("\n".join(disposing.lines(found, where)))
            return 0
        if args.reverse:
            if not person and not args.evidence:
                raise disposing.DispositionRefused("--by <user id> (in person) or --evidence <their post>")
            written, target = disposing.reverse(client, args.reverse, evidence=args.evidence, why=why,
                                                in_person=person)
            print(f"#{target.id}: " + (f"reversed at #{written}" if written else "already reversed"))
            return 0
        if not args.request or not args.kind or not (person or args.evidence):
            parser.print_help(sys.stderr)
            return 2
        origin = _okey(args.request)
        written, same, _, where = disposing.record(client, origin, args.kind, unit=args.unit, evidence=args.evidence,
                                                   why=why, in_person=person)
        if not written:
            print(f"o{origin}: already in force: #{same.id} ({same.says()}); nothing written")
            return 0
        found, _, where = disposing.read_dispositions(client, origin)
        print(f"o{origin}: recorded #{written} in {where[0]}/{where[1]}")
        print("\n".join(disposing.lines([d for d in found if d.id == written], where)[1:]))
        return 0
    except disposing.DispositionRefused as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
