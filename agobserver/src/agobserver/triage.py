"""One judgment about one stall candidate, on this host's model.

`robust_workflow` p1 step 4. `agag.trace.stall_candidates` decides in code
what records can decide. Two kinds it cannot: a ✔ on a conversation whose
work is still live (a correction, or the p3 mistake?) and a long silence
while executing (a long job, or a worker that died?). Those need somebody to
read the conversation, and that is this: the candidate, the trace, the last
messages of the conversation in question, the guide — and one answer,
`stall`, `legit` or `unclear`, with the evidence it rests on.

Like `observe`, it is given nothing else, and like `observe` a run that fails
is an answer (`unclear`), never an exception: the monitor asks again, and
after `MAX_UNCLEAR` the human decides.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agag.agent import AgentSpec, run_role
from agag.selfnote import is_speech
from agag.topics import generation_dir, guide, next_generation, next_record_path, prompt_with_guide, topic_workspace

ROLE = "triage"
GUIDES = Path(__file__).resolve().parents[2] / "agent" / "guides"
RESULT_FILE = "result.json"
VERDICTS = ("stall", "legit", "unclear")
TIMEOUT_SECONDS = 150.0
DEADLINE_MARGIN_SECONDS = 20.0
MAX_TURNS = 6
LINE_LIMIT = 600
#: How many of the request's own conversation's newest posts a judgment
#: reads beside the stalled conversation (robust_workflow p3 step 6).
HOME_MESSAGES = 6
PROMPT_FILE = "prompt.md"
INPUT_FILE = "input.json"

__all__ = ["judge", "triage_prompt"]


def _clip(text: str) -> str:
    """At most `LINE_LIMIT` characters, keeping the beginning **and the
    end**: a report or a relay ends with its question ("Do you accept task
    1?"), and a cut that kept only the head dropped exactly that
    (robust_workflow p3 step 6, trial C)."""
    if len(text) <= LINE_LIMIT:
        return text
    half = (LINE_LIMIT - 5) // 2
    return f"{text[:half]} […] {text[-half:]}"


def _lines(messages: list[dict]) -> list[str]:
    lines = []
    for message in messages:
        if not is_speech(message):
            continue
        text = _clip(" ".join(str(message.get("content") or "").split()))
        lines.append(f"[{message.get('sender_full_name')} #{message.get('id')}] {text}")
    return lines


def triage_prompt(candidate, trace_text: str, tail: list[dict], home: list[dict] | None = None,
                  home_name: str = "") -> str:
    lines = [
        f"A possible stall, kind `{candidate.kind}`, in `#{candidate.channel} › {candidate.topic}`"
        + (f" ({candidate.identity})" if candidate.identity else "") + ".",
        "",
        f"What the records show: {candidate.fact}",
        f"What would happen next if nothing is wrong: {candidate.next_action}",
        "",
        "The request as traced (every conversation opened for it, and its state):",
        "",
        trace_text,
        "",
        "The last messages of that conversation, oldest first:",
        "",
    ]
    lines.extend(_lines(tail))
    if home:
        # Where the request came from — the requester and the person who
        # decides speak here. Without it a judgment of a ✔ on work that waits
        # for somebody's decision saw only "answered 2m ago" in the trace, and
        # not that the question had been put to the human (p3 step 5, C:
        # judged a stall twice, one needless request).
        lines += ["", f"The newest messages of the request's own conversation ({home_name}), oldest first:", ""]
        from agag.agent import is_ack

        spoken = [m for m in home if is_speech(m) and not is_ack(str(m.get("content") or "").strip())]
        lines.extend(_lines(spoken[-HOME_MESSAGES:]))
    return prompt_with_guide(lines, guide(GUIDES, ROLE, "guide.md"))


def _parse(workspace: Path, output: str) -> dict[str, Any]:
    path = workspace / RESULT_FILE
    for text in (path.read_text(encoding="utf-8") if path.is_file() else "", output):
        stripped = (text or "").strip()
        candidates = [stripped] + [
            block.split("\n", 1)[1] if block.lstrip().lower().startswith("json") else block
            for block in stripped.split("```")[1::2]
        ]
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and parsed.get("verdict") in VERDICTS:
                return parsed
    return {}


def judge(spec: AgentSpec, candidate, trace_text: str, tail: list[dict], incident: str, *,
          home: list[dict] | None = None, home_name: str = "", snapshot: str = "") -> dict[str, str]:
    """`{"verdict": stall|legit|unclear, "evidence": …}`. Never raises.

    The exact prompt and what it was built from are kept in the workspace
    (`prompt.md`, `input.json`) beside the transcript, so a verdict can be
    re-asked on the same input — of this model or another (p3 step 6)."""
    workspace = generation_dir(spec.topics_root, spec.instance_name(), incident,
                               next_generation(topic_workspace(spec.topics_root, spec.instance_name(), incident)),
                               ROLE)
    prompt = triage_prompt(candidate, trace_text, tail, home, home_name)
    try:
        (workspace / PROMPT_FILE).write_text(prompt, encoding="utf-8")
        (workspace / INPUT_FILE).write_text(json.dumps({
            "incident": incident, "snapshot": snapshot,
            "candidate": {"kind": candidate.kind, "channel": candidate.channel, "topic": candidate.topic,
                          "identity": candidate.identity, "fact": candidate.fact,
                          "next_action": candidate.next_action, "since": candidate.since,
                          "evidence": list(candidate.evidence), "anchor": candidate.anchor},
            "trace": trace_text, "tail": tail, "home": home or [], "home_name": home_name,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass  # the judgment does not depend on its own record
    try:
        output, record, exit_code = run_role(
            spec, ROLE, prompt,
            cwd=workspace, timeout=TIMEOUT_SECONDS,
            record=next_record_path(spec.records_root / ROLE),
            transcript=workspace / "transcript.jsonl", stream=True,
            extra_args=["--max-turns", str(MAX_TURNS), "--deadline-s", str(TIMEOUT_SECONDS - DEADLINE_MARGIN_SECONDS)],
            extra_meta={"incident": incident},
        )
    except Exception as error:  # noqa: BLE001 - a failed judgment is an answer
        return {"verdict": "unclear", "evidence": f"the judgment could not run: {error}"}
    if exit_code != 0:
        return {"verdict": "unclear", "evidence": f"the judgment ended with exit code {exit_code}"}
    parsed = _parse(workspace, output)
    if not parsed:
        return {"verdict": "unclear", "evidence": "the judgment produced no verdict"}
    return {"verdict": str(parsed["verdict"]), "evidence": " ".join(str(parsed.get("evidence") or "").split())[:800]}
