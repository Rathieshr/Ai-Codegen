"""Handoff schema helpers."""

from __future__ import annotations

from datetime import datetime, timezone


def handoff_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


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
