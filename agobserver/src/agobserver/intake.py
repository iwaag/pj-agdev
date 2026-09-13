"""Accepting one watch: the only place a request becomes work.

One topic in this instance's channel is one watch. A post there is served
here, a local-model run reads it into three fields, and the topic is then
either an **active** watch or a topic holding **one concrete question**.
Nothing in between is scheduled: a request nobody has finished asking is not
evaluated every minute for a day.

Two shapes of care that are not obvious from the outside:

- **The acknowledgement names nobody.** `serve_topic`'s default prefixes a
  reply with a mention of the last other speaker, which is the realm's
  turn-taking rule and exactly wrong here — the requester is waiting for the
  *notification*, not for an acknowledgement, and naming them buys them a
  paid run to read "understood". `handoff=False` is that decision.
- **The visible reply is written by this module, not by the model.** The run
  produces `decision.json` and nothing else; what the channel shows is
  assembled from those fields. A local model's prose is good enough to judge
  a condition and not good enough to be this agent's contract voice.
"""

from __future__ import annotations

import json
from pathlib import Path

from agag.agent import AgentSpec, SWEEP_ACK, exec_options_for, is_ack, run_role
from agag.topics import (
    TopicContext,
    TopicResult,
    chatlog_path,
    conversation_context,
    format_chatlog,
    generation_dir,
    guide,
    next_generation,
    next_record_path,
    prompt_with_guide,
    serve_topic,
    topic_workspace,
)
from agag.zulip import ZulipClient, log, topic_write

from . import anchor, destination as dest, store

#: The guides live beside the package, not inside it: `spec.guides`.
GUIDES = Path(__file__).resolve().parents[2] / "agent" / "guides"
ROLE = "front"
#: One request, one short local run. A model that has not decided in three
#: minutes is not going to.
INTAKE_TIMEOUT_SECONDS = 240.0
DECISION_FILE = "decision.json"

EMPTY_REPLY = (
    "This topic is empty. One topic here is one watch: say what must become "
    "true, what to look at, and where to notify (a message link is best)."
)

__all__ = ["handle_watch", "serve_intake"]


class IntakeError(RuntimeError):
    """The request could not be read into a decision."""


def intake_prompt(conversation: str) -> str:
    return prompt_with_guide(
        [
            "Read the watch request below and write decision.json in the "
            "working directory.",
            "",
            conversation,
        ],
        guide(GUIDES, "intake", "guide.md"),
    )


def _decision(workspace: Path, output: str) -> dict:
    """The run's decision: the file it was asked for, else a block it wrote.

    The file is the contract because a tool call is structured and a final
    message is prose. The fallback exists because a small model that has
    decided correctly and merely forgot the file has still done the work,
    and throwing that away would cost the requester a round trip for nothing.
    """
    path = workspace / DECISION_FILE
    for text in (path.read_text(encoding="utf-8") if path.is_file() else "", output):
        for candidate in _json_candidates(text):
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and "accepted" in parsed:
                return parsed
    raise IntakeError("the run produced no decision.json and no JSON object")


def _json_candidates(text: str):
    """The whole text, then each fenced block in it, newest last."""
    stripped = (text or "").strip()
    if not stripped:
        return
    yield stripped
    parts = stripped.split("```")
    for index in range(1, len(parts), 2):
        block = parts[index]
        yield block.split("\n", 1)[1] if block.lstrip().lower().startswith("json") else block


def _requester(context: TopicContext) -> str:
    """Who asked, read from the conversation rather than from the model.

    The last real speaker who is not this bot. Identity is a fact about the
    transport and there is no reason for a language model to be involved in
    it.
    """
    for message in reversed(context.history):
        if message.get("sender_id") != context.self_id and not is_ack(str(message.get("content", ""))):
            return str(message.get("sender_full_name") or "")
    return ""


def _accepted_body(watch_name: str, accepted: dict, resolved: dest.Resolved) -> str:
    return "\n".join(
        [
            f"**Watching** — `{watch_name}`",
            "",
            f"- **when**: {accepted['condition']}",
            f"- **looking at**: {accepted['target']}",
            f"- **telling**: {resolved.conversation} "
            f"(from `{accepted['destination']}`, anchored to message "
            f"{accepted['destination_id']})",
            "",
            "I will post there once, when that holds, and say nothing here "
            "until then. Resolve this topic (✔) to cancel.",
        ]
    )


def serve_intake(spec: AgentSpec, context: TopicContext) -> TopicResult:
    """Read this topic into a watch, or into one question."""
    watch = anchor.read_watch(
        context.client, context.channel, context.topic, context.self_id,
        history=context.history,
    )
    if watch.state in (anchor.MET, anchor.UNDELIVERABLE):
        return TopicResult(
            [f"`{watch.name}` is finished ({watch.state}). Open a new topic for a new watch."]
        )

    workspace_root = topic_workspace(spec.topics_root, context.channel, context.topic)
    workspace = generation_dir(
        spec.topics_root, context.channel, context.topic,
        next_generation(workspace_root), ROLE,
    )
    context.step = "chatlog placement"
    chatlog = format_chatlog(context.history, context.self_id, drop=is_ack)
    chatlog_path(workspace).write_text(chatlog, encoding="utf-8")

    context.step = "intake run"
    output, _, exit_code = run_role(
        spec, ROLE, intake_prompt(conversation_context(chatlog)),
        cwd=workspace,
        timeout=INTAKE_TIMEOUT_SECONDS,
        record=next_record_path(spec.records_root / "intake"),
        transcript=workspace / "transcript.jsonl",
        stream=True,
        home=(context.channel, context.topic),
        # Reading a request is the one thing a requester may ask to have run
        # another way (`ag.exec-options.v1`). Observing is not on the menu:
        # every interval of every watch runs it, and the local model is what
        # makes waiting free.
        selection=context.selection,
    )
    if exit_code != 0:
        raise IntakeError(f"intake run exited {exit_code}: {output.strip()[:300]}")

    context.step = "decision"
    decision = _decision(workspace, output)
    question = str(decision.get("question") or "").strip()
    if not decision.get("accepted"):
        return _needs_input(spec, context, watch, question or "What should I watch, and where should I tell you?")

    accepted = {
        "condition": str(decision.get("condition") or "").strip(),
        "target": str(decision.get("target") or "").strip(),
        "destination": str(decision.get("destination") or "").strip(),
        "requester": _requester(context),
    }
    if not accepted["condition"]:
        return _needs_input(spec, context, watch, "What condition should I watch for?")
    context.step = "destination"
    parsed, resolved = dest.anchored(context.client, accepted["destination"])
    if parsed is None:
        return _needs_input(
            spec, context, watch,
            "Where should the notification go? Paste a message link from that "
            "conversation (Zulip's *Copy link to message*), or write "
            "`<channel>/<topic>`.",
        )
    if resolved.failed:
        # Not the requester's problem to solve. Asking them for a different
        # destination here would be asking them to work around an outage,
        # and the one they named is very likely fine.
        return _needs_input(
            spec, context, watch,
            f"I could not check `{accepted['destination']}` just now: "
            f"{resolved.reason}. I have not started watching, because I will "
            f"not accept a destination I cannot see. Say anything here to make "
            f"me try again.",
        )
    if not resolved.deliverable:
        reason = "it is already resolved (✔)" if resolved.closed else resolved.reason
        return _needs_input(
            spec, context, watch,
            f"I cannot deliver to `{accepted['destination']}`: {reason}. "
            f"Which conversation should I notify instead?",
        )
    # The destination stops being a name here. What is stored is the id of a
    # message in the conversation the requester meant, so that a rename, a ✔
    # or somebody else taking the freed name cannot move the notification.
    accepted["destination_id"] = resolved.message_id

    context.step = "accepting"
    watch_id = watch.watch_id
    if watch_id is None:
        # Written before the visible post, so the anchor is the first thing in
        # the record and its id is stable no matter what is said afterwards.
        watch_id = context.client.send_to_channel(
            context.channel, context.topic, anchor.watch_note(context.topic)
        )
    name = f"w{watch_id}"
    accepted["watch"] = name
    topic_write(context.topic, anchor.accepted_note(accepted), channel=context.channel, client=context.client)
    topic_write(context.topic, anchor.state_note(anchor.ACTIVE), channel=context.channel, client=context.client)
    store.update(
        spec.local / "watches", name,
        watch=name, channel=context.channel, topic=context.topic,
        state=anchor.ACTIVE, accepted=accepted,
        accepted_at=store.now(), evaluations=0,
    )
    log(f"watch {name} active: {accepted['condition']!r} -> {resolved.conversation}")
    return TopicResult([_accepted_body(name, accepted, resolved)])


def _needs_input(
    spec: AgentSpec, context: TopicContext, watch: anchor.Watch, question: str
) -> TopicResult:
    """One question, and a state that keeps this topic out of the schedule.

    The state note is what stops a half-asked request from being evaluated
    once a minute forever. A watch that was already active and is being
    re-read stays out of the schedule until the answer arrives, which is why
    the store is updated too rather than only the topic.
    """
    topic_write(
        context.topic, anchor.state_note(anchor.NEEDS_INPUT),
        channel=context.channel, client=context.client,
    )
    if watch.watch_id:
        store.update(spec.local / "watches", watch.name, state=anchor.NEEDS_INPUT)
    log(f"watch request in {context.channel!r}/{context.topic!r} needs input: {question}")
    return TopicResult([question])


def handle_watch(spec: AgentSpec, client: ZulipClient, channel: str, topic: str) -> None:
    """Serve one watch topic through the shared skeleton.

    `handoff=False`: the acknowledgement must not name the requester. See the
    module docstring — this is the one line that keeps an accepted watch from
    costing the requester a run.
    """
    log(f"watch topic {channel!r}/{topic!r}")
    serve_topic(
        client, channel, topic, lambda context: serve_intake(spec, context),
        ack_text=SWEEP_ACK,
        empty_reply=EMPTY_REPLY,
        handoff=False,
        exec_options=exec_options_for(spec, client),
    )
