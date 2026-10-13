"""Handoff schema helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import re


def handoff_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_handoff_id(work_item_id: str | int, stage: str, version: int) -> str:
    """Build a stable, URL-safe handoff id."""

    safe_work_item_id = _slug(str(work_item_id))
    safe_stage = _slug(stage)
    return f"handoff_{safe_work_item_id}_{safe_stage}_v{max(version, 1)}"


def default_handoff(
    handoff_id: str,
    pipeline_id: str,
    work_item_id: str,
    stage: str,
    version: int,
    source_stage: str,
    target_stages: list[str],
) -> dict:
    """Create the base handoff object before content is attached."""

    return {
        "handoff_id": handoff_id,
        "pipeline_id": pipeline_id,
        "work_item_id": str(work_item_id),
        "stage": stage,
        "handoff_type": "generic_handoff",
        "version": version,
        "status": "draft",
        "created_at": handoff_timestamp(),
        "approved_at": None,
        "source_stage": source_stage,
        "target_stages": target_stages,
        "summary": "",
        "content": {},
        "refinement": {},
        "repo_context": {},
        "constraints": [],
        "open_questions": [],
        "next_actions": [],
    }


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip().lower())
    normalized = normalized.strip("._-")
    return normalized or "unknown"
