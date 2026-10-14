"""Retire the conversation monitor's local state (observer p3 step 5).

`python -m agobserver.retire_legacy [--dry-run]` — run once at the cutover,
with the old process stopped. It inventories what the conversation monitor
and the watch entrance left in `.local/` — incident records, tracked requests,
held/retired lists, reviews, watches, its health files and probe settings —
and moves them into `.local/archive/observer-p3-<time>/` with
`retirement.json`: each record's last state, and the statement that nothing
was replayed and nothing is claimed complete by the retirement. The Zulip
topics those records point to stay where they are.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

LEGACY = ("incidents", "watches", "triage-replays", "monitor-health.json", "health.toml", "timing.json")


def _read(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def inventory(local: Path) -> dict:
    out: dict = {"incidents": [], "watches": [], "files": []}
    for f in sorted((local / "incidents").glob("*.json")):
        d = _read(f)
        if isinstance(d, dict) and "state" in d:
            out["incidents"].append({"file": f.name, "state": d.get("state"), "kind": d.get("kind"), "topic": d.get("topic"),
                                     "origin": d.get("origin"), "outcome": d.get("outcome")})
        else:
            out["files"].append(f"incidents/{f.name}")
    for f in sorted((local / "watches").glob("*.json")):
        d = _read(f) or {}
        out["watches"].append({"file": f.name, "state": d.get("state") if isinstance(d, dict) else None,
                               "delivered": bool(isinstance(d, dict) and d.get("delivered"))})
    for name in LEGACY:
        if (local / name).exists() and name not in ("incidents", "watches"):
            out["files"].append(name)
    open_incidents = [i for i in out["incidents"] if i["state"] not in ("rescued", "reported", "cancelled", "finished", "withdrawn", "excused", "dismissed")]
    open_watches = [w for w in out["watches"] if w["state"] not in ("met", "cancelled", "undeliverable")]
    out["open"] = {"incidents": open_incidents, "watches": open_watches}
    return out


def retire(local: Path, *, dry_run: bool = False, now: float | None = None) -> dict:
    now = now or time.time()
    inv = inventory(local)
    dest = local / "archive" / f"observer-p3-{time.strftime('%Y%m%dT%H%M%S', time.localtime(now))}"
    record = {
        "schema": "agobserver.legacy-retirement.v1", "at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now)),
        "why": "observer p3: workflow runs are monitored from workflow, Git and executor evidence (agobserver.wfmonitor); "
               "the conversation monitor and its watch entrance are retired",
        "replayed": False, "claims": "none: an archived record says what the old monitor last recorded, not that its work finished",
        "inventory": inv, "archive": str(dest.relative_to(local)),
    }
    if dry_run:
        return record
    dest.mkdir(parents=True, exist_ok=False)
    for name in LEGACY:
        src = local / name
        if src.exists():
            shutil.move(str(src), str(dest / name))
    (dest / "retirement.json").write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
    return record


def main(argv: list[str] | None = None) -> int:
    from .spec import SPEC

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--local", type=Path, default=SPEC.local)
    args = parser.parse_args(argv)
    rec = retire(args.local, dry_run=args.dry_run)
    print(json.dumps({k: rec[k] for k in ("archive", "replayed")} | {"incidents": len(rec["inventory"]["incidents"]), "watches": len(rec["inventory"]["watches"]),
                                                                    "open": {k: len(v) for k, v in rec["inventory"]["open"].items()}, "files": rec["inventory"]["files"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
