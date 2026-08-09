#!/usr/bin/env python3
"""The director: a creative-direction persona with one conversational entrance.

The director is an agent, not a function. Everything a caller wants — a
casual question about a character's voice, a pass/fail judgment on a
generated line, a composed generation desire, a verdict on a delivered
asset — enters through `answer(text)` (devpolicy/policy.md, Single
Entrance). `window.py` serves that entrance over HTTP; `main()` here is a
CLI wrapper on the same entrance, and `reconcile.py` calls it in-process.
Three transports, one place to express a desire.

The persona itself is not in this file. It is the markdown a human wrote in
the direction workspace (`brief.md`, `persona.md`, anything else ending in
`.md`), which is read fresh on every run — editing the persona never means
touching the harness.

The workspace is wide on purpose: the direction files, the game's manifest
and docs, and the delivered assets are all context, and on the claude
backend the persona also gets Read/Glob/Grep over the tree that contains
both. That is context placement, not a security sandbox.

There are no verification gates in front of the persona. `inspect_png` and
the manifest's declared dimensions are handed to it as *information*; what
to do about a mismatch is its judgment, not the harness's.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
GUIDE = HERE / "GUIDE.md"

# Creative judgment is the hard-task end of the spectrum, so the strong
# backend is the default here (roadmap p3 step 4) — the opposite default
# from autolab's window, by the same principle.
DEFAULT_BACKEND = "claude"
DEFAULT_MODELS = {"claude": "claude-sonnet-5", "ollama": "gemma3:latest"}
TIMEOUT_SECONDS = 240
MAX_TEXT = 8000
MAX_PERSONA_BYTES = 60000
CLAUDE_ALLOWED_TOOLS = "Read,Glob,Grep"

# A pass/fail request gets a machine-readable answer without needing a
# second endpoint: the persona ends such a reply with one marker line.
# Same shape as agforge's charter contract (`RESULT_URL:` / `RESULT_FAILED:`).
VERDICT_LINE = re.compile(r"^\s*VERDICT:\s*(pass|fail)\b[\s\-—:]*(.*)$", re.IGNORECASE | re.MULTILINE)


class DirectorError(Exception):
    """The director could not be reached or produced nothing. str() is the record."""


# --- config resolution ---------------------------------------------------
#
# Process env first, then `.local/.env` — agforge's service/agent_run.py
# resolution order, duplicated rather than shared on purpose (a library
# between these workspaces would couple them and buy nothing).


def local_env(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    try:
        lines = (ROOT / ".local" / ".env").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        line = line.strip()
        if line.startswith(f"{name}="):
            value = line.partition("=")[2].strip()
            if value:
                return value
    return None


def backend_name() -> str:
    backend = local_env("DIRECTOR_BACKEND") or DEFAULT_BACKEND
    if backend not in DEFAULT_MODELS:
        raise DirectorError(f"unknown DIRECTOR_BACKEND: {backend!r}")
    return backend


def backend_model(backend: str) -> str:
    return local_env("DIRECTOR_MODEL") or DEFAULT_MODELS[backend]


def newest_match(pattern: str) -> str | None:
    """Newest existing file matching a glob, or None.

    The claude pointer is usually an absolute path into a version-numbered
    editor-extension directory, which goes stale on every update and fails
    as `No such file or directory` — an infra-looking error with a config
    cause. It has already cost autolab two runs and agforge one; the
    resolver is here from the start rather than after a third occurrence.
    """
    matches = [p for p in glob.glob(pattern) if os.path.isfile(p)]
    return max(matches, key=lambda p: os.stat(p).st_mtime) if matches else None


def claude_bin() -> str:
    candidate = local_env("DIRECTOR_CLAUDE_CMD")
    if not candidate:
        return "claude"
    if any(ch in candidate for ch in "*?["):
        return newest_match(candidate) or candidate
    return candidate


# --- the workspace -------------------------------------------------------


@dataclass(frozen=True)
class Workspace:
    """Everything the director can see. A direction workspace is required;
    a manifest is optional — a casual creative question needs no game."""

    direction: Path
    persona: str
    manifest: Path | None = None
    manifest_doc: dict | None = None
    game_root: Path | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def context_root(self) -> Path:
        """The directory the backend runs in: wide enough to hold both the
        direction workspace and the game repo when there is one."""
        if self.game_root is None:
            return self.direction
        try:
            return Path(os.path.commonpath([self.direction, self.game_root]))
        except ValueError:
            return self.direction


def read_persona(direction: Path) -> str:
    """Every top-level `*.md` in the direction workspace, concatenated.

    `brief.md` is the pattern this extends: a human drops `persona.md` (who
    John is, how the game sounds) next to it and the director knows it on the
    next request. No restart, no code change, no prompt buried in Python.
    """
    files = sorted(p for p in direction.glob("*.md") if p.is_file())
    if not files:
        raise DirectorError(f"direction workspace has no *.md persona files: {direction}")
    parts: list[str] = []
    used = 0
    for path in files:
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError as error:
            parts.append(f"## {path.name}\n(unreadable: {error})")
            continue
        if used + len(text) > MAX_PERSONA_BYTES:
            text = text[: max(0, MAX_PERSONA_BYTES - used)] + "\n(truncated)"
        used += len(text)
        parts.append(f"## {path.name}\n{text}")
        if used >= MAX_PERSONA_BYTES:
            break
    return "\n\n".join(parts)


def load_workspace(direction: Path, manifest: Path | None = None) -> Workspace:
    direction = direction.resolve()
    if not direction.is_dir():
        raise DirectorError(f"direction workspace is not a directory: {direction}")
    persona = read_persona(direction)
    notes: list[str] = []
    document = None
    game_root = None
    if manifest is not None:
        manifest = manifest.resolve()
        try:
            document = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            # Information, not a gate: the director can still talk about the
            # game with a broken manifest, and should be told it is broken.
            notes.append(f"manifest could not be read ({error})")
            document = None
        # assets/manifest.json sits one directory below the game repo root.
        game_root = manifest.parent.parent
    return Workspace(
        direction=direction,
        persona=persona,
        manifest=manifest,
        manifest_doc=document if isinstance(document, dict) else None,
        game_root=game_root,
        notes=notes,
    )


def manifest_request(workspace: Workspace, request_id: str) -> dict:
    """The manifest entry for one request id, or a DirectorError naming what
    is there instead. Structural, not judgmental — the director is never
    stopped by this, only callers that genuinely need the entry."""
    requests = (workspace.manifest_doc or {}).get("requests")
    if not isinstance(requests, list):
        raise DirectorError("manifest has no requests array")
    matches = [r for r in requests if isinstance(r, dict) and r.get("id") == request_id]
    if len(matches) != 1:
        known = ", ".join(
            str(r.get("id")) for r in requests if isinstance(r, dict)
        ) or "(none)"
        raise DirectorError(f"no single manifest request {request_id!r}; known ids: {known}")
    return matches[0]


def asset_path(workspace: Workspace, request: dict) -> Path | None:
    relative = request.get("path")
    if not isinstance(relative, str) or not relative or workspace.game_root is None:
        return None
    root = workspace.game_root.resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def asset_inventory(workspace: Workspace) -> list[dict]:
    """What has actually been delivered, as opposed to what the manifest
    claims. The gap between the two is exactly the kind of thing a director
    should be able to notice on its own."""
    out = []
    for request in (workspace.manifest_doc or {}).get("requests", []):
        if not isinstance(request, dict):
            continue
        path = asset_path(workspace, request)
        row = {
            "id": request.get("id"),
            "status": request.get("status"),
            "declares": {
                k: request.get(k) for k in ("format", "width", "height") if k in request
            },
            "path": request.get("path"),
            "exists": bool(path and path.is_file()),
        }
        if path and path.is_file():
            row["bytes"] = path.stat().st_size
            row["inspected"] = inspect_image(path)
        out.append(row)
    return out


def workspace_tree(workspace: Workspace, limit: int = 120) -> list[str]:
    """A shallow file listing of what the persona may read. Cheap orientation
    so the model knows a deeper Read is worth asking for."""
    names: list[str] = []
    for base in (workspace.direction, workspace.game_root):
        if base is None or not base.is_dir():
            continue
        root = base.resolve()
        for path in sorted(root.rglob("*")):
            if any(part.startswith(".") for part in path.relative_to(root).parts):
                continue
            if path.is_file():
                names.append(str(path))
            if len(names) >= limit:
                names.append("(listing truncated)")
                return names
    return names


# --- advisory inspection -------------------------------------------------
#
# This used to be `mechanical_check`, and it used to abort the run. It is
# now a report: it says what the file is, the manifest says what was asked
# for, and the director decides whether the difference matters (roadmap p3
# step 3 — the clamps become tools in the agent's hand, not gates in front
# of it).

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def inspect_image(path: Path) -> dict:
    """Best-effort description of an image file. Never raises: an
    undecodable file is a fact about the file, not an exception."""
    try:
        raw = path.read_bytes()
    except OSError as error:
        return {"readable": False, "note": str(error)}
    if raw.startswith(PNG_SIGNATURE) and len(raw) >= 24:
        try:
            width = int.from_bytes(raw[16:20], "big")
            height = int.from_bytes(raw[20:24], "big")
        except ValueError:
            return {"format": "png", "note": "IHDR unreadable"}
        return {"format": "png", "width": width, "height": height, "bytes": len(raw)}
    if raw[:2] == b"\xff\xd8":
        return {"format": "jpeg", "bytes": len(raw), "note": "dimensions not decoded"}
    return {"format": "unknown", "bytes": len(raw)}


def compare_to_manifest(inspected: dict, request: dict) -> list[str]:
    """Differences between the delivered file and the manifest's wishes,
    phrased as observations. Nothing here stops anything."""
    notes = []
    want_format = str(request.get("format", "")).lower()
    if want_format and inspected.get("format") not in (want_format, None):
        notes.append(f"manifest asks for {want_format}, file looks like {inspected.get('format')}")
    for key in ("width", "height"):
        want = request.get(key)
        got = inspected.get(key)
        if isinstance(want, int) and isinstance(got, int) and want != got:
            notes.append(f"manifest asks for {key} {want}, file has {got}")
    return notes


# --- records -------------------------------------------------------------
#
# devpolicy/agent_records.md: id, backend (model + harness), outcome,
# cost/time when the backend reports them, and on failure a free-text
# report in the failing party's own words.


def records_dir(workspace: Workspace | None) -> Path:
    override = local_env("DIRECTOR_RECORDS_DIR")
    if override:
        return Path(override)
    base = workspace.direction if workspace is not None else ROOT / ".local" / "director"
    return base / "records"


def next_record_id(directory: Path) -> int:
    directory.mkdir(parents=True, exist_ok=True)
    n = 1
    while (directory / f"run-{n:04d}.json").exists():
        n += 1
    return n


def write_record(directory: Path, run_id: int, record: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"run-{run_id:04d}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


# --- backends ------------------------------------------------------------


def run_claude(prompt: str, workspace: Workspace) -> tuple[str, dict]:
    """`claude -p` with read tools over the widened workspace."""
    model = backend_model("claude")
    argv = [
        claude_bin(),
        "-p",
        "--output-format",
        "json",
        "--model",
        model,
        "--allowedTools",
        CLAUDE_ALLOWED_TOOLS,
    ]
    try:
        proc = subprocess.run(
            argv,
            input=prompt,
            cwd=workspace.context_root,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            env={**os.environ, "NO_COLOR": "1"},
        )
    except subprocess.TimeoutExpired:
        raise DirectorError(f"claude backend timed out after {TIMEOUT_SECONDS}s")
    except OSError as error:
        raise DirectorError(f"could not launch claude ({argv[0]}): {error}")
    try:
        doc = json.loads(proc.stdout)
    except ValueError:
        tail = (proc.stderr or proc.stdout or "").strip()[-400:] or "no output"
        raise DirectorError(f"claude backend exited {proc.returncode}: {tail}")
    if doc.get("is_error"):
        raise DirectorError(f"claude backend reported an error: {doc.get('subtype')}")
    text = str(doc.get("result") or "").strip()
    if not text:
        raise DirectorError("claude backend produced no text")
    meta = {
        "model": model,
        "cost_usd": doc.get("total_cost_usd"),
        "num_turns": doc.get("num_turns"),
        "backend_duration_ms": doc.get("duration_ms"),
    }
    return text, meta


def run_ollama(prompt: str, workspace: Workspace) -> tuple[str, dict]:
    """A local model over ollama's /api/chat. It gets no tools, so the
    context blob in the prompt is all it sees; it reports tokens, never a
    price, and a null cost is recorded rather than an invented one."""
    url = (local_env("DIRECTOR_OLLAMA_URL") or "http://127.0.0.1:11434").rstrip("/")
    model = backend_model("ollama")
    body = json.dumps(
        {"model": model, "stream": False, "messages": [{"role": "user", "content": prompt}]}
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{url}/api/chat", data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            doc = json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise DirectorError(f"ollama at {url} returned HTTP {error.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise DirectorError(f"ollama at {url} is unreachable: {error}")
    except ValueError as error:
        raise DirectorError(f"ollama at {url} returned non-JSON: {error}")
    text = ((doc.get("message") or {}).get("content") or "").strip()
    if not text:
        raise DirectorError(f"ollama model {model} returned an empty message")
    meta = {
        "model": model,
        "cost_usd": None,
        "prompt_tokens": doc.get("prompt_eval_count"),
        "output_tokens": doc.get("eval_count"),
    }
    return strip_thinking(text), meta


def run_backend(backend: str, prompt: str, workspace: Workspace) -> tuple[str, dict]:
    """Dispatch by name, resolved at call time — so a test (or a future
    wrapper) can replace one backend without rebuilding a lookup table."""
    if backend == "claude":
        return run_claude(prompt, workspace)
    if backend == "ollama":
        return run_ollama(prompt, workspace)
    raise DirectorError(f"unknown backend: {backend!r}")


THINK_BLOCK = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)


def strip_thinking(text: str) -> str:
    """Some local models emit a <think> block before the answer; it is
    reasoning, not the director speaking."""
    return THINK_BLOCK.sub("", text).strip()


# --- the entrance --------------------------------------------------------

PROMPT = """You are the creative director for this project. Who you are, how
you talk, and what you care about are defined by the DIRECTION FILES below —
they are your own notes, written by your human collaborator. Speak as that
person, in that voice, with that taste.

You talk to two kinds of caller through this one window, and you can tell
them apart from the message itself:

- A human asking you something creative, loose, or half-formed ("would John
  really say this?", "is this twist too heavy?"). Answer as a director would:
  take a position, say why, and say plainly when a call is not yours to make.
- Another agent asking for something practical ("compose a generation
  request for X", "verify this line, pass or fail"). Answer that too, in the
  same voice, and give it what it can act on.

When — and only when — the caller asked for a pass/fail or accept/reject
judgment, make the LAST line of your reply exactly:

    VERDICT: pass — <one short reason>
    VERDICT: fail — <one short reason>

Nothing checks or overrides that line; it is how a machine caller reads you.
Never write it for a question that was not a judgment.

When the caller asks what you can do, what you cannot do, or what any of it
costs, the ENTRANCE GUIDE below is the answer and your own impression is
not. Its figures are measurements; you have no other way of knowing them.
Talking to you is a paid model run and is never free, so quote the number
rather than waving the question away, and say "unknown" wherever the guide
does. Being in character never licenses inventing a figure.

The material below is context, not a cage. The WORKSPACE FILES list names
things you may read yourself when you have the Read/Glob/Grep tools; use them
when the answer depends on something you have not been shown. The MANIFEST
and ASSETS sections are observations, including any mismatch between what was
asked for and what was delivered — they are information for your judgment,
not rules you must enforce. Nothing in this system will overrule you; if you
are unsure, say so in your own words rather than inventing certainty.

Reply in plain prose. No markdown headings, no preamble such as "Here is my
answer" — begin with the answer itself.

=== DIRECTION FILES ===
{persona}

=== ENTRANCE GUIDE ===
{guide}

=== WORKSPACE ===
{workspace}

=== CALLER'S MESSAGE ===
{text}
"""


def build_context(workspace: Workspace, extra: dict | None = None) -> str:
    doc: dict = {
        "direction_workspace": str(workspace.direction),
        "context_root": str(workspace.context_root),
        "readable_files": workspace_tree(workspace),
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if workspace.manifest is not None:
        doc["manifest_path"] = str(workspace.manifest)
        doc["manifest"] = workspace.manifest_doc
        doc["assets"] = asset_inventory(workspace)
    if workspace.notes:
        doc["notes"] = workspace.notes
    if extra:
        doc.update(extra)
    return json.dumps(doc, indent=2, ensure_ascii=False, default=str)


def parse_verdict(reply: str) -> dict | None:
    """The trailing marker line, if the director wrote one. Lenient by
    design: a missing or malformed verdict means the director chose prose,
    which is always allowed."""
    matches = list(VERDICT_LINE.finditer(reply))
    if not matches:
        return None
    last = matches[-1]
    return {"pass": last.group(1).lower() == "pass", "reason": last.group(2).strip()}


def answer(text: str, workspace: Workspace, extra: dict | None = None) -> dict:
    """One director run through the single entrance.

    Returns the record (devpolicy/agent_records.md) with the reply in it.
    A backend failure comes back as a `failed` record rather than an
    exception — a director that cannot reach its model still has to say so.
    """
    text = (text or "").strip()
    if not text:
        raise DirectorError("empty message")
    if len(text) > MAX_TEXT:
        raise DirectorError(f"message longer than {MAX_TEXT} characters")
    directory = records_dir(workspace)
    run_id = next_record_id(directory)
    started = time.monotonic()
    record: dict = {
        "id": f"director/run-{run_id:04d}",
        "started": time.time(),
        "direction": str(workspace.direction),
        "question": text,
        "backend": None,
        "outcome": "failed",
    }
    if extra and extra.get("purpose"):
        record["purpose"] = extra["purpose"]
    try:
        backend = backend_name()
        record["backend"] = backend
        prompt = PROMPT.format(
            persona=workspace.persona,
            guide=read_guide(),
            workspace=build_context(workspace, extra),
            text=text,
        )
        reply, meta = run_backend(backend, prompt, workspace)
    except DirectorError as error:
        record["failure"] = str(error)
        record["duration_ms"] = int((time.monotonic() - started) * 1000)
        write_record(directory, run_id, record)
        return record
    record.update(meta)
    record["backend_model"] = f"{record['backend']}/{meta.get('model')}"
    record["outcome"] = "done"
    record["duration_ms"] = int((time.monotonic() - started) * 1000)
    record["reply"] = reply
    record["verdict"] = parse_verdict(reply)
    write_record(directory, run_id, record)
    return record


def read_guide() -> str:
    """Re-read per request (cagent's llms.txt pattern): editing the card
    takes effect on the next answer, with no restart."""
    try:
        return GUIDE.read_text(encoding="utf-8")
    except OSError:
        return "(no capability card is installed)"


# --- CLI wrapper (same entrance, second transport) -----------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Talk to the director.")
    parser.add_argument("text", nargs="?", help="what you want to say; omit to read stdin")
    parser.add_argument("--direction", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, help="optional game asset manifest")
    parser.add_argument("--json", action="store_true", help="print the whole run record")
    args = parser.parse_args(argv)
    text = args.text if args.text is not None else sys.stdin.read()
    try:
        workspace = load_workspace(args.direction, args.manifest)
        record = answer(text, workspace)
    except DirectorError as error:
        print(f"director: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(record, indent=2, ensure_ascii=False))
    elif record["outcome"] == "done":
        print(record["reply"])
    else:
        print(f"director: {record.get('failure')}", file=sys.stderr)
    return 0 if record["outcome"] == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
