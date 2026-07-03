"""Versioning for Engineering Memory."""

from __future__ import annotations

from typing import Any

from .types import now_iso


class MemoryVersionManager:
    def new_version(self, existing: dict[str, Any], updated: dict[str, Any], actor: str = "") -> dict[str, Any]:
        if existing.get("approvalStatus") in {"Approved", "Indexed", "Available"}:
            updated["version"] = int(existing.get("version") or 1) + 1
            updated["approvalStatus"] = "Draft"
            updated["history"] = [
                *(existing.get("history") or []),
                {
                    "event": "version_created",
                    "fromVersion": existing.get("version", 1),
                    "toVersion": updated["version"],
                    "actor": actor or "HEI",
                    "timestamp": now_iso(),
                },
            ]
            return updated
        updated["version"] = int(existing.get("version") or 1)
        updated["history"] = existing.get("history", [])
        return updated

    def record_status_change(self, memory: dict[str, Any], from_status: str, to_status: str, actor: str = "") -> dict[str, Any]:
        memory.setdefault("history", []).append(
            {
                "event": "status_changed",
                "from": from_status,
                "to": to_status,
                "actor": actor or "HEI",
                "timestamp": now_iso(),
            }
        )
        return memory
