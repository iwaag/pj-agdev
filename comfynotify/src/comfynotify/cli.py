"""The agent-facing `watch` command and the daemon entry point."""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from .commands import CommandIntake
from .notifier import Notifier
from .tickets import DEFAULT_TIMEOUT_S, now, write_ticket

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TICKETS = ROOT / ".local" / "tickets"
DEFAULT_LOG = ROOT / ".local" / "out" / "notifier.log"
DEFAULT_STATE = ROOT / ".local" / "command-mark.json"


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


def build_intake(args: argparse.Namespace, notifier: Notifier) -> CommandIntake | None:
    """The mention sweep, or None with a logged reason.

    Command intake is an addition, not a precondition: a daemon without Zulip
    credentials or a default ComfyUI URL still serves every ticket the CLI
    writes, which is the path this project started from.
    """
    credentials = os.environ.get("AGENTCHAT_ZULIP_ENV")
    comfyui_url = os.environ.get("AGFORGE_COMFYUI_URL")
    if not credentials or not comfyui_url:
        missing = " and ".join(
            name for name, value in
            (("AGENTCHAT_ZULIP_ENV", credentials), ("AGFORGE_COMFYUI_URL", comfyui_url))
            if not value
        )
        notifier.log(f"command intake off: {missing} unset")
        return None
    from agag.zulip import ZulipClient

    client = ZulipClient.from_env(Path(credentials))
    identity = client.whoami()
    intake = CommandIntake(
        client,
        tickets_dir=args.tickets,
        state_path=args.command_state,
        comfyui_url=comfyui_url,
        bot_name=str(identity.get("full_name") or "Comfy Notifier"),
        self_id=int(identity["user_id"]),
        send=notifier.send,
        log=notifier.log,
    )
    notifier.log(f"command intake on as {intake.bot_name} ({intake.self_id})")
    return intake


def daemon(args: argparse.Namespace) -> int:
    notifier = Notifier(args.tickets, args.log, agentchat=args.agentchat)
    intake = None if args.no_commands else build_intake(args, notifier)
    while True:
        if intake is not None:
            try:
                intake.sweep_once()
            except Exception as error:  # noqa: BLE001 — Zulip being down is not fatal
                notifier.log(f"command sweep failed: {error}")
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
    daemon_parser.add_argument("--command-state", type=Path, default=DEFAULT_STATE,
                               help="high-water mark for processed commands (default: %(default)s)")
    daemon_parser.add_argument("--no-commands", action="store_true",
                               help="serve tickets only; do not read Zulip mentions")
    daemon_parser.add_argument("--once", action="store_true")
    daemon_parser.set_defaults(handler=daemon)
    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
