"""Engineering Memory Engine."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .approval import MemoryApprovalService
from .cleanup import MemoryCleanup
from .diagnostics import MemoryDiagnostics
from .retriever import MemoryRetriever
from .types import normalize_memory, now_iso
from .writer import MemoryWriter


class EngineeringMemoryEngine:
    def __init__(self, storage_path: Path | None = None) -> None:
        data_dir = Path(os.getenv("AI_GEN_DATA_DIR", str(Path(__file__).parent.parent.parent / "data")))
        self._path = storage_path or data_dir / "project_intelligence" / "engineering_memory.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self.writer = MemoryWriter()
        self.approvals = MemoryApprovalService()
        self.retriever = MemoryRetriever()
        self.cleanup = MemoryCleanup()
        self.diagnostics = MemoryDiagnostics()

    def list_memory(self, project_id: str = "", category: str = "", status: str = "") -> dict[str, Any]:
        memories = self._read()
        filtered = [
            memory for memory in memories
            if (not project_id or memory.get("projectId") == project_id)
            and (not category or memory.get("category") == category)
            and (not status or memory.get("approvalStatus") == status)
        ]
        return {"memories": filtered, "count": len(filtered), "diagnostics": self.diagnostics.summarize(filtered)}

    def store_memory(self, memory: dict[str, Any], actor: str = "") -> dict[str, Any]:
        memories = self._read()
        result = self.writer.write(memories, memory, actor)
        if not result.get("stored"):
            return result
        stored = result["memory"]
        memories.append(stored)
        self._write(memories)
        return {"stored": True, "memory": stored, "reason": result.get("reason", "")}

    def update_memory(self, memory_id: str, changes: dict[str, Any], actor: str = "") -> dict[str, Any]:
        memories = self._read()
        for index, memory in enumerate(memories):
            if memory.get("id") == memory_id:
                updated = self.writer.update(memory, {**changes, "id": memory_id}, actor)
                memories[index] = updated
                self._write(memories)
                return {"updated": True, "memory": updated}
        raise ValueError(f"Memory {memory_id} was not found.")

    def validate_memory(self, memory_id: str, actor: str = "") -> dict[str, Any]:
        return self._status_update(memory_id, lambda memory: self.approvals.validate(memory, actor))

    def approve_memory(self, memory_id: str, actor: str = "") -> dict[str, Any]:
        return self._status_update(memory_id, lambda memory: self.approvals.approve(memory, actor))

    def index_memory(self, memory_id: str, actor: str = "") -> dict[str, Any]:
        return self._status_update(memory_id, lambda memory: self.approvals.index(memory, actor))

    def make_available(self, memory_id: str, actor: str = "") -> dict[str, Any]:
        return self._status_update(memory_id, lambda memory: self.approvals.make_available(memory, actor))

    def archive_memory(self, memory_id: str, actor: str = "") -> dict[str, Any]:
        memories = self._read()
        archived = self.cleanup.archive_obsolete(memories, memory_id, actor)
        self._write(memories)
        return {"archived": True, "memory": archived}

    def search(self, query: dict[str, Any]) -> dict[str, Any]:
        memories = self._read()
        return self.retriever.find_relevant_memory(memories, query)

    def find_relevant_memory(self, query: dict[str, Any]) -> dict[str, Any]:
        return self.search(query)

    def find_patterns(self, query: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.retriever.find_patterns(self._read(), query)

    def find_architecture(self, query: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.retriever.find_architecture(self._read(), query)

    def find_planning_history(self, query: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.retriever.find_planning_history(self._read(), query)

    def find_execution_history(self, query: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.retriever.find_execution_history(self._read(), query)

    def find_lessons(self, query: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.retriever.find_lessons(self._read(), query)

    def find_reusable_stories(self, query: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.retriever.find_reusable_stories(self._read(), query)

    def detect_patterns(self) -> dict[str, Any]:
        memories = self._read()
        module_pairs: dict[str, int] = {}
        for memory in memories:
            modules = memory.get("index", {}).get("modules", []) if isinstance(memory.get("index"), dict) else []
            for left in modules:
                for right in modules:
                    if left < right:
                        key = f"{left} + {right}"
                        module_pairs[key] = module_pairs.get(key, 0) + 1
        patterns = [
            {"title": key, "count": count, "category": "Pattern Memory"}
            for key, count in sorted(module_pairs.items(), key=lambda item: item[1], reverse=True)
            if count > 1
        ]
        return {"patterns": patterns, "count": len(patterns)}

    def diagnostics_summary(self) -> dict[str, Any]:
        return self.diagnostics.summarize(self._read())

    def _status_update(self, memory_id: str, updater: Any) -> dict[str, Any]:
        memories = self._read()
        for index, memory in enumerate(memories):
            if memory.get("id") == memory_id:
                updated = updater(memory)
                updated["updatedAt"] = now_iso()
                memories[index] = normalize_memory(updated, updated)
                self._write(memories)
                return {"updated": True, "memory": memories[index]}
        raise ValueError(f"Memory {memory_id} was not found.")

    def _read(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            memories = payload.get("memories") if isinstance(payload, dict) else []
            return [normalize_memory(memory, memory) for memory in memories if isinstance(memory, dict)]
        except (OSError, json.JSONDecodeError):
            return []

    def _write(self, memories: list[dict[str, Any]]) -> None:
        self._path.write_text(
            json.dumps({"schemaVersion": "engineering-memory-v1", "memories": memories, "updatedAt": now_iso()}, indent=2),
            encoding="utf-8",
        )
