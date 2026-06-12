"""Append-only JSONL audit trail for the ai-gen pipeline.

Every approval, ADO automation event, and stage transition is appended
to a single JSONL file.  Each line is a complete JSON object.

Schema of each event line:
  {
    "event_id":    "evt_<12hex>",
    "event_type":  "stage_approved" | "ado_automation" | "pipeline_created" | ...,
    "timestamp":   "2026-06-12T08:00:00Z",
    "pipeline_id": "pipeline_abc123",
    "stage":       "ba",          // optional
    "actor":       "azure_devops",// who triggered it
    "details":     { ... }        // event-specific payload
  }
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_DEFAULT_AUDIT_FILE = os.environ.get(
    "AI_GEN_AUDIT_FILE",
    str(Path(__file__).parent.parent.parent / "data" / "audit.jsonl"),
)


def _audit_path() -> Path:
    path = Path(_DEFAULT_AUDIT_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:12]}"


# ── Public API ────────────────────────────────────────────────────────────────

def record_event(
    event_type: str,
    pipeline_id: str,
    actor: str = "system",
    stage: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one audit event to the JSONL file and return it."""
    event: dict[str, Any] = {
        "event_id": _new_event_id(),
        "event_type": event_type,
        "timestamp": _utc_now(),
        "pipeline_id": pipeline_id,
        "actor": actor,
    }
    if stage is not None:
        event["stage"] = stage
    if details:
        event["details"] = details

    _append_event(event)
    return event


def get_events(
    pipeline_id: str | None = None,
    event_type: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Read and filter events from the JSONL file.

    Results are newest-first. Filtering is done in-memory since the file
    is expected to be small (< 50k lines for typical installations).
    """
    path = _audit_path()
    if not path.exists():
        return []

    results: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if pipeline_id and event.get("pipeline_id") != pipeline_id:
                    continue
                if event_type and event.get("event_type") != event_type:
                    continue
                results.append(event)
    except OSError:
        return []

    # Newest-first, capped at limit
    return list(reversed(results))[:limit]


def get_summary(pipeline_id: str | None = None) -> dict[str, Any]:
    """Return aggregate counts per event_type."""
    events = get_events(pipeline_id=pipeline_id, limit=10_000)
    counts: dict[str, int] = {}
    latest: dict[str, str] = {}
    for event in events:
        etype = str(event.get("event_type") or "unknown")
        counts[etype] = counts.get(etype, 0) + 1
        ts = str(event.get("timestamp") or "")
        if ts and ts > latest.get(etype, ""):
            latest[etype] = ts

    return {
        "total_events": len(events),
        "pipeline_id": pipeline_id,
        "by_event_type": [
            {"event_type": k, "count": v, "latest_at": latest.get(k)}
            for k, v in sorted(counts.items(), key=lambda x: x[1], reverse=True)
        ],
    }


# ── Private helpers ───────────────────────────────────────────────────────────

def _append_event(event: dict[str, Any]) -> None:
    """Write one JSON line to the audit file atomically."""
    path = _audit_path()
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        # Never let audit failures break the pipeline
        pass
