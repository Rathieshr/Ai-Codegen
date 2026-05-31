"""Draft work item helpers for planning-oriented workflow templates."""

from __future__ import annotations

import hashlib
import re
from typing import Any


def make_draft_id(source_stage: str, title: str, index: int, parent_draft_id: str | None = None) -> str:
    base = _slug(title) or f"draft_{index}"
    seed = f"{source_stage}|{parent_draft_id or ''}|{title}|{index}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
    if parent_draft_id:
        return f"draft_{_slug(source_stage)}_{_slug(parent_draft_id)}_{base}_{index}_{digest}"
    return f"draft_{_slug(source_stage)}_{base}_{index}_{digest}"


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
    selected: bool = True,
    status: str = "draft",
    azure_work_item_id: int | None = None,
    creation_error: str | None = None,
) -> dict[str, Any]:
    children = [normalize_draft(dict(item)) for item in child_drafts or []]
    draft = {
        "id": draft_id,
        "draft_id": draft_id,
        "type": draft_type,
        "draft_type": draft_type,
        "title": title.strip(),
        "description": description.strip(),
        "acceptance_criteria": [item.strip() for item in acceptance_criteria or [] if str(item).strip()],
        "tags": [item.strip() for item in tags or [] if str(item).strip()],
        "area_path": (area_path or "").strip(),
        "iteration_path": (iteration_path or "").strip(),
        "parent_draft_id": parent_draft_id,
        "parent_work_item_id": str(parent_work_item_id) if parent_work_item_id is not None else None,
        "children": children,
        "child_drafts": children,
        "source_stage": source_stage,
        "selected": bool(selected),
        "status": status,
        "azure_work_item_id": azure_work_item_id,
        "creation_error": creation_error,
    }
    return draft


def normalize_draft(draft: dict[str, Any]) -> dict[str, Any]:
    children = [normalize_draft(dict(item)) for item in draft.get("children") or draft.get("child_drafts") or [] if isinstance(item, dict)]
    draft_id = str(draft.get("draft_id") or draft.get("id") or "").strip()
    draft_type = str(draft.get("draft_type") or draft.get("type") or "Task").strip() or "Task"
    normalized = {
        "id": draft_id,
        "draft_id": draft_id,
        "type": draft_type,
        "draft_type": draft_type,
        "title": str(draft.get("title", "")).strip(),
        "description": str(draft.get("description", "")).strip(),
        "acceptance_criteria": [str(item).strip() for item in draft.get("acceptance_criteria", []) if str(item).strip()],
        "tags": [str(item).strip() for item in draft.get("tags", []) if str(item).strip()],
        "area_path": str(draft.get("area_path", "")).strip(),
        "iteration_path": str(draft.get("iteration_path", "")).strip(),
        "parent_draft_id": _clean_optional_text(draft.get("parent_draft_id")),
        "parent_work_item_id": _clean_optional_text(draft.get("parent_work_item_id")),
        "children": children,
        "child_drafts": children,
        "source_stage": str(draft.get("source_stage", "")).strip(),
        "selected": bool(draft.get("selected", True)),
        "status": str(draft.get("status", "draft")).strip() or "draft",
        "azure_work_item_id": draft.get("azure_work_item_id"),
        "creation_error": _clean_optional_text(draft.get("creation_error")),
    }
    return normalized


def flatten_drafts(drafts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = []
    for draft in drafts:
        item = normalize_draft(dict(draft))
        flat.append({**item, "children": [], "child_drafts": []})
        flat.extend(flatten_drafts(item.get("children", [])))
    return flat


def normalize_drafts(drafts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    roots = [normalize_draft(dict(draft)) for draft in drafts if isinstance(draft, dict)]
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for draft in roots:
        draft_id = draft["draft_id"]
        if draft_id and draft_id not in seen:
            seen.add(draft_id)
            output.append(draft)
    return output


def build_story_drafts_from_epic_or_feature(
    work_item: dict[str, Any],
    *,
    source_stage: str,
    flows: list[str],
    variants: list[str],
    fields: list[str],
    include_ui: bool,
    count: int = 3,
    feature_seeds: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    work_item_type = str(work_item.get("type") or work_item.get("work_item_type") or "").strip().lower()
    if work_item_type == "epic":
        return _build_feature_story_hierarchy(
            work_item,
            source_stage=source_stage,
            flows=flows,
            variants=variants,
            fields=fields,
            include_ui=include_ui,
            count=count,
            feature_seeds=feature_seeds or [],
        )

    area_path = _field(work_item, "areaPath", "area_path")
    iteration_path = _field(work_item, "iterationPath", "iteration_path")
    tags = _tags(work_item)
    subject = _title(work_item)
    outputs: list[dict[str, Any]] = []
    for index in range(1, count + 1):
        story_title = f"{subject}: Story Slice {index}"
        story_id = make_draft_id(source_stage, story_title, index)
        story = make_work_item_draft(
            draft_id=story_id,
            parent_work_item_id=work_item.get("id") or work_item.get("work_item_id"),
            draft_type="User Story",
            title=story_title,
            description=f"As an end user, I want the {subject.lower()} story slice {index} so the feature can be delivered safely.",
            acceptance_criteria=_story_acceptance(subject, flows, fields, index),
            tags=tags,
            area_path=area_path,
            iteration_path=iteration_path,
            source_stage=source_stage,
        )
        story["children"] = _child_task_drafts(
            story,
            source_stage=source_stage,
            include_ui=include_ui,
            variants=variants,
            fields=fields,
            include_documentation=index == 1,
        )
        story["child_drafts"] = story["children"]
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
    return _child_task_drafts(
        make_work_item_draft(
            draft_id=make_draft_id(source_stage, title_seed, 1),
            parent_work_item_id=parent_work_item_id,
            draft_type="Task",
            title=f"Story Delivery: {title_seed}",
            description=f"Coordinate the implementation plan for {title_seed.lower()} before execution begins.",
            acceptance_criteria=[
                "Execution scope is small and well-defined.",
                "Dependencies and ownership are clear.",
            ],
            tags=tags,
            area_path=area_path,
            iteration_path=iteration_path,
            source_stage=source_stage,
        ),
        source_stage=source_stage,
        include_ui=include_ui,
        variants=variants,
        fields=fields,
        include_documentation=True,
    )


def build_create_requests(drafts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for draft in normalize_drafts(drafts):
        _append_create_requests(requests, draft)
    return requests


def mark_drafts_created(drafts: list[dict[str, Any]], created_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    created_map = {str(item.get("draft_id")): dict(item) for item in created_items if item.get("draft_id")}
    updated = [_apply_creation_result(normalize_draft(dict(draft)), created_map) for draft in drafts]
    return normalize_drafts(updated)


def approve_drafts(drafts: list[dict[str, Any]], draft_ids: list[str]) -> list[dict[str, Any]]:
    selected = {str(item) for item in draft_ids}
    updated: list[dict[str, Any]] = []
    for draft in drafts:
        item = normalize_draft(dict(draft))
        if item.get("draft_id") in selected and item.get("status") == "draft":
            item["status"] = "approved"
        item["children"] = approve_drafts(item.get("children", []), draft_ids)
        item["child_drafts"] = item["children"]
        updated.append(item)
    return normalize_drafts(updated)


def _clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "none":
        return None
    return text


def _apply_creation_result(draft: dict[str, Any], created_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    draft_id = str(draft.get("draft_id", ""))
    result = created_map.get(draft_id)
    if result:
        draft["status"] = str(result.get("status", draft.get("status", "draft"))).strip() or "draft"
        draft["azure_work_item_id"] = result.get("azure_work_item_id")
        draft["creation_error"] = result.get("creation_error")
        if result.get("parent_azure_work_item_id") is not None:
            draft["parent_azure_work_item_id"] = result.get("parent_azure_work_item_id")
    children = [_apply_creation_result(normalize_draft(dict(child)), created_map) for child in draft.get("children", [])]
    draft["children"] = children
    draft["child_drafts"] = children
    return draft


def _build_feature_story_hierarchy(
    work_item: dict[str, Any],
    *,
    source_stage: str,
    flows: list[str],
    variants: list[str],
    fields: list[str],
    include_ui: bool,
    count: int,
    feature_seeds: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    area_path = _field(work_item, "areaPath", "area_path")
    iteration_path = _field(work_item, "iterationPath", "iteration_path")
    tags = _tags(work_item)
    subject = _title(work_item)
    outputs: list[dict[str, Any]] = []
    seed_titles = [
        str(seed.get("title", "")).strip()
        for seed in feature_seeds
        if isinstance(seed, dict) and str(seed.get("title", "")).strip()
    ]
    if not seed_titles:
        seed_titles = [f"{subject}: Feature Slice {index}" for index in range(1, min(3, count) + 1)]
    for feature_index, feature_title in enumerate(seed_titles, start=1):
        feature_id = make_draft_id(source_stage, feature_title, feature_index)
        feature = make_work_item_draft(
            draft_id=feature_id,
            parent_work_item_id=work_item.get("id") or work_item.get("work_item_id"),
            draft_type="Feature",
            title=feature_title,
            description=f"Organize the {subject.lower()} epic into the feature slice {feature_index}.",
            acceptance_criteria=[f"Feature slice {feature_index} has clear downstream stories and acceptance criteria."],
            tags=tags,
            area_path=area_path,
            iteration_path=iteration_path,
            source_stage=source_stage,
        )
        stories: list[dict[str, Any]] = []
        for story_index in range(1, 3):
            title = f"{feature_title}: Story {story_index}"
            story = make_work_item_draft(
                draft_id=make_draft_id(source_stage, title, story_index, feature_id),
                parent_work_item_id=work_item.get("id") or work_item.get("work_item_id"),
                parent_draft_id=feature_id,
                draft_type="User Story",
                title=title,
                description=f"As an end user, I want {title.lower()} so the {feature_title.lower()} slice can be delivered.",
                acceptance_criteria=_story_acceptance(feature_title, flows, fields, story_index),
                tags=tags,
                area_path=area_path,
                iteration_path=iteration_path,
                source_stage=source_stage,
            )
            story["children"] = _child_task_drafts(
                story,
                source_stage=source_stage,
                include_ui=include_ui,
                variants=variants,
                fields=fields,
                include_documentation=story_index == 1,
            )
            story["child_drafts"] = story["children"]
            stories.append(story)
        feature["children"] = stories
        feature["child_drafts"] = stories
        outputs.append(feature)
    return outputs[:count]


def _child_task_drafts(
    parent_story: dict[str, Any],
    *,
    source_stage: str,
    include_ui: bool,
    variants: list[str],
    fields: list[str],
    include_documentation: bool,
) -> list[dict[str, Any]]:
    child_drafts: list[dict[str, Any]] = []
    parent_title = str(parent_story.get("title", "")).strip()
    parent_id = parent_story["draft_id"]
    shared = {
        "parent_work_item_id": parent_story.get("parent_work_item_id") if not parent_story.get("parent_draft_id") else None,
        "parent_draft_id": parent_id,
        "tags": list(parent_story.get("tags", [])),
        "area_path": parent_story.get("area_path"),
        "iteration_path": parent_story.get("iteration_path"),
        "source_stage": source_stage,
    }
    order = 1
    if include_ui:
        child_drafts.append(
            make_work_item_draft(
                draft_id=make_draft_id(source_stage, f"UI {parent_title}", order, parent_id),
                draft_type="Task",
                title=f"UI Task: {parent_title}",
                description=f"Design and implement the UI structure for {parent_title.lower()}, including fields and states.",
                acceptance_criteria=[
                    "UI structure reflects the approved story scope.",
                    f"Fields are covered: {', '.join(fields) or 'required interaction fields'}.",
                ],
                **shared,
            )
        )
        order += 1
    child_drafts.append(
        make_work_item_draft(
            draft_id=make_draft_id(source_stage, f"Dev {parent_title}", order, parent_id),
            draft_type="Task",
            title=f"Dev Task: {parent_title}",
            description=f"Implement the approved behavior for {parent_title.lower()} with minimal scope.",
            acceptance_criteria=[
                "Implementation follows the approved execution scope.",
                f"Variant behavior is respected: {', '.join(variants) or 'default flow'}.",
            ],
            **shared,
        )
    )
    order += 1
    child_drafts.append(
        make_work_item_draft(
            draft_id=make_draft_id(source_stage, f"QA {parent_title}", order, parent_id),
            draft_type="Task",
            title=f"QA Task: {parent_title}",
            description=f"Validate the delivered behavior for {parent_title.lower()} and capture regression coverage.",
            acceptance_criteria=[
                "Positive, negative, and edge validation is documented.",
                "Regression risks are covered before closure.",
            ],
            **shared,
        )
    )
    order += 1
    if include_documentation:
        child_drafts.append(
            make_work_item_draft(
                draft_id=make_draft_id(source_stage, f"Docs {parent_title}", order, parent_id),
                draft_type="Task",
                title=f"Documentation Task: {parent_title}",
                description=f"Update supporting release or support documentation for {parent_title.lower()}.",
                acceptance_criteria=["Documentation reflects the delivered behavior and rollout notes."],
                **shared,
            )
        )
    return child_drafts


def _depth(draft: dict[str, Any], flat: list[dict[str, Any]]) -> int:
    by_id = {item.get("draft_id"): item for item in flat}
    depth = 0
    current = draft
    while current.get("parent_draft_id"):
        parent = by_id.get(current.get("parent_draft_id"))
        if not parent:
            break
        depth += 1
        current = parent
    return depth


def _append_create_requests(requests: list[dict[str, Any]], draft: dict[str, Any]) -> None:
    item = normalize_draft(dict(draft))
    if item.get("selected", True):
        requests.append(
            {
                "draft_id": item["draft_id"],
                "type": item["draft_type"],
                "title": item["title"],
                "fields": {
                    "System.Title": item["title"],
                    "System.Description": item["description"],
                    "Microsoft.VSTS.Common.AcceptanceCriteria": "<br/>".join(
                        f"<div>{criterion}</div>" for criterion in item.get("acceptance_criteria", [])
                    ) or None,
                    "System.Tags": "; ".join(item.get("tags", [])) or None,
                    "System.AreaPath": item.get("area_path") or None,
                    "System.IterationPath": item.get("iteration_path") or None,
                },
                "parent_link": {
                    "parent_work_item_id": item.get("parent_work_item_id"),
                    "parent_draft_id": item.get("parent_draft_id"),
                },
            }
        )
    for child in item.get("children", []):
        _append_create_requests(requests, child)


def _story_acceptance(subject: str, flows: list[str], fields: list[str], index: int) -> list[str]:
    criteria = [
        f"{subject} story slice {index} is independently reviewable.",
    ]
    if flows:
        criteria.append(f"Supports the primary flow: {flows[min(index - 1, len(flows) - 1)]}.")
    if fields:
        criteria.append(f"Covers fields: {', '.join(fields[:3])}.")
    return criteria


def _field(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _title(work_item: dict[str, Any]) -> str:
    return str(work_item.get("title", "")).strip() or "Work Item"


def _tags(work_item: dict[str, Any]) -> list[str]:
    tags = work_item.get("tags", [])
    if isinstance(tags, str):
        return [item.strip() for item in tags.split(";") if item.strip()]
    if isinstance(tags, list):
        return [str(item).strip() for item in tags if str(item).strip()]
    return []


def _slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return text[:48]
