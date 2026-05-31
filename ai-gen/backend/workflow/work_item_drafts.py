"""Draft work item helpers for planning-oriented workflow templates."""

from __future__ import annotations

import re
from typing import Any


def make_draft_id(source_stage: str, title: str, index: int, parent_draft_id: str | None = None) -> str:
    base = _slug(title) or f"draft_{index}"
    if parent_draft_id:
        return f"draft_{_slug(source_stage)}_{_slug(parent_draft_id)}_{base}_{index}"
    return f"draft_{_slug(source_stage)}_{base}_{index}"


def make_work_item_draft(
    *,
    draft_id: str,
    parent_work_item_id: str | int | None,
    draft_type: str,
    title: str,
    description: str,
    acceptance_criteria: list[str] | None = None,
    tags: list[str] | None = None,
    area_path: str | None = None,
    iteration_path: str | None = None,
    parent_draft_id: str | None = None,
    child_drafts: list[dict[str, Any]] | None = None,
    source_stage: str,
    status: str = "draft",
    azure_work_item_id: int | None = None,
) -> dict[str, Any]:
    return {
        "draft_id": draft_id,
        "parent_work_item_id": str(parent_work_item_id) if parent_work_item_id is not None else None,
        "draft_type": draft_type,
        "title": title.strip(),
        "description": description.strip(),
        "acceptance_criteria": [item.strip() for item in acceptance_criteria or [] if str(item).strip()],
        "tags": [item.strip() for item in tags or [] if str(item).strip()],
        "area_path": (area_path or "").strip(),
        "iteration_path": (iteration_path or "").strip(),
        "parent_draft_id": parent_draft_id,
        "child_drafts": [dict(item) for item in child_drafts or []],
        "source_stage": source_stage,
        "status": status,
        "azure_work_item_id": azure_work_item_id,
    }


def flatten_drafts(drafts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = []
    for draft in drafts:
        item = dict(draft)
        children = [dict(child) for child in item.pop("child_drafts", [])]
        flat.append({**item, "child_drafts": children})
        flat.extend(flatten_drafts(children))
    return flat


def normalize_drafts(drafts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for draft in flatten_drafts(drafts):
        seen[draft["draft_id"]] = draft
    return list(seen.values())


def build_story_drafts_from_epic_or_feature(
    work_item: dict[str, Any],
    *,
    source_stage: str,
    flows: list[str],
    variants: list[str],
    fields: list[str],
    include_ui: bool,
    count: int = 3,
) -> list[dict[str, Any]]:
    area_path = _field(work_item, "areaPath", "area_path")
    iteration_path = _field(work_item, "iterationPath", "iteration_path")
    tags = _tags(work_item)
    subject = _title(work_item)
    outputs: list[dict[str, Any]] = []
    for index in range(1, count + 1):
        story_title = f"{subject}: Slice {index}"
        story_id = make_draft_id(source_stage, story_title, index)
        story = make_work_item_draft(
            draft_id=story_id,
            parent_work_item_id=work_item.get("id") or work_item.get("work_item_id"),
            draft_type="User Story",
            title=story_title,
            description=f"As an end user, I want the {subject.lower()} workflow slice {index} so the overall delivery can be implemented safely.",
            acceptance_criteria=_story_acceptance(subject, flows, fields, index),
            tags=tags,
            area_path=area_path,
            iteration_path=iteration_path,
            source_stage=source_stage,
        )
        story["child_drafts"] = _child_task_drafts(
            story,
            source_stage=source_stage,
            include_ui=include_ui,
            variants=variants,
            fields=fields,
        )
        outputs.append(story)
    return outputs


def build_child_task_drafts_for_story(
    work_item: dict[str, Any],
    *,
    source_stage: str,
    title_seed: str,
    include_ui: bool,
    fields: list[str],
    variants: list[str],
) -> list[dict[str, Any]]:
    area_path = _field(work_item, "areaPath", "area_path")
    iteration_path = _field(work_item, "iterationPath", "iteration_path")
    tags = _tags(work_item)
    parent_work_item_id = work_item.get("id") or work_item.get("work_item_id")
    story_draft = make_work_item_draft(
        draft_id=make_draft_id(source_stage, title_seed, 1),
        parent_work_item_id=parent_work_item_id,
        draft_type="Task",
        title=f"Plan delivery for {title_seed}",
        description=f"Coordinate the implementation plan for {title_seed.lower()} before execution begins.",
        acceptance_criteria=[
            "Execution scope is small and well-defined.",
            "Dependencies and ownership are clear.",
        ],
        tags=tags,
        area_path=area_path,
        iteration_path=iteration_path,
        source_stage=source_stage,
    )
    return _child_task_drafts(
        story_draft,
        source_stage=source_stage,
        include_ui=include_ui,
        variants=variants,
        fields=fields,
    )


def build_create_requests(drafts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for draft in drafts:
        requests.append(
            {
                "draft_id": draft["draft_id"],
                "type": draft["draft_type"],
                "fields": {
                    "System.Title": draft["title"],
                    "System.Description": draft["description"],
                    "Microsoft.VSTS.Common.AcceptanceCriteria": "<br/>".join(
                        f"<div>{item}</div>" for item in draft.get("acceptance_criteria", [])
                    ),
                    "System.Tags": "; ".join(draft.get("tags", [])),
                    "System.AreaPath": draft.get("area_path") or None,
                    "System.IterationPath": draft.get("iteration_path") or None,
                },
                "parent_link": {
                    "parent_work_item_id": draft.get("parent_work_item_id"),
                    "parent_draft_id": draft.get("parent_draft_id"),
                },
            }
        )
    return requests


def mark_drafts_created(drafts: list[dict[str, Any]], created_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    created_map = {
        str(item.get("draft_id")): int(item["azure_work_item_id"])
        for item in created_items
        if item.get("draft_id") and item.get("azure_work_item_id") is not None
    }
    updated: list[dict[str, Any]] = []
    for draft in drafts:
        item = dict(draft)
        draft_id = str(item.get("draft_id", ""))
        if draft_id in created_map:
            item["status"] = "created"
            item["azure_work_item_id"] = created_map[draft_id]
        updated.append(item)
    return updated


def approve_drafts(drafts: list[dict[str, Any]], draft_ids: list[str]) -> list[dict[str, Any]]:
    selected = {str(item) for item in draft_ids}
    updated: list[dict[str, Any]] = []
    for draft in drafts:
        item = dict(draft)
        if item.get("draft_id") in selected and item.get("status") == "draft":
            item["status"] = "approved"
        updated.append(item)
    return updated


def _child_task_drafts(
    parent_story: dict[str, Any],
    *,
    source_stage: str,
    include_ui: bool,
    variants: list[str],
    fields: list[str],
) -> list[dict[str, Any]]:
    child_drafts: list[dict[str, Any]] = []
    parent_title = str(parent_story.get("title", "")).strip()
    parent_id = parent_story["draft_id"]
    shared = {
        "parent_work_item_id": None,
        "parent_draft_id": parent_id,
        "tags": list(parent_story.get("tags", [])),
        "area_path": parent_story.get("area_path"),
        "iteration_path": parent_story.get("iteration_path"),
        "source_stage": source_stage,
    }
    if include_ui:
        child_drafts.append(
            make_work_item_draft(
                draft_id=make_draft_id(source_stage, f"UI {parent_title}", 1, parent_id),
                draft_type="Task",
                title=f"UI: {parent_title}",
                description=f"Design and implement the UI structure for {parent_title.lower()}, including fields and states.",
                acceptance_criteria=[
                    "UI structure reflects the approved story scope.",
                    f"Fields are covered: {', '.join(fields) or 'required interaction fields'}.",
                ],
                **shared,
            )
        )
    child_drafts.append(
        make_work_item_draft(
            draft_id=make_draft_id(source_stage, f"Dev {parent_title}", 2, parent_id),
            draft_type="Task",
            title=f"DEV: {parent_title}",
            description=f"Implement the approved behavior for {parent_title.lower()} with minimal scope.",
            acceptance_criteria=[
                "Implementation follows the approved execution scope.",
                f"Variant behavior is respected: {', '.join(variants) or 'default flow'}.",
            ],
            **shared,
        )
    )
    child_drafts.append(
        make_work_item_draft(
            draft_id=make_draft_id(source_stage, f"QA {parent_title}", 3, parent_id),
            draft_type="Task",
            title=f"QA: {parent_title}",
            description=f"Validate the delivered behavior for {parent_title.lower()} and capture regression coverage.",
            acceptance_criteria=[
                "Positive, negative, and edge validation is documented.",
                "Regression risks are covered before closure.",
            ],
            **shared,
        )
    )
    return child_drafts


def _story_acceptance(subject: str, flows: list[str], fields: list[str], index: int) -> list[str]:
    return [
        f"Story slice {index} supports the {', '.join(flows) or 'target'} workflow without widening scope.",
        f"Required fields are handled correctly: {', '.join(fields) or 'core inputs'}.",
        f"The {subject.lower()} behavior is clear enough for downstream task creation.",
    ]


def _title(work_item: dict[str, Any]) -> str:
    return str(work_item.get("title") or work_item.get("Title") or "Planned Delivery").strip()


def _field(work_item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(work_item.get(key, "")).strip()
        if value:
            return value
    return ""


def _tags(work_item: dict[str, Any]) -> list[str]:
    values = work_item.get("tags", [])
    if isinstance(values, list):
        return [str(item).strip() for item in values if str(item).strip()]
    return []


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
