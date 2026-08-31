"""The agent-facing `watch` command and the daemon entry point."""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from .notifier import Notifier
from .tickets import DEFAULT_TIMEOUT_S, now, write_ticket

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TICKETS = ROOT / ".local" / "tickets"
DEFAULT_LOG = ROOT / ".local" / "out" / "notifier.log"


def _destination(value: str) -> tuple[str, str]:
    channel, separator, topic = value.partition("/")
    if not separator or not channel or not topic:
        raise argparse.ArgumentTypeError("destination must be <channel>/<topic>")
    return channel, topic


def watch(args: argparse.Namespace) -> int:
    destination = args.to or os.environ.get("AGENTCHAT_HOME")
    if not destination:
        raise SystemExit("--to is required outside an agent run (AGENTCHAT_HOME is unset)")
    channel, topic = _destination(destination)
    comfyui_url = args.comfyui or os.environ.get("AGFORGE_COMFYUI_URL")
    if not comfyui_url:
        raise SystemExit("--comfyui is required when AGFORGE_COMFYUI_URL is unset")
    ticket = {
        "prompt_id": args.prompt_id,
        "comfyui_url": comfyui_url,
        "channel": channel,
        "topic": topic,
        "mention": args.mention,
        "note": args.note or "",
        "timeout_s": args.timeout,
        "created_at": now(),
    }
    path = write_ticket(args.tickets, ticket)
    print(f"watching {args.prompt_id}; callback will land in {channel}/{topic} ({path.name})")
    return 0


def daemon(args: argparse.Namespace) -> int:
    notifier = Notifier(args.tickets, args.log, agentchat=args.agentchat)
    while True:
        notifier.sweep_once()
        if args.once:
            return 0
        time.sleep(args.poll_interval)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write a ComfyUI completion ticket; the notifier posts the callback later."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--tickets", type=Path, default=DEFAULT_TICKETS,
                        help="ignored ticket directory (default: %(default)s)")
    watch_parser = subparsers.add_parser("watch", parents=[common],
        help="queue a callback without waiting for ComfyUI")
    watch_parser.add_argument("prompt_id")
    watch_parser.add_argument("--to", help="callback destination, channel/topic (default: AGENTCHAT_HOME)")
    watch_parser.add_argument("--mention", help="optional Zulip full name to mention")
    watch_parser.add_argument("--note", help="free text returned verbatim in the callback record")
    watch_parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S,
                              help="terminal timeout in seconds (default: %(default)s)")
    watch_parser.add_argument("--comfyui", help="ComfyUI base URL (default: AGFORGE_COMFYUI_URL)")
    watch_parser.set_defaults(handler=watch)
    daemon_parser = subparsers.add_parser("daemon", parents=[common], help="serve tickets forever")
    daemon_parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    daemon_parser.add_argument("--agentchat", default="agentchat")
    daemon_parser.add_argument("--poll-interval", type=float, default=5)
    daemon_parser.add_argument("--once", action="store_true")
    daemon_parser.set_defaults(handler=daemon)
    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
