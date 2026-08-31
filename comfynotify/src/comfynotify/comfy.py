"""Minimal ComfyUI HTTP reader; all result parsing stays in this module."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class ComfyUnavailable(RuntimeError):
    pass


class ComfyClient:
    def __init__(self, base_url: str, timeout_s: float = 20) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def get_json(self, path: str) -> dict[str, Any]:
        try:
            with urlopen(Request(f"{self.base_url}{path}"), timeout=self.timeout_s) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as error:  # urllib's transport failures vary by platform.
            raise ComfyUnavailable(str(error)) from error
        if not isinstance(data, dict):
            raise ComfyUnavailable(f"{path} did not return a JSON object")
        return data

    def history(self, prompt_id: str) -> dict[str, Any] | None:
        return self.get_json(f"/history/{prompt_id}").get(prompt_id)

    def queue_ids(self) -> set[str]:
        queue = self.get_json("/queue")
        result: set[str] = set()
        for items in (queue.get("queue_running") or [], queue.get("queue_pending") or []):
            for item in items:
                if isinstance(item, list) and len(item) > 1:
                    result.add(str(item[1]))
        return result

    def vram_free(self) -> Any:
        stats = self.get_json("/system_stats")
        devices = stats.get("devices") or []
        return devices[0].get("vram_free") if devices and isinstance(devices[0], dict) else None


def output_references(entry: dict[str, Any]) -> list[dict[str, Any]]:
    references = []
    for node in (entry.get("outputs") or {}).values():
        if not isinstance(node, dict):
            continue
        for value in node.values():
            if isinstance(value, list):
                references.extend(item for item in value if isinstance(item, dict) and item.get("filename"))
    return references


def view_url(base_url: str, reference: dict[str, Any]) -> str:
    query = urlencode({
        "filename": reference["filename"],
        "subfolder": reference.get("subfolder", ""),
        "type": reference.get("type", "output"),
    })
    return f"{base_url.rstrip('/')}/view?{query}"
