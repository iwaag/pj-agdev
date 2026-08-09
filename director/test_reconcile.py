from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import director
import reconcile
from test_director import workspace


def png(width: int, height: int) -> bytes:
    return (
        director.PNG_SIGNATURE
        + b"\x00\x00\x00\x0dIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
    )


class MechanicsTests(unittest.TestCase):
    def test_request_image_uses_the_agforge_contract(self):
        responses = [
            {"request_id": "request-1"},
            {"status": "working", "artifacts": []},
            {"status": "done", "artifacts": [{"kind": "image", "url": "http://artifact"}]},
        ]
        with patch.object(reconcile, "http_json", side_effect=responses), patch.object(
            reconcile.time, "sleep"
        ):
            request_id, url = reconcile.request_image("http://agforge", "desire")
        self.assertEqual((request_id, url), ("request-1", "http://artifact"))

    def test_set_delivered_changes_only_the_named_entry(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "requests": [
                            {"id": "background", "status": "requested"},
                            {"id": "other", "status": "requested"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            previous = reconcile.set_delivered(manifest, "background")
            requests = json.loads(manifest.read_text(encoding="utf-8"))["requests"]
            self.assertEqual(previous, "requested")
            self.assertEqual(requests[0]["status"], "delivered")
            self.assertEqual(requests[1]["status"], "requested")

    def test_persist_envelopes_writes_readable_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            direction = Path(temporary)
            payload = {"request": "bg", "attempts": [], "verdict": "in_progress"}
            path = reconcile.persist_envelopes(direction, "bg", payload)
            self.assertEqual(path, direction / "reviews" / "bg.envelopes.json")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), payload)


class DecisionTests(unittest.TestCase):
    def test_decision_line_is_parsed(self):
        for line, expected in (
            ("DECISION: deliver — close enough", "deliver"),
            ("DECISION: retry - warmer light", "retry"),
            ("DECISION: stop — needs a human", "stop"),
        ):
            self.assertEqual(reconcile.parse_decision("prose\n" + line)[0], expected)

    def test_a_reply_without_a_decision_line_parses_to_none(self):
        self.assertEqual(reconcile.parse_decision("I like it.")[0], None)


class FlowTests(unittest.TestCase):
    """The whole point of the rewrite: the director decides, the harness obeys."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.space = workspace(Path(self.temporary.name))
        self.replies: list[str] = []

    def tearDown(self):
        self.temporary.cleanup()

    def run_flow(self, replies, budget=5, image=None):
        self.replies = list(replies)
        asked = []

        def fake_answer(text, space, extra=None):
            asked.append(extra.get("purpose") if extra else None)
            return {
                "id": f"director/run-{len(asked):04d}",
                "outcome": "done",
                "reply": self.replies.pop(0),
            }

        def fake_request_image(url, desire):
            return "agforge-1", "http://artifact"

        def fake_download(url, destination):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(image if image is not None else png(1024, 1024))

        with patch.object(director, "answer", side_effect=fake_answer), patch.object(
            reconcile, "request_image", side_effect=fake_request_image
        ), patch.object(reconcile, "download", side_effect=fake_download):
            result = reconcile.reconcile(
                self.space.direction, self.space.manifest, "background", "http://agforge", budget
            )
        return result, asked

    def test_a_wrong_sized_image_is_delivered_when_the_director_says_so(self):
        """The old harness aborted here. The dimension mismatch is now a note
        in front of the director, and its judgment is final."""
        result, _ = self.run_flow(
            ["a medieval hall", "Size is off but the mood is right.\nDECISION: deliver — mood wins"],
            image=png(512, 512),
        )
        self.assertEqual(result["verdict"], "delivered")
        self.assertIn("512", result["attempts"][0]["observed"])
        self.assertTrue(result["attempts"][0]["differences"])
        delivered = json.loads(self.space.manifest.read_text(encoding="utf-8"))
        self.assertEqual(delivered["requests"][0]["status"], "delivered")

    def test_the_director_can_retry_more_than_twice(self):
        """The old harness stopped after exactly two attempts."""
        replies = ["desire 0"]
        for _ in range(3):
            replies += ["Not yet.\nDECISION: retry — warmer", "a warmer medieval hall"]
        replies += ["Now it is right.\nDECISION: deliver — good"]
        result, _ = self.run_flow(replies, budget=5)
        self.assertEqual(result["verdict"], "delivered")
        self.assertEqual(len(result["attempts"]), 4)

    def test_the_attempt_budget_is_recorded_as_the_harness_stopping_the_director(self):
        replies = ["desire 0"]
        for _ in range(3):
            replies += ["Again.\nDECISION: retry — again", "another desire"]
        result, _ = self.run_flow(replies, budget=2)
        self.assertIn("attempt budget", result["verdict"])
        self.assertEqual(len(result["attempts"]), 2)

    def test_a_generation_failure_is_handed_to_the_director_verbatim(self):
        asked = []

        def fake_answer(text, space, extra=None):
            asked.append((extra or {}).get("purpose"))
            if (extra or {}).get("purpose") == "review-failure":
                self.assertIn("SwarmUI exploded", text)
                return {"id": "r", "outcome": "done", "reply": "DECISION: stop — infra is down"}
            return {"id": "r", "outcome": "done", "reply": "a desire"}

        with patch.object(director, "answer", side_effect=fake_answer), patch.object(
            reconcile,
            "request_image",
            side_effect=reconcile.ReconcileError("agforge job x failed: SwarmUI exploded"),
        ):
            result = reconcile.reconcile(
                self.space.direction, self.space.manifest, "background", "http://agforge"
            )
        self.assertIn("generation failure", result["verdict"])
        self.assertIn("review-failure", asked)

    def test_a_missing_decision_line_stops_rather_than_guessing(self):
        result, _ = self.run_flow(["a desire", "I am honestly not sure about this one."])
        self.assertIn("no decision line", result["verdict"])
        manifest = json.loads(self.space.manifest.read_text(encoding="utf-8"))
        self.assertEqual(manifest["requests"][0]["status"], "requested")

    def test_compose_omissions_are_advisories_not_errors(self):
        result, _ = self.run_flow(
            ["a medieval hall with no numbers in it", "DECISION: deliver — fine"]
        )
        self.assertEqual(result["verdict"], "delivered")
        self.assertTrue(any("1024" in note for note in result["compose_advisories"]))


if __name__ == "__main__":
    unittest.main()
