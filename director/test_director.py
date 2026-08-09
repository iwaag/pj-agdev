from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import director


def workspace(root: Path, *, manifest: bool = True) -> director.Workspace:
    direction = root / "direction"
    direction.mkdir()
    (direction / "brief.md").write_text("Medieval Othello.", encoding="utf-8")
    (direction / "persona.md").write_text("You are Hal, a terse art director.", encoding="utf-8")
    if not manifest:
        return director.load_workspace(direction)
    game = root / "game"
    (game / "assets").mkdir(parents=True)
    path = game / "assets" / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "requests": [
                    {
                        "id": "background",
                        "path": "assets/bg/background.png",
                        "format": "png",
                        "width": 1024,
                        "height": 1024,
                        "status": "requested",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return director.load_workspace(direction, path)


class WorkspaceTests(unittest.TestCase):
    def test_persona_is_every_markdown_file_in_the_direction_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            space = workspace(Path(temporary))
            self.assertIn("Medieval Othello.", space.persona)
            self.assertIn("terse art director", space.persona)
            self.assertIn("persona.md", space.persona)

    def test_a_manifest_is_optional(self):
        with tempfile.TemporaryDirectory() as temporary:
            space = workspace(Path(temporary), manifest=False)
            self.assertIsNone(space.manifest)
            self.assertEqual(space.context_root, space.direction)

    def test_unreadable_manifest_is_a_note_not_a_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "direction").mkdir()
            (root / "direction" / "brief.md").write_text("brief", encoding="utf-8")
            (root / "game" / "assets").mkdir(parents=True)
            broken = root / "game" / "assets" / "manifest.json"
            broken.write_text("{not json", encoding="utf-8")
            space = director.load_workspace(root / "direction", broken)
            self.assertIsNone(space.manifest_doc)
            self.assertTrue(space.notes)

    def test_context_root_widens_to_hold_direction_and_game(self):
        with tempfile.TemporaryDirectory() as temporary:
            space = workspace(Path(temporary))
            root = space.context_root
            self.assertTrue(str(space.direction).startswith(str(root)))
            self.assertTrue(str(space.game_root).startswith(str(root)))


class AdvisoryTests(unittest.TestCase):
    """The clamps are information now — none of them raise."""

    def test_dimension_mismatch_is_reported_not_raised(self):
        notes = director.compare_to_manifest(
            {"format": "png", "width": 512, "height": 512},
            {"format": "png", "width": 1024, "height": 1024},
        )
        self.assertEqual(len(notes), 2)
        self.assertIn("width", notes[0])

    def test_format_mismatch_is_reported_not_raised(self):
        notes = director.compare_to_manifest({"format": "jpeg"}, {"format": "png"})
        self.assertIn("jpeg", notes[0])

    def test_inspect_survives_a_file_that_is_not_an_image(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "junk.png"
            path.write_bytes(b"definitely not a png")
            self.assertEqual(director.inspect_image(path)["format"], "unknown")

    def test_inspect_reads_png_dimensions(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "tiny.png"
            header = director.PNG_SIGNATURE + b"\x00" * 4 + b"IHDR"
            path.write_bytes(header + (7).to_bytes(4, "big") + (3).to_bytes(4, "big"))
            inspected = director.inspect_image(path)
            self.assertEqual((inspected["width"], inspected["height"]), (7, 3))


class VerdictTests(unittest.TestCase):
    def test_marker_line_becomes_structure(self):
        parsed = director.parse_verdict("It reads false.\nVERDICT: fail — John would not say that")
        self.assertFalse(parsed["pass"])
        self.assertIn("John", parsed["reason"])

    def test_prose_without_a_marker_is_not_a_failure(self):
        self.assertIsNone(director.parse_verdict("I think it works, but ask me again tomorrow."))

    def test_last_marker_wins(self):
        parsed = director.parse_verdict("VERDICT: fail — no\nrethinking\nVERDICT: pass — yes")
        self.assertTrue(parsed["pass"])


class AnswerTests(unittest.TestCase):
    def test_answer_records_backend_cost_and_reply(self):
        with tempfile.TemporaryDirectory() as temporary:
            space = workspace(Path(temporary))
            with patch.dict(director.os.environ, {"DIRECTOR_BACKEND": "claude"}), patch.object(
                director, "run_claude", return_value=("Yes.\nVERDICT: pass — fits", {"model": "m", "cost_usd": 0.02})
            ):
                record = director.answer("Would John say this?", space)
            self.assertEqual(record["outcome"], "done")
            self.assertEqual(record["backend_model"], "claude/m")
            self.assertEqual(record["cost_usd"], 0.02)
            self.assertTrue(record["verdict"]["pass"])
            written = json.loads((space.direction / "records" / "run-0001.json").read_text())
            self.assertEqual(written["id"], record["id"])

    def test_backend_failure_becomes_a_failed_record_in_the_backends_words(self):
        with tempfile.TemporaryDirectory() as temporary:
            space = workspace(Path(temporary))
            with patch.dict(director.os.environ, {"DIRECTOR_BACKEND": "ollama"}), patch.object(
                director, "run_ollama", side_effect=director.DirectorError("ollama is unreachable")
            ):
                record = director.answer("hello", space)
            self.assertEqual(record["outcome"], "failed")
            self.assertEqual(record["backend"], "ollama")
            self.assertIn("unreachable", record["failure"])
            self.assertTrue((space.direction / "records" / "run-0001.json").is_file())

    def test_the_prompt_carries_the_persona_and_the_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            space = workspace(Path(temporary))
            with patch.dict(director.os.environ, {"DIRECTOR_BACKEND": "claude"}), patch.object(
                director, "run_claude", return_value=("ok", {"model": "m"})
            ) as backend:
                director.answer("what is delivered?", space)
            prompt = backend.call_args.args[0]
        self.assertIn("terse art director", prompt)
        self.assertIn("background", prompt)
        self.assertIn("what is delivered?", prompt)
        # Entrance Guide: the card is in the prompt, so cost questions are
        # answered from measurements rather than from the model's imagination
        # (it guessed "free" the first time this was run live).
        self.assertIn("entrance guide", prompt.lower())
        self.assertIn("Agent ≠ Model", prompt)

    def test_default_backend_is_the_strong_one(self):
        with patch.dict(director.os.environ, {}, clear=True):
            self.assertEqual(director.backend_name(), "claude")

    def test_unknown_backend_is_refused(self):
        with patch.dict(director.os.environ, {"DIRECTOR_BACKEND": "telepathy"}):
            with self.assertRaises(director.DirectorError):
                director.backend_name()


class ClaudePointerTests(unittest.TestCase):
    def test_a_glob_pointer_resolves_to_the_newest_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, mtime in (("v1", 1000), ("v2", 2000)):
                path = root / f"claude-{name}"
                path.write_text("#!/bin/sh\n", encoding="utf-8")
                director.os.utime(path, (mtime, mtime))
            with patch.dict(director.os.environ, {"DIRECTOR_CLAUDE_CMD": f"{root}/claude-*"}):
                self.assertTrue(director.claude_bin().endswith("claude-v2"))

    def test_a_plain_path_is_used_as_given(self):
        with patch.dict(director.os.environ, {"DIRECTOR_CLAUDE_CMD": "/opt/claude"}):
            self.assertEqual(director.claude_bin(), "/opt/claude")


if __name__ == "__main__":
    unittest.main()
