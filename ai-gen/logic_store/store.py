"""Small JSON-backed logic store for the MVP."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class LogicStore:
    """Load mock business logic and return query-relevant items."""

    def __init__(self, store_path: Path | None = None) -> None:
        self.store_path = store_path or Path(__file__).with_name("login_flow.json")
        self._items = self._load_items()
        self._items_by_key = self._index_items(self._items)

    def find_relevant(self, query: str) -> list[dict[str, Any]]:
        """Match query text against stored keywords with a conservative fallback."""

        normalized_query = query.lower()
        matches = []
        for item in self._items:
            keywords = [keyword.lower() for keyword in item.get("keywords", [])]
            if any(keyword in normalized_query for keyword in keywords):
                matches.append(self._with_dependencies(item))

        return matches

    def _with_dependencies(self, item: dict[str, Any]) -> dict[str, Any]:
        """Return one flow with its dependent flow records."""

        resolved: list[dict[str, Any]] = []
        linked_flows: list[dict[str, str]] = []
        self._resolve_dependencies(
            item=item,
            resolved=resolved,
            linked_flows=linked_flows,
            visiting=set(),
        )

        combined_item = dict(item)
        combined_item["dependent_flows"] = resolved[1:]
        combined_item["linked_flows"] = linked_flows
        return combined_item

    def _resolve_dependencies(
        self,
        item: dict[str, Any],
        resolved: list[dict[str, Any]],
        linked_flows: list[dict[str, str]],
        visiting: set[str],
    ) -> None:
        """Resolve dependencies recursively while preventing circular loops."""

        item_key = self._item_key(item)
        if item_key in visiting:
            return
        if any(self._item_key(existing) == item_key for existing in resolved):
            return

        visiting.add(item_key)
        resolved.append(item)

        for dependency_name in item.get("depends_on", []):
            dependency = self._items_by_key.get(dependency_name.lower())
            if not dependency:
                continue
            dependency_key = self._item_key(dependency)
            if dependency_key in visiting:
                continue
            link = {
                "from": item.get("name", item_key),
                "to": dependency.get("name", dependency_name),
            }
            if link not in linked_flows:
                linked_flows.append(link)
            self._resolve_dependencies(
                item=dependency,
                resolved=resolved,
                linked_flows=linked_flows,
                visiting=visiting,
            )

        visiting.remove(item_key)

    def _index_items(self, items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Index flows by id and name for simple dependency lookup."""

        index: dict[str, dict[str, Any]] = {}
        for item in items:
            for key in {item.get("id"), item.get("name")}:
                if key:
                    index[str(key).lower()] = item
        return index

    def _item_key(self, item: dict[str, Any]) -> str:
        """Return a stable key for dedupe and cycle detection."""

        return str(item.get("id") or item.get("name") or item)

    def _load_items(self) -> list[dict[str, Any]]:
        """Read logic definitions from disk."""

        with self.store_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        if not isinstance(data, list):
            raise ValueError(f"Logic store must contain a list: {self.store_path}")
        return data
