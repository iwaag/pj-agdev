from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "dispatch.py"
SPEC = importlib.util.spec_from_file_location("routine_dispatch", MODULE_PATH)
assert SPEC and SPEC.loader
dispatch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dispatch)


def test_due_not_due_expired_and_already_fired(tmp_path):
    path = tmp_path / "schedule.json"
    path.write_text(
        json.dumps(
            {
                "requests": [
                    {
                        "id": "active",
                        "said_at": "2026-08-25T08:00:00Z",
                        "until": "2026-08-25T12:00:00Z",
                        "by": "developer",
                        "text": "active request",
                    },
                    {
                        "id": "expired",
                        "said_at": "2026-08-25T07:00:00Z",
                        "until": "2026-08-25T08:30:00Z",
                        "by": "developer",
                        "text": "expired request",
                    },
                ],
                "events": [
                    {"id": "due-fire", "at": "2026-08-25T08:55:00Z", "kind": "fire", "routine": "rtnotes", "from": "active", "fired_at": None},
                    {"id": "due-decide", "at": "2026-08-25T08:56:00Z", "kind": "decide", "ask": "Did it work?", "from": "active", "fired_at": None},
                    {"id": "future", "at": "2026-08-25T09:05:00Z", "kind": "fire", "routine": "imgprompt", "from": "active", "fired_at": None},
                    {"id": "expired", "at": "2026-08-25T08:40:00Z", "kind": "fire", "routine": "imgprompt", "from": "expired", "fired_at": None},
                    {"id": "already", "at": "2026-08-25T08:30:00Z", "kind": "fire", "routine": "imgprompt", "from": "active", "fired_at": "2026-08-25T08:31:00Z"},
                ],
            }
        ),
        encoding="utf-8",
    )
    calls = []
    now = datetime(2026, 8, 25, 9, tzinfo=timezone.utc)

    fired = dispatch.dispatch_schedule(
        path,
        now,
        before_action=lambda event_id: calls.append(("marked", event_id, json.loads(path.read_text())["events"])),
        fire=lambda routine: calls.append(("fire", routine)),
        decide=lambda event_id, ask: calls.append(("decide", event_id, ask)),
        after_action=lambda event_id: calls.append(("pushed", event_id)),
        after_prune=lambda event_ids: calls.append(("pruned", event_ids)),
    )

    assert fired == ["due-fire", "due-decide"]
    assert [(call[0], call[1]) for call in calls if call[0] in {"fire", "decide"}] == [
        ("fire", "rtnotes"),
        ("decide", "due-decide"),
    ]
    marked = [call for call in calls if call[0] == "marked"]
    assert marked[0][2][0]["fired_at"] == "2026-08-25T09:00:00Z"
    assert [call[:2] for call in calls if call[0] in {"marked", "pushed"}] == [
        ("marked", "due-fire"), ("pushed", "due-fire"),
        ("marked", "due-decide"), ("pushed", "due-decide"),
    ]
    result = json.loads(path.read_text())
    assert result["events"][2]["fired_at"] is None
    assert result["events"][3]["fired_at"] is None
    assert result["events"][4]["fired_at"] == "2026-08-25T08:31:00Z"


def test_a_logical_tick_records_the_real_time_and_the_logical_one(tmp_path):
    """`--now` advances the clock for what is due; it must not make the record
    claim the action happened at that time. p3's GUI showed fires in the
    future because it did."""
    path = tmp_path / "schedule.json"
    path.write_text(
        json.dumps(
            {
                "requests": [
                    {"id": "r1", "said_at": "2026-08-25T08:00:00Z", "until": "2026-09-01T00:00:00Z",
                     "by": "developer", "text": "daily papers"},
                ],
                "events": [
                    {"id": "e1", "at": "2026-08-30T09:00:00Z", "kind": "fire", "routine": "papers",
                     "from": "r1", "fired_at": None},
                ],
            }
        ),
        encoding="utf-8",
    )

    fired = dispatch.dispatch_schedule(
        path,
        datetime(2026, 8, 30, 9, tzinfo=timezone.utc),
        real_now=datetime(2026, 8, 25, 5, 30, tzinfo=timezone.utc),
        before_action=lambda _event_id: None,
        fire=lambda _routine: None,
        decide=lambda _event_id, _ask: None,
        after_action=lambda _event_id: None,
        after_prune=lambda _event_ids: None,
    )

    assert fired == ["e1"]
    event = json.loads(path.read_text())["events"][0]
    assert event["fired_at"] == "2026-08-25T05:30:00Z"
    assert event["logical_at"] == "2026-08-30T09:00:00Z"
    # And the schedule still validates with the new field present.
    dispatch.load_schedule(path)


def test_a_real_tick_records_no_logical_time(tmp_path):
    """Production has one clock, so there is nothing to keep beside it."""
    path = tmp_path / "schedule.json"
    path.write_text(
        json.dumps(
            {
                "requests": [
                    {"id": "r1", "said_at": "2026-08-25T08:00:00Z", "until": "2026-08-25T12:00:00Z",
                     "by": "developer", "text": "daily papers"},
                ],
                "events": [
                    {"id": "e1", "at": "2026-08-25T09:00:00Z", "kind": "fire", "routine": "papers",
                     "from": "r1", "fired_at": None},
                ],
            }
        ),
        encoding="utf-8",
    )

    dispatch.dispatch_schedule(
        path,
        datetime(2026, 8, 25, 9, 3, tzinfo=timezone.utc),
        before_action=lambda _event_id: None,
        fire=lambda _routine: None,
        decide=lambda _event_id, _ask: None,
        after_action=lambda _event_id: None,
        after_prune=lambda _event_ids: None,
    )

    event = json.loads(path.read_text())["events"][0]
    assert event["fired_at"] == "2026-08-25T09:03:00Z"
    assert "logical_at" not in event


def test_events_older_than_seven_days_are_pruned(tmp_path):
    path = tmp_path / "schedule.json"
    path.write_text(
        json.dumps(
            {
                "requests": [{"id": "r1", "said_at": "2026-08-01T00:00:00Z", "until": "2026-09-01T00:00:00Z", "text": "keep"}],
                "events": [
                    {"id": "old", "at": "2026-08-17T23:59:59Z", "kind": "fire", "routine": "rtnotes", "from": "r1", "fired_at": "2026-08-18T00:00:00Z"},
                    {"id": "edge", "at": "2026-08-18T00:00:00Z", "kind": "fire", "routine": "rtnotes", "from": "r1", "fired_at": "2026-08-18T00:00:00Z"},
                ],
            }
        ),
        encoding="utf-8",
    )
    pruned = []
    dispatch.dispatch_schedule(
        path,
        datetime(2026, 8, 25, tzinfo=timezone.utc),
        before_action=lambda _event_id: None,
        fire=lambda _routine: None,
        decide=lambda _event_id, _ask: None,
        after_action=lambda _event_id: None,
        after_prune=lambda event_ids: pruned.extend(event_ids),
    )
    assert pruned == ["old"]
    assert [event["id"] for event in json.loads(path.read_text())["events"]] == ["edge"]
