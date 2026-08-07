from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import director


class DirectorTests(unittest.TestCase):
    def context(self, root: Path) -> director.Context:
        direction = root / "direction"
        direction.mkdir()
        (direction / "brief.md").write_text("Medieval Othello.", encoding="utf-8")
        game = root / "game"
        (game / "assets").mkdir(parents=True)
        manifest = game / "assets" / "manifest.json"
        manifest.write_text(
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
        return director.load_context(direction, manifest, "background")

    def test_compose_requires_technical_contract_in_desire(self):
        with tempfile.TemporaryDirectory() as temporary:
            context = self.context(Path(temporary))
            with patch.object(
                director,
                "run_question",
                return_value=(' {"desire":"medieval oil painting, PNG, 1024x1024"} ', {"cost": 1}),
            ):
                answer, meta = director.compose(context)
            self.assertEqual(answer["desire"], "medieval oil painting, PNG, 1024x1024")
            self.assertEqual(meta, {"cost": 1})

    def test_compose_rejects_missing_dimensions(self):
        with tempfile.TemporaryDirectory() as temporary:
            context = self.context(Path(temporary))
            with patch.object(
                director,
                "run_question",
                return_value=(' {"desire":"medieval PNG"} ', {}),
            ):
                with self.assertRaises(director.DirectorError):
                    director.compose(context)

    def test_review_uses_only_manifest_declared_asset(self):
        with tempfile.TemporaryDirectory() as temporary:
            context = self.context(Path(temporary))
            asset = director.expected_asset_path(context)
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"placeholder")
            with patch.object(
                director,
                "run_question",
                return_value=(' {"accepted":true,"reason":"Roughly matches."} ', {}),
            ) as question:
                answer, _ = director.review(context)
            self.assertTrue(answer["accepted"])
            self.assertIn(str(asset), question.call_args.args[1])
            self.assertTrue(question.call_args.kwargs["allow_read"])

    def test_backend_runs_with_direction_as_working_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            context = self.context(Path(temporary))
            completed = subprocess_result('{"result":"{}","total_cost_usd":0.1}')
            with patch.object(director.subprocess, "run", return_value=completed) as run:
                text, meta = director.run_question(context, "question")
            self.assertEqual(text, "{}")
            self.assertEqual(meta["total_cost_usd"], 0.1)
            self.assertEqual(run.call_args.kwargs["cwd"], context.direction)


def subprocess_result(stdout: str):
    class Result:
        returncode = 0
        stderr = ""

    result = Result()
    result.stdout = stdout
    return result


if __name__ == "__main__":
    unittest.main()
