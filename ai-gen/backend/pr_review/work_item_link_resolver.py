"""Resolve PR-linked work items from supplied request data."""

from __future__ import annotations

from typing import Any

from backend.implementation_validation.models import clean, unique


class WorkItemLinkResolver:
    def resolve(self, pull_request: dict[str, Any] | None = None, linked_work_items: list[Any] | None = None) -> list[dict[str, Any]]:
        pull_request = pull_request or {}
        raw_items = linked_work_items or pull_request.get("linked_work_items") or pull_request.get("linkedWorkItems") or pull_request.get("workItems") or []
        items: list[dict[str, Any]] = []
        for item in raw_items:
            if isinstance(item, dict):
                items.append(
                    {
                        "id": item.get("id") or item.get("workItemId") or item.get("work_item_id"),
                        "type": clean(item.get("type") or item.get("workItemType") or item.get("work_item_type")),
                        "title": clean(item.get("title") or item.get("name")),
                        "url": clean(item.get("url")),
                    }
                )
            elif clean(item):
                items.append({"id": clean(item), "type": "", "title": "", "url": ""})
        seen = set()
        result = []
        for item in items:
            key = str(item.get("id") or item.get("url") or item.get("title"))
            if key and key not in seen:
                seen.add(key)
                result.append(item)
        return result

    def diagnostics(self, linked_items: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "linkedWorkItemCount": len(linked_items),
            "linkedWorkItemTypes": unique([clean(item.get("type")) for item in linked_items]),
        }
