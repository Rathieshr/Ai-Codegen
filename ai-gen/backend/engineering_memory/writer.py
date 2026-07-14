"""Engineering Memory writer."""

from __future__ import annotations

from typing import Any

from .indexer import MemoryIndexer
from .policies import MemoryPolicies
from .types import memory_fingerprint, normalize_memory
from .version_manager import MemoryVersionManager


class MemoryWriter:
    def __init__(self) -> None:
        self.policies = MemoryPolicies()
        self.indexer = MemoryIndexer()
        self.versioning = MemoryVersionManager()

    def write(self, memories: list[dict[str, Any]], incoming: dict[str, Any], actor: str = "") -> dict[str, Any]:
        if self._contains_raw_prompt(incoming):
            return {"stored": False, "reason": "Raw prompts cannot become Engineering Memory.", "memory": {}}
        source = incoming.get("source") if isinstance(incoming.get("source"), dict) else incoming
        allowed, reason = self.policies.can_learn_from_source(source)
        if not allowed:
            return {"stored": False, "reason": reason, "memory": {}}
        draft = normalize_memory({**incoming, "approvalStatus": incoming.get("approvalStatus") or "Validated"})
        duplicate = self.find_duplicate(memories, draft)
        if duplicate:
            return {"stored": False, "duplicate": True, "reason": "Duplicate Engineering Memory rejected.", "memory": duplicate}
        indexed = self.indexer.index(draft)
        return {"stored": True, "reason": reason, "memory": indexed}

    @staticmethod
    def _contains_raw_prompt(incoming: dict[str, Any]) -> bool:
        raw_keys = {"rawprompt", "finalprompt", "providerprompt"}
        if any(str(key).replace("_", "").casefold() in raw_keys for key in incoming):
            return True
        content = incoming.get("content")
        if isinstance(content, dict) and any(str(key).replace("_", "").casefold() in raw_keys for key in content):
            return True
        return False

    def update(self, existing: dict[str, Any], incoming: dict[str, Any], actor: str = "") -> dict[str, Any]:
        normalized = normalize_memory(incoming, existing)
        versioned = self.versioning.new_version(existing, normalized, actor)
        return self.indexer.index(versioned)

    def find_duplicate(self, memories: list[dict[str, Any]], incoming: dict[str, Any]) -> dict[str, Any] | None:
        fingerprint = memory_fingerprint(incoming)
        for memory in memories:
            if memory.get("fingerprint") == fingerprint:
                return memory
            same_title = str(memory.get("title", "")).casefold() == str(incoming.get("title", "")).casefold()
            same_category = memory.get("category") == incoming.get("category")
            same_artifact = memory.get("artifactType") == incoming.get("artifactType") and memory.get("artifactId") == incoming.get("artifactId")
            if same_title and same_category and same_artifact:
                return memory
        return None
