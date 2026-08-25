from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
from pathlib import Path


ROUTINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROUTINE_DIR))
loader = importlib.machinery.SourceFileLoader("rtschedule_tool", str(ROUTINE_DIR / "rtschedule"))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec
rtschedule = importlib.util.module_from_spec(spec)
loader.exec_module(rtschedule)


def test_next_ids_ignore_descriptive_proof_ids():
    assert rtschedule.next_id([{"id": "r-step1"}, {"id": "r2"}], "r") == "r3"
    assert rtschedule.next_id([{"id": "e-manual"}], "e") == "e1"


def test_find_row_reports_the_missing_kind():
    try:
        rtschedule.find_row([], "e9", "event")
    except rtschedule.dispatch.DispatchError as error:
        assert str(error) == "unknown event id: e9"
    else:
        raise AssertionError("missing event was accepted")
