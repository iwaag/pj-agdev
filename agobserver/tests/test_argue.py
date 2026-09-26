"""Observer in an argue (`argue` p1): the new mention route answers an
argue invitation through the shared participation and nothing else — the
loop the devenv notes warned about (Front thanking Observer by name) stays
closed because a `front-` topic is not an argue."""

from agobserver import argue, listener


class Client:
    def whoami(self):
        return {"user_id": 23, "full_name": "agobserver-agstudio1"}


def test_an_argue_invitation_is_answered_by_the_shared_participation(monkeypatch):
    seen = {}
    monkeypatch.setattr(argue, "participate", lambda client, channel, topic, **kw: seen.update(kw, topic=topic) or [1])
    monkeypatch.setattr(argue, "role_context", lambda: "ROLE")
    argue.handle_mention(Client(), "argue", "argue-fish")
    assert seen["topic"] == "argue-fish" and seen["spec"] is listener.SPEC and seen["role_context"] == "ROLE"


def test_a_thank_you_in_a_front_topic_is_not_an_invitation(monkeypatch):
    monkeypatch.setattr(argue, "participate", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("ran")))
    argue.handle_mention(Client(), "front", "front-observer-p1")


def test_the_argue_role_is_reading_only_on_the_paid_model():
    from pathlib import Path
    from agag.agent_config import load_config, resolve_role

    config, overlay = load_config(listener.SPEC.agents_config, Path("/nonexistent"))
    role = resolve_role(config, overlay, "argue", check_available=False)
    # Reading tools plus the read-only shared-context reader (give_context_easier p1).
    assert role.allowed_tools == "Read,Glob,Grep,Bash(agrefs:*)" and role.harness == "claude_code"
