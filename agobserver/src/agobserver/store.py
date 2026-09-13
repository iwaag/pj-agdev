"""The ignored local execution store: progress, not the request.

The request lives in Zulip (`anchor.py`). What lives here is what a *poll*
accumulates and nobody should have to read in a channel — the last
observation, how many evaluations a watch has cost, the id of the newest
message already looked at, and the delivery record. Keeping it out of Zulip
is deliberate: a watch that reports every look is a watch nobody leaves
running.

Recovery is therefore two-sided, and the sides are not equal. Losing this
directory loses **memory**, never work: every active watch is found again by
reading the channel, and the first evaluation after that simply has no
previous observation to compare against. Losing Zulip would lose the watch,
which is why nothing about the request itself is only here.

Every write is atomic (write beside, rename over), so the worker may be
killed at any point without leaving a half-written record behind.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = ["load", "load_all", "now", "path_for", "save", "update"]


def now() -> str:
    return datetime.now(UTC).isoformat()


def path_for(directory: Path, key: str, /) -> Path:
    return directory / f"{key}.json"


def save(directory: Path, key: str, record: dict[str, Any], /) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = path_for(directory, key)
    descriptor, staged_name = tempfile.mkstemp(prefix=".watch.", dir=directory)
    staged = Path(staged_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(record, output, indent=2, sort_keys=True, ensure_ascii=False)
            output.write("\n")
        os.replace(staged, target)
    finally:
        if staged.exists():
            staged.unlink()
    return target


def load(directory: Path, key: str, /) -> dict[str, Any]:
    """This watch's progress, or an empty record. A damaged file is empty.

    A record that cannot be parsed is memory, and memory that cannot be read
    is memory this process does not have — refusing to evaluate over it would
    turn a lost file into a stopped watch.
    """
    try:
        loaded = json.loads(path_for(directory, key).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def load_all(directory: Path) -> dict[str, dict[str, Any]]:
    if not directory.is_dir():
        return {}
    records: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        record = load(directory, path.stem)
        if record:
            records[path.stem] = record
    return records


def update(directory: Path, key: str, /, **fields: Any) -> dict[str, Any]:
    """Merge `fields` into one watch's record.

    `directory` and `key` are positional-only: every field a caller wants to
    store arrives as a keyword, and `watch=` is one of them — a record that
    could not carry its own name because the parameter had taken the word is
    exactly the kind of collision a positional-only marker exists for.
    """
    record = load(directory, key)
    record.update(fields)
    record["updated_at"] = now()
    save(directory, key, record)
    return record
