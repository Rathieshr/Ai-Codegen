"""JSON persistence for Azure DevOps action packs and event receipts."""

from __future__ import annotations

from typing import Any

from backend.platform.shared import JsonMapStore

from .models import AzureDevOpsActionPack


class AzureDevOpsAgentRepository:
    def __init__(self, packs: JsonMapStore, receipts: JsonMapStore) -> None:
        self._packs = packs
        self._receipts = receipts

    def save(self, pack: AzureDevOpsActionPack) -> AzureDevOpsActionPack:
        values = self._packs.read()
        values[pack.pack_id] = pack.to_dict()
        self._packs.write(values)
        return pack

    def get(self, pack_id: str) -> AzureDevOpsActionPack | None:
        value = self._packs.read().get(pack_id)
        return AzureDevOpsActionPack.from_dict(value) if isinstance(value, dict) else None

    def list(self) -> list[AzureDevOpsActionPack]:
        return [AzureDevOpsActionPack.from_dict(value) for value in self._packs.read().values() if isinstance(value, dict)]

    def reserve_event(self, event_id: str, metadata: dict[str, Any]) -> bool:
        values = self._receipts.read()
        if values.get(event_id):
            return False
        values[event_id] = metadata
        self._receipts.write(values)
        return True

    def receipt(self, event_id: str) -> dict[str, Any] | None:
        return self._receipts.read().get(event_id)

    def complete_event(self, event_id: str, run_id: str, pack_id: str) -> None:
        values = self._receipts.read()
        value = values.get(event_id) or {}
        values[event_id] = {**value, "runId": run_id, "packId": pack_id, "status": "Completed"}
        self._receipts.write(values)
