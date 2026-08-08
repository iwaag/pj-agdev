#!/usr/bin/env python3
"""Request, review, and deliver requested manifest assets through agforge."""

from __future__ import annotations

import argparse
import binascii
import json
import shutil
import struct
import sys
import time
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass
from pathlib import Path

import director


POLL_SECONDS = 3
GENERATION_TIMEOUT_SECONDS = 180
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class ReconcileError(Exception):
    """The asset reconcile could not safely complete."""


@dataclass(frozen=True)
class MechanicalResult:
    width: int
    height: int
    format: str


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
            if not isinstance(artifacts, list):
                raise ReconcileError("agforge done response has no artifacts")
            images = [item for item in artifacts if isinstance(item, dict) and item.get("kind") == "image"]
            if len(images) != 1 or not isinstance(images[0].get("url"), str):
                raise ReconcileError("agforge did not return exactly one image URL")
            return request_id, images[0]["url"]
        if state == "failed":
            error = status.get("detail") or "unknown failure"
            raise ReconcileError(f"agforge job {request_id} failed: {error}")
        if state not in ("queued", "running", "working"):
            raise ReconcileError(f"agforge job {request_id} has unknown status {state!r}")
        time.sleep(POLL_SECONDS)
    raise ReconcileError(f"agforge job {request_id} exceeded {GENERATION_TIMEOUT_SECONDS}s")


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        temporary.replace(destination)
    except (OSError, urllib.error.URLError) as error:
        temporary.unlink(missing_ok=True)
        raise ReconcileError(f"could not download generated image: {error}") from error


def decode_png(path: Path) -> MechanicalResult:
    raw = path.read_bytes()
    if not raw.startswith(PNG_SIGNATURE):
        raise ReconcileError("candidate is not a PNG image")
    offset = len(PNG_SIGNATURE)
    width = height = bit_depth = color_type = interlace = None
    compressed = bytearray()
    saw_end = False
    while offset < len(raw):
        if offset + 12 > len(raw):
            raise ReconcileError("PNG has a truncated chunk")
        length = struct.unpack(">I", raw[offset : offset + 4])[0]
        kind = raw[offset + 4 : offset + 8]
        data_start = offset + 8
        data_end = data_start + length
        if data_end + 4 > len(raw):
            raise ReconcileError("PNG chunk exceeds file length")
        data = raw[data_start:data_end]
        expected_crc = struct.unpack(">I", raw[data_end : data_end + 4])[0]
        actual_crc = binascii.crc32(kind + data) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise ReconcileError(f"PNG {kind.decode('ascii', 'replace')} chunk has invalid CRC")
        if kind == b"IHDR":
            if length != 13 or width is not None:
                raise ReconcileError("PNG has an invalid IHDR")
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", data
            )
            if compression != 0 or filtering != 0 or interlace != 0:
                raise ReconcileError("PNG uses unsupported compression, filtering, or interlace")
        elif kind == b"IDAT":
            compressed.extend(data)
        elif kind == b"IEND":
            saw_end = True
            break
        offset = data_end + 4
    if None in (width, height, bit_depth, color_type) or not compressed or not saw_end:
        raise ReconcileError("PNG is missing required IHDR, IDAT, or IEND data")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    if channels is None or bit_depth not in (1, 2, 4, 8, 16):
        raise ReconcileError("PNG has unsupported color or bit depth")
    try:
        pixels = zlib.decompress(bytes(compressed))
    except zlib.error as error:
        raise ReconcileError(f"PNG pixel stream does not decode: {error}") from error
    row_bytes = (width * channels * bit_depth + 7) // 8
    if len(pixels) != height * (row_bytes + 1):
        raise ReconcileError("PNG decoded pixel stream has the wrong length")
    return MechanicalResult(width=width, height=height, format="png")


def mechanical_check(path: Path, request: dict) -> MechanicalResult:
    expected_format = str(request.get("format", "")).lower()
    if expected_format != "png":
        raise ReconcileError(f"unsupported manifest format: {expected_format!r}")
    result = decode_png(path)
    expected = (request.get("width"), request.get("height"))
    if (result.width, result.height) != expected:
        raise ReconcileError(
            f"dimension mismatch: got {result.width}x{result.height}, expected {expected[0]}x{expected[1]}"
        )
    return result


def set_delivered(manifest: Path, request_id: str) -> None:
    document = json.loads(manifest.read_text(encoding="utf-8"))
    changed = 0
    for request in document["requests"]:
        if request.get("id") == request_id:
            if request.get("status") != "requested":
                raise ReconcileError(f"request {request_id!r} is no longer requested")
            request["status"] = "delivered"
            changed += 1
    if changed != 1:
        raise ReconcileError(f"manifest did not contain exactly one request {request_id!r}")
    temporary = manifest.with_suffix(manifest.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    temporary.replace(manifest)


def persist_envelopes(direction: Path, request_id: str, payload: dict) -> Path:
    """Write the full compose/review evidence for one request atomically.

    Called after compose and after every attempt so partial evidence survives
    any later failure — the parent episode lost a successful envelope this way.
    """
    path = direction / "reviews" / f"{request_id}.envelopes.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def write_review(
    path: Path,
    desire: str,
    attempts: list[dict],
    verdict: str,
) -> None:
    lines = [
        "# Background asset review",
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
            f"- agforge request id: `{attempt['request_id']}`",
            f"- Mechanical check: {attempt['mechanical']}",
            f"- Subjective verdict: {attempt.get('subjective', 'not run')}",
            f"- Reason: {attempt.get('reason', 'n/a')}",
            "",
        ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def reconcile(direction_path: Path, manifest_path: Path, request_id: str, agforge_url: str) -> dict:
    context = director.load_context(direction_path, manifest_path, request_id)
    if context.request.get("status") != "requested":
        raise ReconcileError(f"request {request_id!r} is not in requested state")
    composed, compose_meta = director.compose(context)
    desire = composed["desire"]
    suffix = "." + str(context.request.get("format", "png")).lower()
    candidate = context.direction / "candidates" / f"{request_id}{suffix}"
    attempts: list[dict] = []
    evidence = {
        "request": request_id,
        "desire": desire,
        "compose_meta": compose_meta,
        "attempts": attempts,
        "verdict": "in_progress",
    }
    persist_envelopes(context.direction, request_id, evidence)
    last_error: ReconcileError | None = None
    for attempt_number in (1, 2):
        agforge_id = "not-created"
        try:
            agforge_id, url = request_image(agforge_url, desire)
            download(url, candidate)
            mechanical = mechanical_check(candidate, context.request)
        except ReconcileError as error:
            last_error = error
            attempts.append(
                {
                    "attempt": attempt_number,
                    "request_id": agforge_id,
                    "mechanical": f"failed: {error}",
                }
            )
            persist_envelopes(context.direction, request_id, evidence)
            if "refused:" in str(error):
                break
            continue
        try:
            subjective, review_meta = director.review(context, candidate)
        except director.DirectorError as error:
            last_error = ReconcileError(f"director review failed: {error}")
            attempts.append(
                {
                    "attempt": attempt_number,
                    "request_id": agforge_id,
                    "mechanical": f"passed: {mechanical.format} {mechanical.width}x{mechanical.height}",
                    "subjective": f"error: {error}",
                }
            )
            persist_envelopes(context.direction, request_id, evidence)
            continue
        attempts.append(
            {
                "attempt": attempt_number,
                "request_id": agforge_id,
                "mechanical": f"passed: {mechanical.format} {mechanical.width}x{mechanical.height}",
                "subjective": "accepted" if subjective["accepted"] else "rejected",
                "reason": subjective["reason"],
                "review_meta": review_meta,
            }
        )
        persist_envelopes(context.direction, request_id, evidence)
        if subjective["accepted"]:
            destination = director.expected_asset_path(context)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidate, destination)
            set_delivered(context.manifest, request_id)
            evidence["verdict"] = "provisional"
            persist_envelopes(context.direction, request_id, evidence)
            write_review(
                context.direction / "reviews" / f"{request_id}.md",
                desire,
                attempts,
                "provisional",
            )
            return {"desire": desire, "compose_meta": compose_meta, "attempts": attempts}
        last_error = ReconcileError(f"director rejected attempt {attempt_number}: {subjective['reason']}")
    evidence["verdict"] = "rejected"
    persist_envelopes(context.direction, request_id, evidence)
    write_review(
        context.direction / "reviews" / f"{request_id}.md",
        desire,
        attempts,
        "rejected — human review required",
    )
    raise last_error or ReconcileError("asset reconciliation did not produce an acceptable candidate")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--direction", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--agforge-url", required=True)
    args = parser.parse_args(argv)
    try:
        result = reconcile(args.direction, args.manifest, args.request_id, args.agforge_url)
    except (director.DirectorError, ReconcileError) as error:
        print(f"asset reconcile: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
