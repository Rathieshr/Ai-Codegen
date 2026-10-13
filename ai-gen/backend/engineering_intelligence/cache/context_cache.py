"""Small in-process cache for immutable context versions."""

from __future__ import annotations

from typing import Any


class ContextCache:
    def __init__(self) -> None:
        self._values: dict[str, dict[str, Any]] = {}

    def get(self, version: str) -> dict[str, Any] | None:
        value = self._values.get(version)
        return dict(value) if value else None

    def put(self, version: str, context: dict[str, Any]) -> None:
        self._values[version] = dict(context)

    def clear(self) -> None:
        self._values.clear()
