"""Canonical Engineering Command Center workspace models."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


THEMES = {"system", "light", "dark", "high-contrast"}
DENSITIES = {"comfortable", "compact"}
ROLES = {"admin", "contributor", "viewer"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_preferences(user_id: str = "current-user") -> dict[str, Any]:
    return {
        "userId": user_id or "current-user",
        "theme": "system",
        "density": "comfortable",
        "sidebarCollapsed": False,
        "defaultWorkspace": "overview",
        "notificationsEnabled": True,
        "commandPaletteEnabled": True,
        "updatedAt": now_iso(),
    }


def normalize_preferences(value: dict[str, Any], user_id: str) -> dict[str, Any]:
    result = {**default_preferences(user_id), **deepcopy(value), "userId": user_id or "current-user", "updatedAt": now_iso()}
    theme = str(result.get("theme") or "system").lower()
    density = str(result.get("density") or "comfortable").lower()
    if theme not in THEMES:
        raise ValueError(f"theme must be one of: {', '.join(sorted(THEMES))}.")
    if density not in DENSITIES:
        raise ValueError(f"density must be one of: {', '.join(sorted(DENSITIES))}.")
    result["theme"] = theme
    result["density"] = density
    result["sidebarCollapsed"] = bool(result.get("sidebarCollapsed"))
    result["notificationsEnabled"] = bool(result.get("notificationsEnabled", True))
    result["commandPaletteEnabled"] = bool(result.get("commandPaletteEnabled", True))
    return result


def normalize_role(role: str) -> str:
    value = str(role or "viewer").strip().lower()
    return value if value in ROLES else "viewer"
