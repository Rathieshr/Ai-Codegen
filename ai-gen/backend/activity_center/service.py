"""Chronological, read-only projection of HEI engineering activity."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable


CATEGORIES = (
    "Repository Sync", "Planning", "Execution", "Prompt", "Runtime", "Validation",
    "QA", "Memory", "ADO", "Approvals", "PR", "Notifications", "Activity",
)
_REDACTED_KEYS = ("password", "secret", "token", "credential", "authorization", "pat", "rawresponse")


class ActivityCenterError(RuntimeError):
    def __init__(self, message: str, *, code: str = "activity_error", status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class ActivityCenterService:
    """Projects existing stores without executing or mutating lifecycle work."""

    def __init__(
        self,
        *,
        platform: Any,
        intelligence_trace: Any | None = None,
        runtime_observability: Any | None = None,
        governance_audit: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.platform = platform
        self.intelligence_trace = intelligence_trace
        self.runtime_observability = runtime_observability
        self.governance_audit = governance_audit

    def list(self, *, search: str = "", category: str = "", status: str = "", source: str = "", correlation_id: str = "", offset: int = 0, limit: int = 100) -> dict[str, Any]:
        values = self._all()
        query = search.strip().casefold()
        values = [item for item in values if (
            (not category or item["category"].casefold() == category.casefold())
            and (not status or item["status"].casefold() == status.casefold())
            and (not source or item["source"].casefold() == source.casefold())
            and (not correlation_id or item["correlationId"] == correlation_id)
            and (not query or query in _search_text(item))
        )]
        total = len(values)
        bounded_limit = max(1, min(int(limit or 100), 250))
        bounded_offset = max(0, int(offset or 0))
        page = values[bounded_offset:bounded_offset + bounded_limit]
        return {
            "activity": page,
            "count": len(page),
            "total": total,
            "offset": bounded_offset,
            "limit": bounded_limit,
            "hasMore": bounded_offset + len(page) < total,
            "categories": list(CATEGORIES),
            "summary": _summary(values),
        }

    def get(self, activity_id: str) -> dict[str, Any]:
        item = next((value for value in self._all() if value["activityId"] == activity_id), None)
        if not item:
            raise ActivityCenterError("Activity record not found.", code="activity_not_found", status=404)
        return {"activity": item}

    def correlation(self, correlation_id: str) -> dict[str, Any]:
        correlation_id = str(correlation_id or "").strip()
        if not correlation_id:
            raise ActivityCenterError("Correlation ID is required.", code="correlation_required")
        items = [value for value in self._all() if value["correlationId"] == correlation_id]
        if not items:
            raise ActivityCenterError("Correlation trace not found.", code="correlation_not_found", status=404)
        items.sort(key=lambda value: value["occurredAt"])
        return {
            "correlationId": correlation_id,
            "activity": items,
            "count": len(items),
            "stages": _ordered_unique([item["category"] for item in items]),
            "startedAt": items[0]["occurredAt"],
            "completedAt": items[-1]["occurredAt"],
            "status": "Needs Attention" if any(_is_failure(item["status"]) for item in items) else "Complete",
        }

    def replay(self, activity_id: str) -> dict[str, Any]:
        item = self.get(activity_id)["activity"]
        trace = self.correlation(item["correlationId"]) if item.get("correlationId") else None
        return {
            "replayed": True,
            "replayMode": "ViewOnly",
            "sideEffects": False,
            "message": "Historical activity reconstructed. No engineering operation was executed.",
            "activity": item,
            "correlationTrace": trace,
        }

    def _all(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        records.extend(self._records("PlatformActivity", self._safe(lambda: self.platform.activity.list_recent(limit=5000)), "activity"))
        records.extend(self._records("PlatformEvent", self._safe(lambda: self.platform.events.list_recent(limit=5000)), "events"))
        records.extend(self._records("PlatformAudit", self._safe(lambda: self.platform.audit.list_recent(limit=5000)), "events"))
        records.extend(self._records("Notification", self._safe(lambda: self.platform.notifications.list_recent(limit=5000)), "notifications"))
        if self.intelligence_trace:
            records.extend(self._records("IntelligenceTrace", self._safe(self.intelligence_trace.list_traces), "traces"))
        if self.runtime_observability:
            records.extend(self._runtime_records(self._safe(lambda: self.runtime_observability.list(limit=500))))
        if self.governance_audit:
            records.extend(self._records("GovernanceAudit", self._safe(self.governance_audit), "events"))
        unique = {record["activityId"]: record for record in records}
        return sorted(unique.values(), key=lambda value: value["occurredAt"], reverse=True)

    def _safe(self, action: Callable[[], Any]) -> dict[str, Any]:
        try:
            value = action()
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    def _records(self, source_type: str, payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
        values = payload.get(key) if isinstance(payload.get(key), list) else []
        return [_normalize(source_type, value) for value in values if isinstance(value, dict)]

    def _runtime_records(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for trace in payload.get("traces") or []:
            if not isinstance(trace, dict):
                continue
            for stage in trace.get("timeline") or []:
                if not isinstance(stage, dict):
                    continue
                output.append(_normalize("RuntimeTrace", {**stage, "id": f"{trace.get('traceId')}:{stage.get('stage')}", "traceId": trace.get("traceId"), "correlationId": trace.get("correlationId"), "sessionId": trace.get("sessionId"), "provider": (trace.get("metrics") or {}).get("provider"), "model": (trace.get("metrics") or {}).get("model")}))
        return output


def _normalize(source_type: str, value: dict[str, Any]) -> dict[str, Any]:
    source_id = _first(value, "activityId", "eventId", "auditId", "notificationId", "traceId", "id")
    event_type = _first(value, "eventType", "activityType", "type", "action", "decision", "stage", "title") or source_type
    occurred_at = _first(value, "createdAt", "time", "when", "updatedAt", "completedAt", "startedAt", "generatedAt") or datetime.now(timezone.utc).isoformat()
    correlation_id = _first(value, "correlationId", "correlation_id") or _nested(value, "metadata", "correlationId")
    details = _sanitize(value)
    if not source_id:
        source_id = hashlib.sha256(json.dumps(details, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    title = _first(value, "title", "decision", "action", "stage", "eventType", "activityType") or _humanize(event_type)
    summary = _first(value, "description", "message", "reason") or _payload_summary(value)
    status = _status(value, event_type)
    category = _category(source_type, f"{event_type} {title} {summary}")
    artifact_type = _first(value, "artifactType", "targetType") or _nested(value, "payload", "artifactType")
    artifact_id = _first(value, "artifactId", "targetId", "workItemId") or _nested(value, "payload", "artifactId")
    return {
        "activityId": f"{source_type}:{source_id}",
        "category": category,
        "eventType": event_type,
        "title": _humanize(title),
        "summary": summary or "No additional details recorded.",
        "status": status,
        "source": _first(value, "source") or source_type,
        "sourceType": source_type,
        "sourceId": source_id,
        "actor": _first(value, "actor", "who") or "system",
        "artifactType": artifact_type,
        "artifactId": artifact_id,
        "correlationId": correlation_id,
        "occurredAt": occurred_at,
        "replayable": True,
        "replayMode": "ViewOnly",
        "details": details,
    }


def _category(source_type: str, text: str) -> str:
    lowered = text.casefold()
    if source_type == "Notification": return "Notifications"
    if any(word in lowered for word in ("azure devops", "azuredevops", "ado ", "work item synchronized", "sprint intelligence")): return "ADO"
    if any(word in lowered for word in ("repository", "snapshot", "scan", "sync", "graph refresh")): return "Repository Sync"
    if "prompt" in lowered or "token optimization" in lowered: return "Prompt"
    if any(word in lowered for word in ("runtime", "provider called", "response received", "interpreted", "engineering diff")): return "Runtime"
    if "validation" in lowered or "compliance" in lowered: return "Validation"
    if any(word in lowered for word in ("qa", "test", "coverage", "release readiness")): return "QA"
    if "memory" in lowered: return "Memory"
    if any(word in lowered for word in ("pull request", "pr candidate", "pr comment")): return "PR"
    if any(word in lowered for word in ("approval", "approved", "rejected")): return "Approvals"
    if any(word in lowered for word in ("execution", "implementation package", "manifest")): return "Execution"
    if any(word in lowered for word in ("planning", "epic", "feature", "story", "task", "capability")): return "Planning"
    return "Activity"


def _status(value: dict[str, Any], event_type: str) -> str:
    status = _first(value, "status", "severity", "outcome")
    if status: return _humanize(status)
    lowered = event_type.casefold()
    if any(word in lowered for word in ("failed", "blocked", "error", "rejected", "timedout")): return "Failed"
    if any(word in lowered for word in ("completed", "approved", "ready", "created", "posted", "merged")): return "Completed"
    if any(word in lowered for word in ("started", "requested", "queued", "received")): return "In Progress"
    return "Recorded"


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): "[redacted]" if any(term in str(key).casefold() for term in _REDACTED_KEYS) else _sanitize(item) for key, item in value.items()}
    if isinstance(value, list): return [_sanitize(item) for item in value]
    return value


def _payload_summary(value: dict[str, Any]) -> str:
    payload = value.get("payload") if isinstance(value.get("payload"), dict) else {}
    return str(payload.get("message") or payload.get("reason") or payload.get("title") or "")


def _search_text(item: dict[str, Any]) -> str:
    return " ".join(str(item.get(key) or "") for key in ("category", "eventType", "title", "summary", "status", "source", "actor", "artifactType", "artifactId", "correlationId")).casefold()


def _summary(values: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(values),
        "needsAttention": sum(1 for item in values if _is_failure(item["status"])),
        "correlations": len({item["correlationId"] for item in values if item["correlationId"]}),
        "categories": {category: sum(1 for item in values if item["category"] == category) for category in CATEGORIES if any(item["category"] == category for item in values)},
    }


def _is_failure(status: str) -> bool:
    return any(word in status.casefold() for word in ("fail", "block", "error", "critical", "reject", "timeout"))


def _humanize(value: Any) -> str:
    text = str(value or "").replace("_", " ").replace("-", " ")
    output = []
    for index, char in enumerate(text):
        if index and char.isupper() and text[index - 1].islower(): output.append(" ")
        output.append(char)
    return " ".join("".join(output).split()).strip()


def _first(value: dict[str, Any], *keys: str) -> str:
    for key in keys:
        item = value.get(key)
        if item is not None and str(item).strip(): return str(item).strip()
    return ""


def _nested(value: dict[str, Any], parent: str, key: str) -> str:
    nested = value.get(parent)
    return str(nested.get(key) or "").strip() if isinstance(nested, dict) else ""


def _ordered_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
