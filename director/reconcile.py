#!/usr/bin/env python3
"""Deliver a manifest asset, with the director making every judgment call.

The flow is the same as it always was — compose, ask agforge, download,
look at the file, decide — but the decisions moved. This module used to
abort a run when the delivered PNG was the wrong size and used to stop
after exactly two attempts. Both were harness clamps in front of the agent
(review1.md, E3 table, class (b)), and both are gone: the file inspection
is now an *observation handed to the director*, and how many attempts to
make is the director's call, made one attempt at a time.

What remains in the harness is mechanism, not judgment: HTTP to agforge,
downloading bytes, copying the accepted file into place, and flipping one
manifest entry. Plus one cost bound — `--attempt-budget` — which exists to
stop an unattended loop from spending forever, not to say when the work is
good enough. When it bites, it is recorded as the harness stopping the
director, and that is a fact worth having in the record.

Every director run here goes through the same `answer()` entrance a human
reaches over HTTP. reconcile is a caller of the window, not a second door.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import director

POLL_SECONDS = 3
GENERATION_TIMEOUT_SECONDS = 300
DEFAULT_ATTEMPT_BUDGET = 5

DECISION_LINE = re.compile(
    r"^\s*DECISION:\s*(deliver|retry|stop)\b[\s\-—:]*(.*)$", re.IGNORECASE | re.MULTILINE
)


class ReconcileError(Exception):
    """The mechanical part of the flow failed. Judgment failures are not this."""


# --- agforge mechanics ---------------------------------------------------


def http_json(url: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        raise ReconcileError(f"agforge request failed: {error}") from error
    if not isinstance(result, dict):
        raise ReconcileError("agforge returned a non-object response")
    return result


def request_image(base_url: str, desire: str) -> tuple[str, str]:
    created = http_json(f"{base_url.rstrip('/')}/api/requests", {"desire": desire})
    request_id = created.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise ReconcileError("agforge create response has no request id")
    deadline = time.monotonic() + GENERATION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        status = http_json(f"{base_url.rstrip('/')}/api/requests/{request_id}")
        state = status.get("status")
        if state == "done":
            artifacts = status.get("artifacts")
            images = [
                a for a in artifacts or [] if isinstance(a, dict) and a.get("kind") == "image"
            ]
            if not images or not isinstance(images[0].get("url"), str):
                raise ReconcileError(f"agforge job {request_id} returned no image URL")
            return request_id, images[0]["url"]
        if state == "failed":
            raise ReconcileError(
                f"agforge job {request_id} failed: {status.get('detail') or 'unknown failure'}"
            )
        if state not in ("queued", "running", "working"):
            raise ReconcileError(f"agforge job {request_id} has unknown status {state!r}")
        time.sleep(POLL_SECONDS)
    raise ReconcileError(f"agforge job {request_id} exceeded {GENERATION_TIMEOUT_SECONDS}s")


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as out:
            shutil.copyfileobj(response, out)
        temporary.replace(destination)
    except (OSError, urllib.error.URLError) as error:
        temporary.unlink(missing_ok=True)
        raise ReconcileError(f"could not download generated image: {error}") from error


# --- manifest mechanics --------------------------------------------------


def set_delivered(manifest: Path, request_id: str) -> str | None:
    """Flip exactly one entry to `delivered`, returning its previous status.

    The previous status is returned rather than enforced: re-delivering an
    entry is the director's business, and the record says what changed.
    """
    document = json.loads(manifest.read_text(encoding="utf-8"))
    previous = None
    changed = 0
    for request in document.get("requests", []):
        if isinstance(request, dict) and request.get("id") == request_id:
            previous = request.get("status")
            request["status"] = "delivered"
            changed += 1
    if changed != 1:
        raise ReconcileError(f"manifest did not contain exactly one request {request_id!r}")
    temporary = manifest.with_suffix(manifest.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    temporary.replace(manifest)
    return previous


def persist_envelopes(direction: Path, request_id: str, payload: dict) -> Path:
    """Write the full evidence for one request atomically, after every step,
    so partial evidence survives any later failure — a parent episode lost a
    successful envelope exactly this way."""
    path = direction / "reviews" / f"{request_id}.envelopes.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    temporary.replace(path)
    return path


def write_review(path: Path, desire: str, attempts: list[dict], verdict: str) -> None:
    lines = [
        "# Asset review",
        "",
        f"- Verdict: **{verdict}**",
        f"- Desire: {desire}",
        "",
        "## Attempts",
        "",
    ]
    for attempt in attempts:
        lines += [
            f"### Attempt {attempt['attempt']}",
            "",
            f"- agforge request id: `{attempt.get('agforge_request_id', 'not created')}`",
            f"- Observed: {attempt.get('observed', 'n/a')}",
            f"- Director decision: {attempt.get('decision', 'none')}",
            f"- Reason: {attempt.get('reason', 'n/a')}",
            "",
        ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


# --- talking to the director ---------------------------------------------


def parse_decision(reply: str) -> tuple[str | None, str]:
    matches = list(DECISION_LINE.finditer(reply))
    if not matches:
        return None, ""
    last = matches[-1]
    return last.group(1).lower(), last.group(2).strip()


def ask(workspace: director.Workspace, text: str, extra: dict) -> dict:
    record = director.answer(text, workspace, extra)
    if record["outcome"] != "done":
        raise ReconcileError(f"director unreachable: {record.get('failure')}")
    return record


COMPOSE_MESSAGE = """I need a generation request for one asset in the game's
manifest: `{request_id}`. Its manifest entry is in your workspace context.

Write the request you want sent to agforge, our image-generation agent. It
takes one free-text desire and nothing else, so anything that matters —
subject, mood, and any technical thing you care about such as size or
format — has to be in the words. Say it the way you would say it to an
illustrator you trust.

Reply with the request itself and nothing else: no preamble, no quotes, no
explanation. Do not write a VERDICT line.
"""

REVIEW_MESSAGE = """Attempt {attempt} of the `{request_id}` asset came back.
Here is what I can tell you about the file, and what the manifest said it
wanted:

{observation}

The file is on disk at:
{path}

Look at it if you can (you have Read), and tell me what to do. The last line
of your reply must be exactly one of:

    DECISION: deliver — <short reason>
    DECISION: retry — <what you want different next time>
    DECISION: stop — <short reason>

`deliver` copies this file into the game and marks the manifest entry
delivered. `retry` generates again — if you choose it, say in your reply
what the next request should emphasise, in your own words, and I will send
that. `stop` leaves it for a human. Nothing here overrides you; the size and
format notes above are observations, not rules — if the difference does not
matter to you, deliver it anyway.
"""

RETRY_MESSAGE = """You asked to retry the `{request_id}` asset and said:

{reason}

Write the new request for agforge — the whole thing, not a diff. Same rules
as before: one free-text desire, everything that matters in the words, no
preamble and no VERDICT line.
"""


def failure_message(request_id: str, attempt: int, error: str) -> str:
    return f"""Attempt {attempt} of the `{request_id}` asset did not produce a
file at all. What went wrong, verbatim:

{error}

That is the whole of what I know. Tell me what to do — the last line of your
reply must be exactly one of:

    DECISION: retry — <what you want different next time>
    DECISION: stop — <short reason>

There is nothing to deliver, so `deliver` is not available this time.
"""


def observe(path: Path, request: dict) -> dict:
    inspected = director.inspect_image(path)
    return {
        "file": inspected,
        "manifest_wants": {
            k: request.get(k) for k in ("format", "width", "height") if k in request
        },
        "differences": director.compare_to_manifest(inspected, request),
    }


# --- the flow ------------------------------------------------------------


def reconcile(
    direction_path: Path,
    manifest_path: Path,
    request_id: str,
    agforge_url: str,
    attempt_budget: int = DEFAULT_ATTEMPT_BUDGET,
) -> dict:
    workspace = director.load_workspace(direction_path, manifest_path)
    request = director.manifest_request(workspace, request_id)

    composed = ask(
        workspace,
        COMPOSE_MESSAGE.format(request_id=request_id),
        {"purpose": "compose", "request_id": request_id, "manifest_entry": request},
    )
    desire = composed["reply"].strip()
    # Advisory only (roadmap p3 step 3): the harness notes when the composed
    # desire omits something the manifest declared, and sends it anyway. This
    # is the assertion that used to abort the run, demoted to a note.
    advisories: list[str] = []
    for key in ("width", "height", "format"):
        value = request.get(key)
        if value is not None and str(value).lower() not in desire.lower():
            advisories.append(f"composed desire does not mention {key} {value}")

    suffix = "." + str(request.get("format", "png")).lower()
    candidate = workspace.direction / "candidates" / f"{request_id}{suffix}"
    attempts: list[dict] = []
    evidence = {
        "request": request_id,
        "desire": desire,
        "compose_record": composed["id"],
        "compose_advisories": advisories,
        "attempts": attempts,
        "verdict": "in_progress",
    }
    persist_envelopes(workspace.direction, request_id, evidence)

    verdict = "stopped"
    for attempt_number in range(1, attempt_budget + 1):
        entry: dict = {"attempt": attempt_number, "desire": desire}
        attempts.append(entry)
        try:
            agforge_id, url = request_image(agforge_url, desire)
            entry["agforge_request_id"] = agforge_id
            download(url, candidate)
        except ReconcileError as error:
            # A failed generation is not the end of the run: the director is
            # told what happened, in the failing party's own words, and says
            # whether to go again. That is the harvest loop, not a clamp.
            entry["observed"] = f"generation failed: {error}"
            persist_envelopes(workspace.direction, request_id, evidence)
            record = ask(
                workspace,
                failure_message(request_id, attempt_number, str(error)),
                {"purpose": "review-failure", "request_id": request_id},
            )
            decision, reason = parse_decision(record["reply"])
            entry.update(
                director_record=record["id"],
                decision=decision or "stop (no decision line)",
                reason=reason or record["reply"][:300],
            )
            persist_envelopes(workspace.direction, request_id, evidence)
            if decision == "retry":
                desire = ask(
                    workspace,
                    RETRY_MESSAGE.format(request_id=request_id, reason=reason or record["reply"]),
                    {"purpose": "recompose", "request_id": request_id},
                )["reply"].strip()
                continue
            verdict = "stopped after a generation failure"
            break

        observation = observe(candidate, request)
        entry["observed"] = json.dumps(observation["file"], ensure_ascii=False)
        entry["differences"] = observation["differences"]
        persist_envelopes(workspace.direction, request_id, evidence)

        record = ask(
            workspace,
            REVIEW_MESSAGE.format(
                attempt=attempt_number,
                request_id=request_id,
                observation=json.dumps(observation, indent=2, ensure_ascii=False),
                path=candidate,
            ),
            {"purpose": "review", "request_id": request_id, "observation": observation},
        )
        decision, reason = parse_decision(record["reply"])
        entry.update(
            director_record=record["id"],
            decision=decision or "stop (no decision line)",
            reason=reason or record["reply"][:300],
        )
        persist_envelopes(workspace.direction, request_id, evidence)

        if decision == "deliver":
            destination = director.asset_path(workspace, request)
            if destination is None:
                raise ReconcileError("manifest entry has no usable asset path")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidate, destination)
            entry["delivered_to"] = str(destination)
            entry["previous_status"] = set_delivered(workspace.manifest, request_id)
            verdict = "delivered"
            break
        if decision == "retry":
            desire = ask(
                workspace,
                RETRY_MESSAGE.format(request_id=request_id, reason=reason or record["reply"]),
                {"purpose": "recompose", "request_id": request_id},
            )["reply"].strip()
            continue
        verdict = "stopped by the director" if decision == "stop" else "stopped: no decision line"
        break
    else:
        # Not a judgment: the harness ran out of the money it was allowed to
        # spend while the director still wanted to keep going.
        verdict = f"attempt budget of {attempt_budget} exhausted while the director wanted to retry"

    evidence["verdict"] = verdict
    persist_envelopes(workspace.direction, request_id, evidence)
    write_review(workspace.direction / "reviews" / f"{request_id}.md", desire, attempts, verdict)
    return evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--direction", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--agforge-url", required=True)
    parser.add_argument(
        "--attempt-budget",
        type=int,
        default=DEFAULT_ATTEMPT_BUDGET,
        help="cost bound, not a quality gate: how many generations this run may pay for",
    )
    args = parser.parse_args(argv)
    try:
        result = reconcile(
            args.direction, args.manifest, args.request_id, args.agforge_url, args.attempt_budget
        )
    except (director.DirectorError, ReconcileError) as error:
        print(f"asset reconcile: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["verdict"] == "delivered" else 2


if __name__ == "__main__":
    raise SystemExit(main())
