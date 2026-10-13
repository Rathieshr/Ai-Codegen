"""Persistence for the latest interpreted response per execution session."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.platform.shared import JsonMapStore


class ResponseInterpretationRepository:
    def __init__(self, store: JsonMapStore) -> None:
        self.store = store

    def save(self, interpretation: dict[str, Any]) -> dict[str, Any]:
        values = self.store.read()
        values[interpretation["sessionId"]] = deepcopy(interpretation)
        self.store.write(values)
        return deepcopy(interpretation)

    def get(self, session_id: str) -> dict[str, Any] | None:
        value = self.store.read().get(session_id)
        return deepcopy(value) if isinstance(value, dict) else None
