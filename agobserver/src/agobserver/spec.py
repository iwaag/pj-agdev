"""Observer's agent spec: its instance, its local state and its roles.

Shared by the workflow monitor (`wfmonitor`, observer p3) and the watch
listener, which is kept as a library but not started.
"""

from __future__ import annotations

from pathlib import Path

from agag.agent import AgentSpec
from agag.execopt import Option

ROOT = Path(__file__).resolve().parents[2]

SPEC = AgentSpec(
    "agobserver",
    ROOT,
    plan_prefix="watch-",
    run_prefix="",
    # `ag.exec-options.v1`. Observing is deliberately not on this menu: an
    # evaluation runs every interval for as long as a watch waits, and the
    # local model is the reason that is affordable. What can be asked for is
    # a harder *reading* of a request, once.
    exec_options=(
        # Declared rather than left to be prepended, because the pool has to
        # be said out loud: the local harness spends no shared account, so
        # `agag.execpool` derives `unknown` — which is the honest answer for
        # "there is no usage window to judge a threshold against", not a gap.
        Option(
            "default",
            pool="unknown",
            covers="everything",
            summary="the local model on this host; no shared account is spent",
        ),
        Option(
            "sonnet",
            pool="anthropic",
            covers="reading a watch request",
            summary="for a request the local model keeps asking questions about",
        ),
    ),
    exec_roles=("front",),
)
