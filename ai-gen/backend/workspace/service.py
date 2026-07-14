"""Engineering Command Center workspace application service."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.platform.shared import JsonMapStore

from .models import default_preferences, normalize_preferences, normalize_role, now_iso
from .navigation import NavigationService


class WorkspaceService:
    def __init__(self, store: JsonMapStore, *, navigation: NavigationService | None = None, platform: Any | None = None) -> None:
        self.store = store
        self.navigation = navigation or NavigationService()
        self.platform = platform

    def get_workspace(self, user_id: str, role: str) -> dict[str, Any]:
        normalized_role = normalize_role(role)
        preferences = self.get_preferences(user_id)
        navigation = self.navigation.get_navigation(normalized_role)
        allowed = {item["id"] for item in navigation["items"] if item.get("enabled")}
        if preferences["defaultWorkspace"] not in allowed:
            preferences["defaultWorkspace"] = "overview"
        return {
            "workspaceId": "hei-engineering-command-center",
            "name": "Engineering Command Center",
            "description": "Engineering Operating Console",
            "version": "7.10",
            "currentUser": {"userId": user_id or "current-user", "role": normalized_role},
            "preferences": preferences,
            "navigation": navigation["items"],
            "capabilities": {
                "globalSearch": True, "commandPalette": True, "workspaceSwitcher": True,
                "notifications": True, "statusBar": True, "themes": ["system", "light", "dark", "high-contrast"],
                "keyboardNavigation": True, "lazyLoading": True, "caching": True,
                "virtualization": True, "backgroundRefresh": True, "realTimeNotifications": True,
            },
            "status": {"state": "Ready", "message": "HEI services available", "checkedAt": now_iso()},
            "notifications": [],
        }

    def get_preferences(self, user_id: str) -> dict[str, Any]:
        key = user_id or "current-user"
        stored = self.store.read().get(key)
        return normalize_preferences(stored if isinstance(stored, dict) else default_preferences(key), key)

    def update_preferences(self, user_id: str, changes: dict[str, Any], role: str) -> dict[str, Any]:
        key = user_id or "current-user"
        current = self.get_preferences(key)
        value = normalize_preferences({**current, **deepcopy(changes)}, key)
        navigation = self.navigation.get_navigation(role)
        valid = {item["id"] for item in navigation["items"] if item.get("enabled")}
        if value["defaultWorkspace"] not in valid:
            raise ValueError("defaultWorkspace is not available for the current role.")
        records = self.store.read(); records[key] = value; self.store.write(records)
        if self.platform:
            self.platform.audit.record({"action": "WorkspacePreferencesUpdated", "actor": key, "source": "API", "targetType": "WorkspacePreferences", "targetId": key, "before": current, "after": value})
        return value

    def record_diagnostic(self, value: dict[str, Any]) -> dict[str, Any]:
        event_type = str(value.get("eventType") or "HubDiagnostic")
        correlation_id = str(value.get("correlationId") or "")
        project_id = str(value.get("projectId") or "")
        metadata = dict(value.get("metadata") or {})
        if self.platform:
            self.platform.events.publish({
                "eventType": event_type,
                "source": "CommandCenter",
                "projectId": project_id,
                "correlationId": correlation_id,
                "payload": metadata,
            })
            self.platform.activity.add_activity({
                "activityType": "CommandCenter",
                "title": event_type,
                "description": str(value.get("message") or "HEI hub diagnostic recorded."),
                "source": "CommandCenter",
                "projectId": project_id,
                "correlationId": correlation_id,
                "metadata": metadata,
            })
        return {"recorded": True, "eventType": event_type, "correlationId": correlation_id}

    def get_navigation(self, role: str) -> dict[str, Any]:
        return self.navigation.get_navigation(role)
