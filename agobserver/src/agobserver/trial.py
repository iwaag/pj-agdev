"""`python -m agobserver.trial <probe> --out <dir>` — one Observer triage of a
fixture probe (`agent_guide` p2 ex1; p2 step 7's driver).

`triage-unopened`: the probe's conversation on the fixture board is judged
as a stalled request would be — its trace, the last post as the fact, the
Developer responsible — by `triage.judge`, the call the monitor makes. The
verdict is the reply the probe's rule reads. Every run's `agentchat` reads
the fixture board. `--guides <tree>` or `--guides-rev <commit>` judges with
another `agent/guides` tree, `--dry-run` writes the prompt and runs no model.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from agag.fixture.run import Trial, client, newest, tool_calls, trial_parser

#: This checkout, where `--guides-rev` is looked up.
ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    args = trial_parser("python -m agobserver.trial", __doc__, "agobserver").parse_args(argv)
    trial = Trial.start(args, ROOT)
    from agag.trace import Candidate, trace, trace_lines

    from . import triage
    from .listener import SPEC

    if trial.guides is not None:
        triage.GUIDES = trial.guides
    probe = trial.probe
    board = client(trial.store)
    history = board.topic_history(probe.channel, probe.topic, 50)
    asked, root = history[-1], history[0]
    candidate = Candidate(kind="silent", channel=probe.channel, topic=probe.topic, identity="",
                          fact=f"the last post (#{asked['id']}) is autolab's question to the Developer, and nothing "
                               "has been posted since",
                          responsible="Developer", next_action="the Developer answers autolab's question",
                          since=int(asked["timestamp"]), evidence=(int(asked["id"]),), judgment=True,
                          anchor=int(root["id"]))
    incident = f"fixture-{probe.name}"
    with trial.session():
        verdict = triage.judge(SPEC, candidate, "\n".join(trace_lines(trace(board, int(root["id"])))), history,
                               incident)
    workspace = newest(SPEC.topics_root / SPEC.instance_name() / incident, "*")
    calls = tool_calls(workspace / triage.ROLE / "transcript.jsonl") if workspace is not None else []
    return trial.finish(json.dumps(verdict, ensure_ascii=False), records=SPEC.records_root / triage.ROLE,
                        role=triage.ROLE, verdict=verdict, calls=calls)


if __name__ == "__main__":
    sys.exit(main())
