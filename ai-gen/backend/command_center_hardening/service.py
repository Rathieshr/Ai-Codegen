"""Bounded, cached operational health aggregation for Command Center V1."""

from __future__ import annotations

import os
import resource
import sys
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from time import monotonic, perf_counter
from typing import Any, Callable


class CommandCenterHardeningService:
    def __init__(self, *, platform: Any, sdk: Any | None = None, service_probes: dict[str, Callable[[], Any]] | None = None, cache_ttl_seconds: float = 10.0, version: str = "7.10") -> None:
        self.platform = platform
        self.sdk = sdk
        self.service_probes = service_probes or {}
        self.cache_ttl_seconds = max(1.0, float(cache_ttl_seconds))
        self.version = version
        self._cache: dict[str, Any] | None = None
        self._cached_at = 0.0
        self._lock = RLock()

    def snapshot(self, *, force: bool = False, include_diagnostics: bool = False) -> dict[str, Any]:
        with self._lock:
            age = monotonic() - self._cached_at
            if not force and self._cache is not None and age < self.cache_ttl_seconds:
                value = deepcopy(self._cache)
                value["cache"] = {"status": "Hit", "ageMs": round(age * 1000, 2), "ttlSeconds": self.cache_ttl_seconds}
                return value if include_diagnostics else _without_internal_diagnostics(value)
            value = self._build()
            self._cache = deepcopy(value)
            self._cached_at = monotonic()
            value["cache"] = {"status": "Miss", "ageMs": 0.0, "ttlSeconds": self.cache_ttl_seconds}
            return value if include_diagnostics else _without_internal_diagnostics(value)

    def _build(self) -> dict[str, Any]:
        started = perf_counter()
        latencies: dict[str, float] = {}
        warnings: list[dict[str, str]] = []

        health = self._probe("platform", self.platform.platform_health, {}, latencies, warnings)
        jobs_payload = self._probe("jobs", lambda: self.platform.jobs.list_recent(limit=1000), {"jobs": [], "count": 0}, latencies, warnings)
        events_payload = self._probe("events", lambda: self.platform.events.list_recent(limit=500), {"events": [], "count": 0}, latencies, warnings)
        notifications_payload = self._probe("notifications", lambda: self.platform.notifications.list_recent(limit=50), {"notifications": [], "count": 0}, latencies, warnings)
        activity_payload = self._probe("activity", lambda: self.platform.activity.list_recent(limit=100), {"activity": [], "count": 0}, latencies, warnings)
        audit_payload = self._probe("audit", lambda: self.platform.audit.list_recent(limit=100), {"events": [], "count": 0}, latencies, warnings)
        agents_payload = self._probe("agentRuntime", lambda: self.platform.agent_runs.list_recent(limit=500), {"runs": [], "count": 0}, latencies, warnings)
        extra_services = {name: self._probe(name, probe, {}, latencies, warnings) for name, probe in self.service_probes.items()}

        jobs = _items(jobs_payload, "jobs")
        events = _items(events_payload, "events")
        notifications = _items(notifications_payload, "notifications")
        activity = _items(activity_payload, "activity")
        audit = _items(audit_payload, "events")
        agent_runs = _items(agents_payload, "runs")
        status_counts = Counter(str(item.get("status") or "Unknown") for item in jobs)
        queue_depth = sum(status.casefold() in {"queued", "pending"} for status in status_counts.elements())
        running = sum(status.casefold() in {"running", "inprogress"} for status in status_counts.elements())
        failed = sum(status.casefold() in {"failed", "error"} for status in status_counts.elements())
        unread = [item for item in notifications if not item.get("readAt")]
        storage = _storage(self.platform.storage_root)
        memory = _memory()
        service_rows = _services(health, extra_services, latencies, warnings)
        overall = "Degraded" if failed or warnings or any(item["status"] in {"Degraded", "Unavailable"} for item in service_rows) else "Healthy"
        total_latency = round((perf_counter() - started) * 1000, 2)

        return {
            "schemaVersion": "hei-command-center-hardening-v1",
            "version": self.version,
            "status": overall,
            "platformHealth": health,
            "jobs": {"total": int(jobs_payload.get("count") or len(jobs)), "running": running, "queued": queue_depth, "failed": failed, "byStatus": dict(status_counts), "recent": jobs[:20]},
            "queues": {"depth": queue_depth, "running": running, "failed": failed, "health": "Attention" if failed else "Healthy"},
            "events": {"total": int(events_payload.get("count") or len(events)), "recent": events[:20], "byType": dict(Counter(str(item.get("eventType") or "Unknown") for item in events))},
            "sdk": {"name": "HEI Platform SDK", "status": "Ready" if self.sdk is not None else "Not Registered", "contract": "Service Contracts", "transport": "Backend APIs", "methodCount": _public_method_count(self.sdk)},
            "services": service_rows,
            "performance": {"snapshotLatencyMs": total_latency, "serviceLatencyMs": latencies, "slowestService": max(latencies, key=latencies.get) if latencies else "", "refreshMode": "Background", "cacheEnabled": True},
            "storage": storage,
            "database": {"type": "JSON Document Store", "status": storage["status"], "persistent": True, "files": storage["fileCount"]},
            "memory": memory,
            "notifications": {"total": int(notifications_payload.get("count") or len(notifications)), "unread": len(unread), "items": unread[:10]},
            "diagnostics": {"warnings": warnings, "activityRecords": int(activity_payload.get("count") or len(activity)), "auditRecords": int(audit_payload.get("count") or len(audit)), "agentRuns": int(agents_payload.get("count") or len(agent_runs)), "probeCount": 7 + len(extra_services)},
            "cache": {"status": "Miss", "ageMs": 0.0, "ttlSeconds": self.cache_ttl_seconds},
            "generatedAt": _now(),
        }

    @staticmethod
    def _probe(name: str, action: Callable[[], Any], fallback: Any, latencies: dict[str, float], warnings: list[dict[str, str]]) -> Any:
        started = perf_counter()
        try:
            value = action()
            return value if value is not None else fallback
        except Exception as error:
            warnings.append({"service": name, "code": "unavailable", "message": str(error) or f"{name} is unavailable."})
            return fallback
        finally:
            latencies[name] = round((perf_counter() - started) * 1000, 2)


def _without_internal_diagnostics(value: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(value)
    result["diagnostics"] = {"warningCount": len((result.get("diagnostics") or {}).get("warnings") or []), "available": True, "adminOnly": True}
    return result


def _items(payload: Any, key: str) -> list[dict[str, Any]]:
    values = payload.get(key) if isinstance(payload, dict) else []
    return [item for item in values if isinstance(item, dict)] if isinstance(values, list) else []


def _services(health: dict[str, Any], extras: dict[str, Any], latencies: dict[str, float], warnings: list[dict[str, str]]) -> list[dict[str, Any]]:
    rows = []
    for key, raw in (health.items() if isinstance(health, dict) else []):
        if not key.casefold().endswith("status"): continue
        status = _service_status(raw)
        rows.append({"id": key.removesuffix("Status"), "name": _humanize(key.removesuffix("Status")), "status": status, "latencyMs": latencies.get("platform", 0.0)})
    unavailable = {item["service"] for item in warnings}
    for name in extras:
        rows.append({"id": name, "name": _humanize(name), "status": "Unavailable" if name in unavailable else "Healthy", "latencyMs": latencies.get(name, 0.0)})
    return rows


def _service_status(value: Any) -> str:
    text = str(value or "Unknown").casefold()
    if text in {"healthy", "ready", "completed", "active"}: return "Healthy"
    if text in {"not_registered", "not configured", "pending"}: return "Not Registered"
    if text in {"failed", "error", "unavailable", "critical"}: return "Unavailable"
    return "Degraded"


def _storage(root: Path) -> dict[str, Any]:
    try:
        files = [path for path in Path(root).rglob("*") if path.is_file()]
        size = sum(path.stat().st_size for path in files)
        return {"status": "Healthy", "fileCount": len(files), "bytesUsed": size, "megabytesUsed": round(size / 1_048_576, 3), "writable": os.access(root, os.W_OK)}
    except OSError:
        return {"status": "Unavailable", "fileCount": 0, "bytesUsed": 0, "megabytesUsed": 0.0, "writable": False}


def _memory() -> dict[str, Any]:
    usage = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    bytes_used = usage if sys.platform == "darwin" else usage * 1024
    return {"status": "Healthy", "processMegabytes": round(bytes_used / 1_048_576, 2), "metric": "Peak RSS"}


def _public_method_count(value: Any) -> int:
    if value is None: return 0
    return sum(1 for name in dir(value) if not name.startswith("_") and callable(getattr(value, name, None)))


def _humanize(value: str) -> str:
    output = []
    for index, char in enumerate(str(value or "")):
        if index and char.isupper() and str(value)[index - 1].islower(): output.append(" ")
        output.append(char)
    return "".join(output).strip().title()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
