"""failsafe p3: the monitor's side of the consolidated recovery path."""

from __future__ import annotations

from agag.post import PROGRESS as PROGRESS_INTENT, REPORT, PostMeta, compose
from agag.reply import failure_line

from test_failsafe_reproductions import ACK, CHANNEL, DEV, FRONT, OBS
from test_health_path import asked, incident_posts, post, world  # noqa: F401 - the fixture


def test_a_request_left_unanswered_by_two_failed_replies_goes_to_the_owners(world):
    """p2's #12509 without its luck: Front's listener served the Developer's
    question twice and neither run produced a usable reply. Asking Front a
    third time buys a third run of the same failure; the owners are told."""
    case = world("running")
    watcher = case.make()
    question = post(case, "front", case.desk, "And which file changed?", DEV, after=100)
    post(case, "front", case.desk, ACK, FRONT)
    post(case, "front", case.desk, compose(f"@**Developer**\n\n{failure_line('no block', final=False)}",
                                            PostMeta(intent=PROGRESS_INTENT)), FRONT)
    again = post(case, "front", case.desk, ACK, FRONT, after=25)
    post(case, "front", case.desk, compose(f"@**Developer**\n\n{failure_line('no block')}",
                                            PostMeta(intent=REPORT, end=again)), FRONT)
    watcher.tick()
    assert not [p for p in incident_posts(case) if "could not answer" in p], "not before its 60 s"
    for _ in range(3):
        case.clock.now += 60
        watcher.tick()
    said = [p for p in incident_posts(case) if "could not answer its requester" in p]
    reports = [p for p in said if "Stopped: I could not get this moving" in p]
    assert len(reports) == 1 and reports[0].startswith("@**Developer**"), "reported once, to the owners by name"
    assert len(said) == 2, "and handed to a developer review once"
    assert not asked(case), "Front is not asked a third time"
    assert question
