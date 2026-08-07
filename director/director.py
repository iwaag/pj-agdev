#!/usr/bin/env python3
"""One-question director runner for isolated creative direction workspaces."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


MODEL = "claude-sonnet-5"
TIMEOUT_SECONDS = 180


class DirectorError(Exception):
    """A director question could not be answered safely or structurally."""


@dataclass(frozen=True)
class Context:
    direction: Path
    brief: str
    manifest: Path
    request: dict


def load_context(direction: Path, manifest: Path, request_id: str) -> Context:
    direction = direction.resolve()
    manifest = manifest.resolve()
    brief_path = direction / "brief.md"
    if not direction.is_dir() or not brief_path.is_file():
        raise DirectorError(f"direction workspace must contain brief.md: {direction}")
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DirectorError(f"could not read manifest: {error}") from error
    requests = document.get("requests") if isinstance(document, dict) else None
    if not isinstance(requests, list):
        raise DirectorError("manifest.requests must be an array")
    matches = [item for item in requests if isinstance(item, dict) and item.get("id") == request_id]
    if len(matches) != 1:
        raise DirectorError(f"manifest must contain exactly one request with id {request_id!r}")
    return Context(
        direction=direction,
        brief=brief_path.read_text(encoding="utf-8").strip(),
        manifest=manifest,
        request=matches[0],
    )


def run_question(context: Context, prompt: str, allow_read: bool = False) -> tuple[str, dict]:
    command = os.environ.get("DIRECTOR_CLAUDE_CMD", "claude")
    argv = [command, "-p", "--output-format", "json", "--model", MODEL]
    if allow_read:
        argv += ["--allowedTools", "Read"]
    try:
        process = subprocess.run(
            argv,
            cwd=context.direction,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise DirectorError(f"director timed out after {TIMEOUT_SECONDS}s") from error
    except OSError as error:
        raise DirectorError(f"could not launch director backend: {error}") from error
    if process.returncode != 0:
        tail = (process.stderr or process.stdout or "no output").strip().splitlines()
        raise DirectorError(
            f"director backend exited {process.returncode}: {tail[-1] if tail else 'no output'}"
        )
    try:
        outer = json.loads(process.stdout)
    except json.JSONDecodeError as error:
        raise DirectorError("director backend did not return its JSON envelope") from error
    if not isinstance(outer, dict) or not isinstance(outer.get("result"), str):
        raise DirectorError("director backend envelope has no result text")
    meta = {
        key: outer[key]
        for key in ("total_cost_usd", "duration_ms", "num_turns", "is_error")
        if key in outer
    }
    return outer["result"], meta


def parse_json_answer(answer: str) -> dict:
    cleaned = answer.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").removeprefix("json").strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise DirectorError(f"director answer is not JSON: {answer[:160]!r}") from error
    if not isinstance(value, dict):
        raise DirectorError("director answer must be a JSON object")
    return value


def compose(context: Context) -> tuple[dict, dict]:
    prompt = f"""You are the creative director for one game asset.
Use only the direction brief and manifest entry supplied below. Compose a
single desire-only request for an image-generation service. Preserve all
technical fields exactly, including dimensions and format, inside the desire
text. Return raw JSON only: {{"desire":"one concise generation desire"}}.

Direction brief:
{context.brief}

Manifest entry:
{json.dumps(context.request, ensure_ascii=False, indent=2)}
"""
    answer, meta = run_question(context, prompt)
    result = parse_json_answer(answer)
    desire = result.get("desire")
    if not isinstance(desire, str) or not desire.strip():
        raise DirectorError("compose answer has no non-empty desire")
    width = context.request.get("width")
    height = context.request.get("height")
    fmt = context.request.get("format")
    dimensions = f"{width}x{height}"
    if dimensions not in desire.replace("×", "x"):
        raise DirectorError(f"compose answer omitted exact dimensions {dimensions}")
    if isinstance(fmt, str) and fmt.lower() not in desire.lower():
        raise DirectorError(f"compose answer omitted format {fmt}")
    return {"desire": desire.strip()}, meta


def expected_asset_path(context: Context) -> Path:
    relative = context.request.get("path")
    if not isinstance(relative, str) or not relative:
        raise DirectorError("manifest request has no asset path")
    # assets/manifest.json is one directory below the game repository root.
    root = context.manifest.parent.parent
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as error:
        raise DirectorError("manifest asset path escapes the game repository") from error
    return candidate


def review(context: Context) -> tuple[dict, dict]:
    asset = expected_asset_path(context)
    if not asset.is_file():
        raise DirectorError(f"delivered asset does not exist: {asset}")
    prompt = f"""You are leniently reviewing one immature generated game asset.
Use the Read tool to inspect exactly this image: {asset}
Reject only a clear thematic failure. Answer raw JSON only:
{{"accepted":true_or_false,"reason":"one sentence"}}.

Direction brief:
{context.brief}

Manifest entry:
{json.dumps(context.request, ensure_ascii=False, indent=2)}
"""
    answer, meta = run_question(context, prompt, allow_read=True)
    result = parse_json_answer(answer)
    if not isinstance(result.get("accepted"), bool):
        raise DirectorError("review answer must contain boolean accepted")
    reason = result.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise DirectorError("review answer must contain a reason")
    return {"accepted": result["accepted"], "reason": reason.strip()}, meta


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("question", choices=("compose", "review"))
    result.add_argument("--direction", required=True, type=Path)
    result.add_argument("--manifest", required=True, type=Path)
    result.add_argument("--request-id", required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        context = load_context(args.direction, args.manifest, args.request_id)
        answer, meta = compose(context) if args.question == "compose" else review(context)
    except DirectorError as error:
        print(f"director: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"answer": answer, "meta": meta}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
