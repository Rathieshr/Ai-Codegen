"""Lifecycle audit helpers."""

from __future__ import annotations

from typing import Any


class LifecycleAudit:
    def summarize(self, history: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "eventCount": len(history),
            "lastEvent": history[-1] if history else {},
            "actors": sorted({str(item.get("actor")) for item in history if item.get("actor")}),
        }
