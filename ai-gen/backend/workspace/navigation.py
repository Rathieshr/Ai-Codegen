"""Role-aware navigation for the Engineering Operating Console."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .models import normalize_role


NAVIGATION: tuple[dict[str, Any], ...] = (
    {"id": "overview", "label": "Overview", "target": "overview", "icon": "home", "roles": ["admin", "contributor", "viewer"]},
    {"id": "planning", "label": "Planning", "target": "planning", "icon": "plan", "roles": ["admin", "contributor", "viewer"]},
    {"id": "repository", "label": "Repository", "target": "admin", "icon": "repository", "roles": ["admin"]},
    {"id": "execution", "label": "Execution", "target": "execution", "icon": "execute", "roles": ["admin", "contributor", "viewer"]},
    {"id": "approvals", "label": "Approvals", "target": "governance", "icon": "approval", "roles": ["admin", "contributor"]},
    {"id": "azure-devops", "label": "Azure DevOps", "target": "admin", "icon": "azure", "roles": ["admin", "contributor", "viewer"]},
    {"id": "agents", "label": "Agents", "target": "agents", "icon": "agents", "roles": ["admin", "contributor"]},
    {"id": "activity", "label": "Activity", "target": "diagnostics", "icon": "activity", "roles": ["admin", "contributor", "viewer"]},
    {"id": "health", "label": "Health", "target": "diagnostics", "icon": "health", "roles": ["admin", "contributor", "viewer"]},
    {"id": "settings", "label": "Settings", "target": "admin", "icon": "settings", "roles": ["admin"]},
    {"id": "portfolio", "label": "Portfolio", "target": "overview", "icon": "portfolio", "roles": ["admin", "contributor", "viewer"], "future": True, "enabled": False},
    {"id": "memory", "label": "Memory", "target": "memory", "icon": "memory", "roles": ["admin", "contributor", "viewer"]},
    {"id": "administration", "label": "Administration", "target": "admin", "icon": "admin", "roles": ["admin"]},
)


class NavigationService:
    def get_navigation(self, role: str) -> dict[str, Any]:
        normalized = normalize_role(role)
        items = []
        for position, source in enumerate(NAVIGATION):
            if normalized not in source["roles"]:
                continue
            item = deepcopy(source)
            item.setdefault("enabled", True)
            item["position"] = position
            item["lazy"] = item["id"] != "overview"
            item.pop("roles", None)
            items.append(item)
        return {"role": normalized, "items": items, "count": len(items)}
