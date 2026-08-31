"""Atomic, disk-backed tickets shared by the short CLI and the daemon."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT_S = 20 * 60


def now() -> str:
    return datetime.now(UTC).isoformat()


def write_ticket(directory: Path, ticket: dict[str, Any]) -> Path:
    """Atomically create one ticket; the daemon can safely scan immediately."""
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{ticket['prompt_id']}.json"
    if target.exists():
        raise FileExistsError(f"ticket already exists for {ticket['prompt_id']}")
    descriptor, staged_name = tempfile.mkstemp(prefix=".ticket.", dir=directory)
    staged = Path(staged_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(ticket, output, indent=2, sort_keys=True)
            output.write("\n")
        os.replace(staged, target)
    finally:
        if staged.exists():
            staged.unlink()
    return target


def load_tickets(directory: Path) -> list[tuple[Path, dict[str, Any]]]:
    if not directory.exists():
        return []
    tickets = []
    for path in sorted(directory.glob("*.json")):
        try:
            ticket = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"cannot read ticket {path.name}: {error}") from error
        if not isinstance(ticket, dict):
            raise ValueError(f"ticket {path.name} is not an object")
        tickets.append((path, ticket))
    return tickets


def replace_ticket(path: Path, ticket: dict[str, Any]) -> None:
    descriptor, staged_name = tempfile.mkstemp(prefix=".ticket.", dir=path.parent)
    staged = Path(staged_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(ticket, output, indent=2, sort_keys=True)
            output.write("\n")
        os.replace(staged, path)
    finally:
        if staged.exists():
            staged.unlink()


def archive(path: Path, record: dict[str, Any]) -> Path:
    done = path.parent / "done"
    done.mkdir(parents=True, exist_ok=True)
    target = done / path.name
    record["completed_at"] = now()
    replace_ticket(path, record)
    os.replace(path, target)
    return target
