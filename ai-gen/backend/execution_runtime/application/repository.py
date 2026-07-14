"""Persistent session repository for the AI Execution Runtime."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.platform.shared import JsonMapStore


class ExecutionRuntimeRepository:
    def __init__(self, store: JsonMapStore) -> None:
        self.store = store

    def save(self, session: dict[str, Any]) -> dict[str, Any]:
        sessions = self.store.read()
        sessions[session["sessionId"]] = deepcopy(session)
        self.store.write(sessions)
        return deepcopy(session)

    def get(self, session_id: str) -> dict[str, Any] | None:
        value = self.store.read().get(session_id)
        return deepcopy(value) if isinstance(value, dict) else None

    def find_by_idempotency_key(self, idempotency_key: str) -> dict[str, Any] | None:
        if not idempotency_key:
            return None
        for value in self.store.read().values():
            if isinstance(value, dict) and value.get("idempotencyKey") == idempotency_key:
                return deepcopy(value)
        return None
