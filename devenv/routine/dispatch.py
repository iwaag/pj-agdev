#!/usr/bin/env python3
"""Dispatch concrete routine events from the local rtschedule clone."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


AGDEV_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPO = AGDEV_ROOT / ".local" / "rtschedule"
DEFAULT_TRIGGER = Path(__file__).with_name("trigger.sh")
DEFAULT_AGENTCHAT = AGDEV_ROOT / "agfront" / ".venv" / "bin" / "agentchat"
DEFAULT_ZULIP_ENV = AGDEV_ROOT / ".local" / "zulip" / "developer.env"
DEFAULT_GITEA_TOKEN = AGDEV_ROOT / "agautolab" / ".local" / "gitea" / "autolab-agent.token"
DEFAULT_GITEA_ASKPASS = AGDEV_ROOT / "agautolab" / ".local" / "gitea" / "askpass.sh"
SCHEDULE_POINTER = "Gitea autodev/rtschedule, schedule.json"


class DispatchError(RuntimeError):
    """The schedule could not be read, updated, or dispatched safely."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def parse_time(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise DispatchError(f"{field} is not an ISO-8601 timestamp: {value!r}") from error
    if parsed.tzinfo is None:
        raise DispatchError(f"{field} must include a timezone: {value!r}")
    return parsed.astimezone(timezone.utc)


def format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_schedule(path: Path) -> dict[str, Any]:
    try:
        schedule = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DispatchError(f"cannot read {path}: {error}") from error
    if not isinstance(schedule, dict):
        raise DispatchError("schedule root must be an object")
    requests = schedule.get("requests")
    events = schedule.get("events")
    if not isinstance(requests, list) or not isinstance(events, list):
        raise DispatchError("schedule must contain requests and events arrays")
    request_ids: set[str] = set()
    for request in requests:
        if not isinstance(request, dict) or not isinstance(request.get("id"), str):
            raise DispatchError("every request must be an object with a string id")
        if request["id"] in request_ids:
            raise DispatchError(f"duplicate request id: {request['id']}")
        request_ids.add(request["id"])
        parse_time(request["said_at"], f"request {request['id']} said_at")
        parse_time(request["until"], f"request {request['id']} until")
        if not isinstance(request.get("text"), str):
            raise DispatchError(f"request {request['id']} has no text")
    event_ids: set[str] = set()
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get("id"), str):
            raise DispatchError("every event must be an object with a string id")
        event_id = event["id"]
        if event_id in event_ids:
            raise DispatchError(f"duplicate event id: {event_id}")
        event_ids.add(event_id)
        parse_time(event["at"], f"event {event_id} at")
        if event.get("from") not in request_ids:
            raise DispatchError(f"event {event_id} refers to unknown request {event.get('from')!r}")
        if event.get("fired_at") is not None:
            parse_time(event["fired_at"], f"event {event_id} fired_at")
        if event.get("logical_at") is not None:
            parse_time(event["logical_at"], f"event {event_id} logical_at")
        kind = event.get("kind")
        if kind == "fire" and not isinstance(event.get("routine"), str):
            raise DispatchError(f"fire event {event_id} has no routine")
        if kind == "decide" and not isinstance(event.get("ask"), str):
            raise DispatchError(f"decide event {event_id} has no ask")
        if kind not in {"fire", "decide"}:
            raise DispatchError(f"event {event_id} has unknown kind {kind!r}")
    return schedule


def atomic_write(path: Path, schedule: dict[str, Any]) -> None:
    text = json.dumps(schedule, ensure_ascii=False, indent=2) + "\n"
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            handle.write(text)
            temporary = Path(handle.name)
        temporary.replace(path)
    except OSError as error:
        raise DispatchError(f"cannot atomically write {path}: {error}") from error


def request_map(schedule: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {request["id"]: request for request in schedule["requests"]}


def due_events(schedule: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    requests = request_map(schedule)
    due = []
    for event in schedule["events"]:
        if event["fired_at"] is not None or parse_time(event["at"], f"event {event['id']} at") > now:
            continue
        request = requests[event["from"]]
        if parse_time(request["until"], f"request {request['id']} until") < now:
            continue
        due.append(event)
    return sorted(due, key=lambda event: (parse_time(event["at"], "event at"), event["id"]))


def prune_old_events(schedule: dict[str, Any], now: datetime) -> list[str]:
    cutoff = now - timedelta(days=7)
    removed = [
        event["id"]
        for event in schedule["events"]
        if parse_time(event["at"], f"event {event['id']} at") < cutoff
    ]
    if removed:
        removed_set = set(removed)
        schedule["events"] = [event for event in schedule["events"] if event["id"] not in removed_set]
    return removed


def dispatch_schedule(
    path: Path,
    now: datetime,
    *,
    real_now: datetime | None = None,
    before_action: Callable[[str], None],
    fire: Callable[[str], None],
    decide: Callable[[str, str], None],
    after_action: Callable[[str], None],
    after_prune: Callable[[list[str]], None],
) -> list[str]:
    """Dispatch one snapshot. The durable marker is written before each action.

    `now` is the tick's clock — what is due, and what has expired. `real_now`
    is when the dispatch actually happened; it differs only under `--now`, the
    accelerated test clock. `fired_at` is always the real time, so the record
    never claims an action happened in the future (p3's report4 found the GUI
    showing exactly that), and the logical tick is kept beside it as
    `logical_at` so an accelerated sitting stays readable afterwards.
    """
    logical = None if real_now is None else now
    stamp = format_time(now if real_now is None else real_now)
    schedule = load_schedule(path)
    removed = prune_old_events(schedule, now)
    if removed:
        atomic_write(path, schedule)
        after_prune(removed)

    fired = []
    for event in due_events(schedule, now):
        event["fired_at"] = stamp
        if logical is not None:
            event["logical_at"] = format_time(logical)
        atomic_write(path, schedule)
        before_action(event["id"])
        if event["kind"] == "fire":
            fire(event["routine"])
        else:
            decide(event["id"], event["ask"])
        after_action(event["id"])
        fired.append(event["id"])
    return fired


def git_environment() -> dict[str, str]:
    env = dict(os.environ)
    token_path = Path(os.environ.get("RTSCHEDULE_GITEA_TOKEN_FILE", DEFAULT_GITEA_TOKEN))
    try:
        token = token_path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise DispatchError(f"cannot read Gitea token file {token_path}: {error}") from error
    if not token:
        raise DispatchError(f"Gitea token file is empty: {token_path}")
    env.update(
        GIT_ASKPASS=str(Path(os.environ.get("RTSCHEDULE_GITEA_ASKPASS", DEFAULT_GITEA_ASKPASS))),
        GIT_TERMINAL_PROMPT="0",
        AUTOLAB_GITEA_TOKEN_VALUE=token,
    )
    return env


def run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    try:
        completed = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)
    except OSError as error:
        raise DispatchError(f"cannot run {command[0]}: {error}") from error
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()[:500]
        raise DispatchError(f"{' '.join(command)} failed ({completed.returncode}): {detail}")


def git(repo: Path, *arguments: str, env: dict[str, str]) -> None:
    run(["git", *arguments], cwd=repo, env=env)


def commit(repo: Path, message: str, env: dict[str, str]) -> None:
    git(repo, "add", "schedule.json", env=env)
    git(
        repo,
        "-c", "user.name=routine-dispatcher",
        "-c", "user.email=routine-dispatcher@agdev.invalid",
        "commit", "-m", message,
        env=env,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(os.environ.get("RTSCHEDULE_REPO", DEFAULT_REPO)))
    parser.add_argument("--now", help="UTC test override (ISO-8601); omit in service use")
    args = parser.parse_args(argv)

    repo = args.repo.resolve()
    schedule_path = repo / "schedule.json"
    logical = parse_time(args.now, "--now") if args.now else None
    now = logical if logical is not None else utc_now()
    try:
        env = git_environment()
        agentchat = Path(os.environ.get("AGENTCHAT", DEFAULT_AGENTCHAT))
        trigger = Path(os.environ.get("ROUTINE_TRIGGER", DEFAULT_TRIGGER))
        zulip_env = str(Path(os.environ.get("AGENTCHAT_ZULIP_ENV", DEFAULT_ZULIP_ENV)))
        git(repo, "pull", "--rebase", env=env)

        def mark(event_id: str) -> None:
            commit(repo, f"Mark schedule event {event_id} fired", env)
            print(f"{format_time(now)} marked {event_id} before action", flush=True)

        def fire(routine: str) -> None:
            run([str(trigger), routine], env={**env, "AGENTCHAT_ZULIP_ENV": zulip_env})

        def decide(event_id: str, ask: str) -> None:
            text = f"Schedule decide event `{event_id}`.\n\n{ask}\n\nSchedule: {SCHEDULE_POINTER}."
            action_env = {**env, "AGENTCHAT_ZULIP_ENV": zulip_env}
            action_env.pop("AGENTCHAT_HOME", None)
            run([str(agentchat), "send", "front", "front-schedule", text], env=action_env)

        def pushed(event_id: str) -> None:
            git(repo, "push", "origin", "HEAD:main", env=env)
            print(f"{format_time(now)} dispatched and pushed {event_id}", flush=True)

        def pruned(event_ids: list[str]) -> None:
            commit(repo, f"Prune {len(event_ids)} schedule events older than 7 days", env)
            git(repo, "push", "origin", "HEAD:main", env=env)
            print(f"{format_time(now)} pruned {','.join(event_ids)}", flush=True)

        fired = dispatch_schedule(
            schedule_path,
            now,
            real_now=utc_now() if logical is not None else None,
            before_action=mark,
            fire=fire,
            decide=decide,
            after_action=pushed,
            after_prune=pruned,
        )
        # Flush a marker left by a previous crash after its external action.
        # It is already in local history, so this never repeats that action.
        git(repo, "push", "origin", "HEAD:main", env=env)
        if not fired:
            print(f"{format_time(now)} no due events", flush=True)
        return 0
    except DispatchError as error:
        print(f"{format_time(now)} dispatch failed: {error}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
