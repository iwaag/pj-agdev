#!/usr/bin/env python3
"""The director's window: HTTP transport for director.answer().

Stdlib-only single file, in the shape of agautolab's gateway. Routes:

  POST /window   {"text": str, "direction"?: str, "manifest"?: str}
  GET  /guide    GUIDE.md, the capability card, as plain text
  GET  /healthz  liveness probe

`POST /window` is the director's single desire-accepting entrance
(devpolicy/policy.md, Single Entrance). `director.py`'s CLI and
`reconcile.py` reach the same `answer()` in-process — three transports, one
conceptual entrance.

`direction` and `manifest` are addressing, not desire: which workspace you
are talking about, never what you want. They default to
DIRECTOR_DIRECTION / DIRECTOR_MANIFEST so a single-project deployment needs
neither. Both are resolved against DIRECTOR_WORKSPACE_ROOT when it is set,
which is the whole of the access control here: this is an experimental
local service and, like autolab's window, its auth waits for the
system-wide design.

One answer at a time: the default backend spends money, so the window
carries the same one-at-a-time guard autolab's does.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import director

MAX_BODY = 64 * 1024
KIND = "director.window.v1"

window_lock = threading.Lock()


def resolve_workspace(direction: str | None, manifest: str | None) -> director.Workspace:
    direction = direction or director.local_env("DIRECTOR_DIRECTION")
    manifest = manifest or director.local_env("DIRECTOR_MANIFEST")
    if not direction:
        raise director.DirectorError(
            "no direction workspace: pass \"direction\" or set DIRECTOR_DIRECTION"
        )
    root = director.local_env("DIRECTOR_WORKSPACE_ROOT")
    paths = []
    for value in (direction, manifest):
        if value is None:
            paths.append(None)
            continue
        path = Path(value).expanduser().resolve()
        if root:
            base = Path(root).expanduser().resolve()
            try:
                path.relative_to(base)
            except ValueError:
                raise director.DirectorError(f"path escapes DIRECTOR_WORKSPACE_ROOT: {value}")
        paths.append(path)
    return director.load_workspace(paths[0], paths[1])


class Handler(BaseHTTPRequestHandler):
    server_version = "director-window/1"

    def send_json(self, code, obj):
        body = (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, code, text):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/healthz":
            return self.send_json(200, {"ok": True})
        if path == "/guide":
            return self.send_text(200, director.read_guide())
        self.send_json(404, {"error": "unknown route"})

    def do_POST(self):
        if self.path.split("?")[0] != "/window":
            return self.send_json(404, {"error": "unknown route"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_BODY:
                return self.send_json(413, {"error": "body too large"})
            req = json.loads(self.rfile.read(length))
            text = req["text"]
            assert isinstance(text, str) and text.strip()
        except Exception:
            return self.send_json(400, {"error": 'body must be {"text": "..."}'})
        try:
            workspace = resolve_workspace(req.get("direction"), req.get("manifest"))
        except director.DirectorError as error:
            return self.send_json(400, {"error": str(error)})
        if not window_lock.acquire(blocking=False):
            return self.send_json(409, {"error": "the director is already answering someone"})
        try:
            record = director.answer(text, workspace)
        except director.DirectorError as error:
            return self.send_json(400, {"error": str(error)})
        finally:
            window_lock.release()
        # The record is the response: the caller sees which backend answered
        # and what it cost without a second request, and a failed backend is
        # a 502 carrying the backend's own words.
        self.send_json(
            200 if record["outcome"] == "done" else 502,
            {"kind": KIND, "type": "window", **record},
        )

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main():
    host = os.environ.get("DIRECTOR_WINDOW_HOST", "127.0.0.1")
    port = int(os.environ.get("DIRECTOR_WINDOW_PORT", "8094"))
    signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"director-window listening on {host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
