"""Filesystem-backed storage for handoff artifacts."""

from __future__ import annotations

import os
from pathlib import Path

from backend.handoff.markdown_renderer import render_handoff_markdown
from backend.repo_context.storage import read_json, write_json


def handoff_root() -> Path:
    return Path(os.getenv("AI_GEN_HANDOFF_ROOT", ".ai_gen_handoffs"))


def save_handoff(handoff: dict) -> dict:
    """Persist JSON and markdown forms of a handoff artifact."""

    root = handoff_root()
    work_item_id = str(handoff.get("work_item_id", "unknown"))
    stage = str(handoff.get("stage", "stage"))
    version = int(handoff.get("version", 1))
    directory = root / "work_items" / work_item_id
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{stage}_v{version}.json"
    md_path = directory / f"{stage}_v{version}.md"
    write_json(json_path, handoff)
    md_path.write_text(render_handoff_markdown(handoff), encoding="utf-8")

    index_path = root / "index.json"
    index = read_json(index_path, default={}) or {}
    index[handoff["handoff_id"]] = {
        "path": str(json_path),
        "markdown_path": str(md_path),
        "work_item_id": work_item_id,
        "stage": stage,
        "status": handoff.get("status", "draft"),
        "version": version,
    }
    write_json(index_path, index)
    return handoff


def load_handoff(handoff_id: str) -> dict | None:
    """Load a handoff artifact by id."""

    index = read_json(handoff_root() / "index.json", default={}) or {}
    record = index.get(handoff_id)
    if not record:
        return None
    return read_json(record["path"], default=None)


def load_handoff_markdown(handoff_id: str) -> str | None:
    """Load the markdown form of a handoff artifact by id."""

    index = read_json(handoff_root() / "index.json", default={}) or {}
    record = index.get(handoff_id)
    if not record:
        return None
    markdown_path = record.get("markdown_path")
    if markdown_path and Path(markdown_path).exists():
        return Path(markdown_path).read_text(encoding="utf-8")
    json_path = Path(record["path"])
    fallback_path = json_path.with_suffix(".md")
    if fallback_path.exists():
        return fallback_path.read_text(encoding="utf-8")
    handoff = read_json(record["path"], default=None)
    return render_handoff_markdown(handoff) if handoff else None


def latest_handoff(work_item_id: str | int, stage: str = "dev", status: str | None = "approved") -> dict | None:
    """Return the most recent handoff for a work item and stage."""

    work_item_id = str(work_item_id)
    items = [
        item
        for item in list_handoffs(work_item_id)
        if item.get("stage") == stage and (status is None or item.get("status") == status)
    ]
    if not items:
        return None
    items.sort(key=lambda item: int(item.get("version", 0)), reverse=True)
    return items[0]


def list_handoffs(work_item_id: str | int) -> list[dict]:
    """List all stored handoffs for a work item."""

    work_item_id = str(work_item_id)
    directory = handoff_root() / "work_items" / work_item_id
    if not directory.exists():
        return []
    output: list[dict] = []
    for path in sorted(directory.glob("*.json")):
        data = read_json(path, default=None)
        if data:
            output.append(data)
    return output
