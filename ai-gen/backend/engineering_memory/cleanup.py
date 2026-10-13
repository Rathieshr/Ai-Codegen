"""Engineering Memory cleanup."""

from __future__ import annotations

from typing import Any

from .types import now_iso


class MemoryCleanup:
    def archive_obsolete(self, memories: list[dict[str, Any]], memory_id: str, actor: str = "") -> dict[str, Any]:
        for memory in memories:
            if memory.get("id") == memory_id:
                previous = memory.get("approvalStatus", "Draft")
                memory["approvalStatus"] = "Archived"
                memory["archivedAt"] = now_iso()
                memory.setdefault("history", []).append(
                    {"event": "archived", "from": previous, "to": "Archived", "actor": actor or "HEI", "timestamp": now_iso()}
                )
                return memory
        raise ValueError(f"Memory {memory_id} was not found.")

    def reduce_stale_confidence(self, memories: list[dict[str, Any]], amount: float = 0.05) -> list[dict[str, Any]]:
        for memory in memories:
            if memory.get("approvalStatus") in {"Deprecated"}:
                memory["confidence"] = max(0.0, float(memory.get("confidence", 0.0)) - amount)
        return memories
