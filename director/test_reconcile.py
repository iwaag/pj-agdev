from __future__ import annotations

import binascii
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

import reconcile


def chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
    )


def png(width: int, height: int) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    pixels = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))
    return reconcile.PNG_SIGNATURE + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")


class ReconcileTests(unittest.TestCase):
    def test_request_image_uses_agforge_contract(self):
        responses = [
            {"request_id": "request-1"},
            {"status": "working", "artifacts": []},
            {
                "status": "done",
                "artifacts": [{"kind": "image", "url": "http://artifact"}],
            },
        ]
        with patch.object(reconcile, "http_json", side_effect=responses), patch.object(
            reconcile.time, "sleep"
        ):
            request_id, url = reconcile.request_image("http://agforge", "desire")
        self.assertEqual(request_id, "request-1")
        self.assertEqual(url, "http://artifact")

    def test_mechanical_check_decodes_png_and_dimensions(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "image.png"
            path.write_bytes(png(2, 3))
            result = reconcile.mechanical_check(
                path, {"format": "png", "width": 2, "height": 3}
            )
            self.assertEqual((result.width, result.height), (2, 3))

    def test_mechanical_check_rejects_dimension_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "image.png"
            path.write_bytes(png(2, 3))
            with self.assertRaisesRegex(reconcile.ReconcileError, "dimension mismatch"):
                reconcile.mechanical_check(
                    path, {"format": "png", "width": 3, "height": 2}
                )

    def test_set_delivered_changes_only_selected_status(self):
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
            reconcile.set_delivered(manifest, "background")
            requests = json.loads(manifest.read_text(encoding="utf-8"))["requests"]
            self.assertEqual(requests[0]["status"], "delivered")
            self.assertEqual(requests[1]["status"], "requested")


if __name__ == "__main__":
    unittest.main()
