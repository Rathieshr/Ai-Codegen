"""Compiles approved HEI sources into the fixed automation command set."""

from __future__ import annotations

import hashlib
from html import escape
from typing import Any

from .models import (
    AddWorkItemCommentCommand, ApplyAreaPathCommand, ApplyEstimateCommand,
    ApplyIterationPathCommand, ApplyTagsCommand, AutomationCommand,
    CREATE_COMMANDS, LinkParentChildCommand, UpdateWorkItemCommand,
)


FIELD_MAP = {
    "title": "System.Title", "description": "System.Description", "acceptanceCriteria": "Microsoft.VSTS.Common.AcceptanceCriteria",
    "storyPoints": "Microsoft.VSTS.Scheduling.StoryPoints", "tags": "System.Tags", "areaPath": "System.AreaPath", "iterationPath": "System.IterationPath",
}


class AutomationCommandCompiler:
    def from_recommendation(self, recommendation: dict[str, Any]) -> tuple[list[AutomationCommand], list[str]]:
        kind = str(recommendation.get("recommendationType") or "")
        target = str(recommendation.get("workItemId") or "")
        revision = int(recommendation.get("workItemRevision") or 0)
        proposed = recommendation.get("proposedValue")
        command: AutomationCommand | None = None
        if kind == "NormalizedTitle": command = UpdateWorkItemCommand(self._id(recommendation, 0), target, {"System.Title": proposed}, expected_revision=revision, reason="Apply approved normalized title.")
        elif kind == "BusinessGoal": command = UpdateWorkItemCommand(self._id(recommendation, 0), target, {"System.Description": proposed}, expected_revision=revision, reason="Apply approved business goal.")
        elif kind == "StoryPointRecommendation":
            points = proposed.get("points") if isinstance(proposed, dict) else proposed
            command = ApplyEstimateCommand(self._id(recommendation, 0), target, {"Microsoft.VSTS.Scheduling.StoryPoints": points}, expected_revision=revision, reason="Apply approved story-point estimate.")
        elif kind == "ApplyTags": command = ApplyTagsCommand(self._id(recommendation, 0), target, {"System.Tags": _tags(proposed)}, expected_revision=revision, reason="Apply approved tags.")
        elif kind == "ApplyAreaPath": command = ApplyAreaPathCommand(self._id(recommendation, 0), target, {"System.AreaPath": proposed}, expected_revision=revision, reason="Apply approved area path.")
        elif kind == "ApplyIterationPath": command = ApplyIterationPathCommand(self._id(recommendation, 0), target, {"System.IterationPath": proposed}, expected_revision=revision, reason="Apply approved iteration path.")
        elif kind == "AddWorkItemComment": command = AddWorkItemCommentCommand(self._id(recommendation, 0), target, {"comment": proposed}, expected_revision=revision, reason="Add approved work-item comment.")
        elif isinstance(proposed, dict) and isinstance(proposed.get("fields"), dict):
            fields = _allowed_fields(proposed["fields"])
            command = UpdateWorkItemCommand(self._id(recommendation, 0), target, fields, expected_revision=revision, reason="Apply approved field recommendation.")
        return ([command] if command else [], [] if command else [f"Recommendation type {kind} has no safe write mapping and remains advisory."])

    def from_planning_pack(self, pack: dict[str, Any]) -> tuple[list[AutomationCommand], list[str]]:
        payload = pack.get("payload") if isinstance(pack.get("payload"), dict) else pack
        items = payload.get("items") or payload.get("workItems") or payload.get("artifacts") or []
        items = [item for item in items if isinstance(item, dict)]
        order = {"Requirement": 0, "Epic": 1, "Feature": 2, "Story": 3, "User Story": 3, "Product Backlog Item": 3, "PBI": 3, "Task": 4}
        items.sort(key=lambda item: order.get(str(item.get("type") or item.get("workItemType")), 99))
        commands: list[AutomationCommand] = []; warnings: list[str] = []
        for index, item in enumerate(items):
            item_type = str(item.get("type") or item.get("workItemType") or "")
            alias = str(item.get("alias") or item.get("id") or f"item-{index + 1}")
            external_id = str(item.get("externalId") or item.get("workItemId") or "")
            fields = _item_fields(item)
            if external_id:
                commands.append(UpdateWorkItemCommand(self._id(pack, index), external_id, fields, work_item_type=item_type, expected_revision=int(item.get("revision") or 0), reason="Update approved Planning Pack item."))
            elif item_type in CREATE_COMMANDS:
                commands.append(CREATE_COMMANDS[item_type](self._id(pack, index), alias, fields, work_item_type=_ado_type(item_type), reason="Create approved Planning Pack item."))
            else:
                warnings.append(f"Unsupported Planning Pack work-item type: {item_type or 'missing' }.")
                continue
            parent = str(item.get("parentAlias") or item.get("parentId") or "")
            if parent:
                commands.append(LinkParentChildCommand(self._id(pack, index, "link"), alias if not external_id else external_id, {}, parent_ref=parent, reason="Create approved parent-child hierarchy link."))
            for suffix, cls, field_name, value in (
                ("estimate", ApplyEstimateCommand, "Microsoft.VSTS.Scheduling.StoryPoints", item.get("storyPoints")),
                ("tags", ApplyTagsCommand, "System.Tags", _tags(item.get("tags"))),
                ("area", ApplyAreaPathCommand, "System.AreaPath", item.get("areaPath")),
                ("iteration", ApplyIterationPathCommand, "System.IterationPath", item.get("iterationPath")),
            ):
                if value not in (None, "", []): commands.append(cls(self._id(pack, index, suffix), alias if not external_id else external_id, {field_name: value}, reason=f"Apply approved {suffix}."))
            if item.get("comment"):
                commands.append(AddWorkItemCommentCommand(self._id(pack, index, "comment"), alias if not external_id else external_id, {"comment": item["comment"]}, reason="Add approved Planning Pack comment."))
        return commands, warnings

    @staticmethod
    def _id(source: dict[str, Any], index: int, suffix: str = "command") -> str:
        source_id = source.get("recommendationId") or source.get("artifact_id") or source.get("artifactId") or source.get("id") or "source"
        digest = hashlib.sha256(f"{source_id}:{index}:{suffix}".encode()).hexdigest()[:14]
        return f"ado-command-{digest}"


def _allowed_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {FIELD_MAP.get(key, key): value for key, value in fields.items() if FIELD_MAP.get(key, key) in set(FIELD_MAP.values())}


def _item_fields(item: dict[str, Any]) -> dict[str, Any]:
    supplied = item.get("fields") if isinstance(item.get("fields"), dict) else {}
    item_type = str(item.get("type") or item.get("workItemType") or "")
    criteria = item.get("acceptanceCriteria")
    description = item.get("description")
    if item_type in {"Epic", "Feature"}:
        measures = criteria or item.get("successMeasures") or item.get("businessValue")
        if not measures and item.get("title"):
            measures = [f"The approved {item_type.lower()} outcome for {item['title']} is delivered and verified through its child work items."]
        description = _description_with_success_measures(description, measures)
        criteria = None
    values = {**supplied, "title": item.get("title"), "description": description, "acceptanceCriteria": criteria}
    return {name: value for name, value in _allowed_fields(values).items() if value not in (None, "", [])}


def _description_with_success_measures(description: Any, measures: Any) -> str:
    values = measures if isinstance(measures, list) else [measures]
    items = [str(value).strip() for value in values if str(value).strip()]
    if not items:
        return str(description or "")
    rendered = "".join(f"<li>{escape(value)}</li>" for value in items)
    prefix = escape(str(description or "").strip())
    return f"{prefix}<h3>Success Measures</h3><ul>{rendered}</ul>"


def _ado_type(value: str) -> str:
    return "User Story" if value == "Story" else "Product Backlog Item" if value == "PBI" else value


def _tags(value: Any) -> str:
    if isinstance(value, list): return "; ".join(str(item) for item in value if str(item).strip())
    return str(value or "")
