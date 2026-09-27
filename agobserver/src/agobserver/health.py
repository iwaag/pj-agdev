"""The owners whose work Observer can probe, and one bounded probe of it.

failsafe p2 step 3. An owner that exposes the execution health interface
(`agag.health.v1`: `python -m agag.health`, pyagag) is listed in the
ignored `.local/health.toml` with the command that answers for it:

    [owners."autolab-agstudio1"]
    command = ["/…/agautolab/.venv/bin/python", "-m", "agag.health",
               "--dir", "/…/agautolab/.local/executions",
               "--queue", "/…/agautolab/.local/mirror/listener.sqlite"]
    timeout = 10

The monitor appends `--ack <id> --channel <c> --topic <t> --window <s>` and
reads one JSON document from stdout. For a post nobody acknowledged yet
(failsafe p5) it appends `--queued --since <post time>` instead of the ack:
where that post is in the owner's queue (`agag.health.probe_queue`). The command is the whole contract: how
the owner inspects its harness stays on its side of it. An owner that is
not listed is not probed and keeps the conversation-only rules (`silent`,
`quiet`), which is the documented limitation, not an error.

**Bounded.** Each probe runs under its own timeout. A command that fails,
times out or prints something that is not the document answers `unknown`
with the reason, promptly: a dead adapter makes Observer uncertain, never
blocked. The trial fault `faults/probe-fail` (while it exists) makes every
probe answer `unknown` without running anything.
"""

from __future__ import annotations

import json
import subprocess
import time
import tomllib
from pathlib import Path
from typing import Any, Callable

CONFIG_FILE = "health.toml"
DEFAULT_TIMEOUT = 10.0
SCHEMA = "agag.health.v1"
FAULT = "probe-fail"

__all__ = ["HealthProbes", "unknown"]


def unknown(why: str, **extra) -> dict[str, Any]:
    """A probe result that establishes nothing, and says why."""
    return {"schema": SCHEMA, "observed_at": time.time(), "verdict": "unknown", "why": why,
            "unknowns": [why], "process": {"state": "unknown"}, "progress": {}, "wait": {"kind": "unknown"},
            "serving": None, **extra}


class HealthProbes:
    """The configured owners, and a probe of one serving of theirs."""

    def __init__(self, owners: dict[str, dict[str, Any]] | None = None, *, faults: Path | None = None,
                 runner: Callable[..., Any] = subprocess.run):
        self.owners = {str(name): dict(entry) for name, entry in (owners or {}).items() if entry.get("command")}
        self.faults = faults
        self.runner = runner
        self.runs = 0
        self.failures = 0
        self.last: dict[str, Any] | None = None

    @classmethod
    def load(cls, local: Path) -> "HealthProbes":
        try:
            with open(Path(local) / CONFIG_FILE, "rb") as handle:
                config = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError):
            config = {}
        return cls(config.get("owners") or {}, faults=Path(local) / "faults")

    def covers(self, owner: str) -> bool:
        return bool(owner) and owner in self.owners

    def probe(self, owner: str, *, ack: int, channel: str, topic: str, window: float,
              queued_since: float | None = None) -> dict[str, Any]:
        """One `agag.health.v1` document about the serving acked by `ack` —
        or, with `queued_since`, about a post made then that nobody has
        acknowledged yet. Never raises; never takes longer than the owner's
        timeout."""
        entry = self.owners.get(owner)
        if entry is None:
            return unknown(f"{owner or 'the owner'} exposes no health interface here")
        started = time.time()
        self.runs += 1
        if self.faults is not None and (self.faults / FAULT).exists():
            self.failures += 1
            result = unknown(f"the health probe of {owner} failed (fault injected: {FAULT})")
            self._remember(owner, ack, started, result)
            return result
        timeout = float(entry.get("timeout") or DEFAULT_TIMEOUT)
        argv = [*map(str, entry["command"]), "--ack", str(int(ack or 0)), "--channel", channel, "--topic", topic,
                "--window", str(int(window))]
        if queued_since is not None:
            argv += ["--queued", "--since", str(float(queued_since))]
        try:
            done = self.runner(argv, capture_output=True, text=True, timeout=timeout, check=False)
            result = json.loads((done.stdout or "").strip().splitlines()[-1]) if (done.stdout or "").strip() else None
            if not isinstance(result, dict) or result.get("schema") != SCHEMA:
                raise ValueError(f"exit {done.returncode}, no health document"
                                 + (f": {(done.stderr or '').strip()[-200:]}" if done.stderr else ""))
        except subprocess.TimeoutExpired:
            self.failures += 1
            result = unknown(f"the health probe of {owner} did not answer within {timeout:g} s")
        except Exception as error:  # noqa: BLE001 - a probe answers, it does not raise
            self.failures += 1
            result = unknown(f"the health probe of {owner} failed: {error}")
        self._remember(owner, ack, started, result)
        return result

    def probe_queue(self, owner: str, *, channel: str, topic: str, since: float, window: float) -> dict[str, Any]:
        """Where a post made at `since` waits in `owner`'s queue (failsafe p5)."""
        return self.probe(owner, ack=0, channel=channel, topic=topic, window=window, queued_since=since)

    def _remember(self, owner: str, ack: int, started: float, result: dict[str, Any]) -> None:
        self.last = {"owner": owner, "ack": int(ack or 0), "at": started,
                     "seconds": round(time.time() - started, 3), "verdict": result.get("verdict")}

    def stats(self) -> dict[str, Any]:
        return {"owners": sorted(self.owners), "runs": self.runs, "failures": self.failures, "last": self.last}
