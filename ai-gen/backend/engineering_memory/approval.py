"""Approval workflow for Engineering Memory."""

from __future__ import annotations

from typing import Any

from .indexer import MemoryIndexer
from .policies import MemoryPolicies
from .types import now_iso
from .version_manager import MemoryVersionManager


class MemoryApprovalService:
    def __init__(self) -> None:
        self.policies = MemoryPolicies()
        self.versioning = MemoryVersionManager()
        self.indexer = MemoryIndexer()

    def validate(self, memory: dict[str, Any], actor: str = "") -> dict[str, Any]:
        current = memory.get("approvalStatus", "Draft")
        memory["approvalStatus"] = "Validated"
        memory["validatedBy"] = actor or "HEI"
        memory["validatedAt"] = now_iso()
        return self.versioning.record_status_change(memory, current, "Validated", actor)

    def approve(self, memory: dict[str, Any], actor: str = "") -> dict[str, Any]:
        current = memory.get("approvalStatus", "Draft")
        memory["approvalStatus"] = "Approved"
        memory["approvedBy"] = actor or "HEI"
        memory["approvedAt"] = now_iso()
        return self.versioning.record_status_change(memory, current, "Approved", actor)

    def index(self, memory: dict[str, Any], actor: str = "") -> dict[str, Any]:
        current = memory.get("approvalStatus", "Draft")
        memory["approvalStatus"] = "Indexed"
        memory["indexedAt"] = now_iso()
        indexed = self.indexer.index(memory)
        return self.versioning.record_status_change(indexed, current, "Indexed", actor)

    def make_available(self, memory: dict[str, Any], actor: str = "") -> dict[str, Any]:
        current = memory.get("approvalStatus", "Draft")
        memory["approvalStatus"] = "Available"
        memory["availableAt"] = now_iso()
        return self.versioning.record_status_change(memory, current, "Available", actor)
