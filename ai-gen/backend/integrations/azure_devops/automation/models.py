"""Allow-listed command and execution models for approved ADO automation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar


@dataclass
class AutomationCommand:
    command_id: str
    target_ref: str
    fields: dict[str, Any] = field(default_factory=dict)
    work_item_type: str = ""
    parent_ref: str = ""
    expected_revision: int = 0
    required_permission: str = "WorkItems.Write"
    reason: str = ""
    TYPE: ClassVar[str] = "AutomationCommand"

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value.update({"commandType": self.TYPE, "commandId": value.pop("command_id"), "targetRef": value.pop("target_ref"), "workItemType": value.pop("work_item_type"), "parentRef": value.pop("parent_ref"), "expectedRevision": value.pop("expected_revision"), "requiredPermission": value.pop("required_permission")})
        return value


class CreateEpicCommand(AutomationCommand): TYPE = "CreateEpicCommand"
class CreateFeatureCommand(AutomationCommand): TYPE = "CreateFeatureCommand"
class CreateStoryCommand(AutomationCommand): TYPE = "CreateStoryCommand"
class CreateTaskCommand(AutomationCommand): TYPE = "CreateTaskCommand"
class UpdateWorkItemCommand(AutomationCommand): TYPE = "UpdateWorkItemCommand"
class LinkParentChildCommand(AutomationCommand): TYPE = "LinkParentChildCommand"
class ApplyEstimateCommand(AutomationCommand): TYPE = "ApplyEstimateCommand"
class ApplyTagsCommand(AutomationCommand): TYPE = "ApplyTagsCommand"
class ApplyAreaPathCommand(AutomationCommand): TYPE = "ApplyAreaPathCommand"
class ApplyIterationPathCommand(AutomationCommand): TYPE = "ApplyIterationPathCommand"
class AddWorkItemCommentCommand(AutomationCommand): TYPE = "AddWorkItemCommentCommand"


CREATE_COMMANDS = {"Epic": CreateEpicCommand, "Feature": CreateFeatureCommand, "Story": CreateStoryCommand, "User Story": CreateStoryCommand, "Product Backlog Item": CreateStoryCommand, "PBI": CreateStoryCommand, "Task": CreateTaskCommand}


@dataclass
class AutomationPlan:
    plan_id: str
    source_type: str
    source_id: str
    source_revision: int
    connection_id: str
    project_id: str
    commands: list[AutomationCommand]
    current_values: dict[str, Any]
    warnings: list[str]
    conflicts: list[str]
    required_permissions: list[str]
    approved_by: str
    dry_run: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"planId": self.plan_id, "sourceType": self.source_type, "sourceId": self.source_id, "sourceRevision": self.source_revision, "connectionId": self.connection_id, "projectId": self.project_id, "dryRun": self.dry_run, "operations": [item.to_dict() for item in self.commands], "currentValues": self.current_values, "proposedValues": {item.command_id: item.fields for item in self.commands}, "hierarchyLinks": [{"parent": item.parent_ref, "child": item.target_ref} for item in self.commands if isinstance(item, LinkParentChildCommand)], "warnings": self.warnings, "conflicts": self.conflicts, "requiredPermissions": self.required_permissions, "approvedBy": self.approved_by}
