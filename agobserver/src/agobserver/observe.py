"""One short evaluation of one watch.

An evaluation gets four things and nothing else: the accepted request, the
previous observation, whatever evidence it gathers itself, and the observe
guide. It does **not** get the watch topic's chatlog, this agent's other
watches, the realm, or any development guide. That is not economy — a local
model's accuracy falls off a cliff when the prompt carries material that
does not bear on the question, and everything above is material that does
not bear on the question.

The answer is three-valued on purpose. `met` and `not_met` are judgments
about the world; `unable` is a statement about the *look*, and keeping it
separate is what stops a target that cannot be read from being reported
forever as a condition that has not held yet.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agag.agent import AgentSpec, run_role
from agag.topics import (
    generation_dir,
    guide,
    next_generation,
    next_record_path,
    prompt_with_guide,
    topic_workspace,
)

from . import anchor

ROLE = "observe"
GUIDES = Path(__file__).resolve().parents[2] / "agent" / "guides"
RESULT_FILE = "result.json"

MET = "met"
NOT_MET = "not_met"
UNABLE = "unable"
VERDICTS = (MET, NOT_MET, UNABLE)

#: The wall-clock bound on one evaluation. An unreachable target or a model
#: that has stopped making progress must not hold the worker: with sequential
#: evaluation, one stuck watch is every watch stopped.
TIMEOUT_SECONDS = 180.0
#: Handed to agcode so it reports its own deadline as a result document
#: instead of being killed mid-turn with nothing to show for it.
DEADLINE_MARGIN_SECONDS = 20.0
MAX_TURNS = 12
#: How much of a long evidence string survives into the record and the
#: notification. Enough to quote a line; not enough to paste a log.
EVIDENCE_LIMIT = 1200

__all__ = ["MET", "NOT_MET", "UNABLE", "Observation", "evaluate", "observe_prompt"]


@dataclass(frozen=True)
class Observation:
    """One evaluation's answer."""

    verdict: str
    evidence: str = ""
    duration_ms: int = 0
    #: Set when the run itself failed rather than the target being unreadable.
    error: str = ""

    @property
    def met(self) -> bool:
        return self.verdict == MET

    @property
    def looked(self) -> bool:
        """Whether this was an observation at all, as opposed to a failure."""
        return self.verdict in (MET, NOT_MET)

    def as_record(self, at: str) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "evidence": self.evidence,
            "at": at,
            "duration_ms": self.duration_ms,
            **({"error": self.error} if self.error else {}),
        }


def observe_prompt(watch: anchor.Watch, previous: dict[str, Any] | None) -> str:
    """The whole prompt: the request, the last answer, then the guide."""
    lines = [
        f"Watch `{watch.name}`. Decide whether this condition holds right now.",
        "",
        f"Condition: {watch.condition}",
        f"What to look at: {watch.target or '(not stated — read it from the condition)'}",
    ]
    if previous:
        verdict = previous.get("verdict", "")
        evidence = str(previous.get("evidence", ""))[:EVIDENCE_LIMIT]
        lines += [
            "",
            "Your previous observation of this same watch:",
            f"  at {previous.get('at', 'an earlier time')} you answered "
            f"{verdict!r} — {evidence}",
        ]
    else:
        lines += ["", "You have not looked at this watch before."]
    return prompt_with_guide(lines, guide(GUIDES, ROLE, "guide.md"))


def _result(workspace: Path, output: str) -> dict[str, Any]:
    path = workspace / RESULT_FILE
    for text in (path.read_text(encoding="utf-8") if path.is_file() else "", output):
        for candidate in _json_candidates(text):
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and parsed.get("verdict") in VERDICTS:
                return parsed
    return {}


def _json_candidates(text: str):
    stripped = (text or "").strip()
    if not stripped:
        return
    yield stripped
    parts = stripped.split("```")
    for index in range(1, len(parts), 2):
        block = parts[index]
        yield block.split("\n", 1)[1] if block.lstrip().lower().startswith("json") else block


def evaluate(spec: AgentSpec, watch: anchor.Watch, previous: dict[str, Any] | None) -> Observation:
    """Look once. Never raises: a failed look is an answer, not an exception.

    Every way this can go wrong — the harness exiting non-zero, the deadline,
    a model that wrote no readable verdict — comes back as `unable` with the
    reason. The caller schedules the next interval either way, and a watch is
    never lost because one look failed.
    """
    workspace_root = topic_workspace(spec.topics_root, watch.channel, watch.topic)
    workspace = generation_dir(
        spec.topics_root, watch.channel, watch.topic,
        next_generation(workspace_root), ROLE,
    )
    try:
        output, record, exit_code = run_role(
            spec, ROLE, observe_prompt(watch, previous),
            cwd=workspace,
            timeout=TIMEOUT_SECONDS,
            record=next_record_path(spec.records_root / ROLE),
            transcript=workspace / "transcript.jsonl",
            stream=True,
            # No `home`: an evaluation has no conversation and must not be
            # able to speak in one. The guide says so too, but the reason it
            # is true is that nothing here hands it one.
            extra_args=[
                "--max-turns", str(MAX_TURNS),
                "--deadline-s", str(TIMEOUT_SECONDS - DEADLINE_MARGIN_SECONDS),
            ],
            extra_meta={"watch": watch.name},
        )
    except Exception as error:  # noqa: BLE001 - a failed look is an answer
        return Observation(UNABLE, evidence=f"the evaluation could not run: {error}", error=str(error))
    duration = int(record.get("duration_ms") or 0)
    if exit_code != 0:
        return Observation(
            UNABLE,
            evidence=f"the evaluation ended with exit code {exit_code}: {output.strip()[:300]}",
            duration_ms=duration,
            error=f"exit {exit_code}",
        )
    parsed = _result(workspace, output)
    if not parsed:
        return Observation(
            UNABLE,
            evidence="the evaluation produced no verdict",
            duration_ms=duration,
            error="no verdict",
        )
    return Observation(
        verdict=str(parsed["verdict"]),
        evidence=" ".join(str(parsed.get("evidence") or "").split())[:EVIDENCE_LIMIT],
        duration_ms=duration,
    )
