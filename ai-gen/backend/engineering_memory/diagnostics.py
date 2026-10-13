"""Engineering Memory diagnostics."""

from __future__ import annotations

from collections import Counter
from typing import Any


class MemoryDiagnostics:
    def summarize(self, memories: list[dict[str, Any]]) -> dict[str, Any]:
        categories = Counter(memory.get("category", "Project Memory") for memory in memories)
        statuses = Counter(memory.get("approvalStatus", "Draft") for memory in memories)
        return {
            "total": len(memories),
            "categories": dict(categories),
            "statuses": dict(statuses),
            "available": statuses.get("Available", 0) + statuses.get("Indexed", 0),
            "draft": statuses.get("Draft", 0),
            "approved": statuses.get("Approved", 0),
        }
