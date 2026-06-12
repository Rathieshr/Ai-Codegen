"""State models for the structured assistant pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

STAGE_ORDER = ["ba", "ui", "dev", "test", "critic"]
DEFAULT_TEMPLATE_NAME = "legacy_delivery"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StageFeedback:
    id: str
    author: str
    timestamp: str
    comment: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StageFeedback":
        return cls(**data)


@dataclass
class StageState:
    stage: str
    status: str = "locked"
    approved: bool = False
    approved_at: str | None = None
    approved_by: str | None = None
    version: int = 0
    output: dict[str, Any] = field(default_factory=dict)
    critic: dict[str, Any] | None = None
    handoff_id: str | None = None
    skip_reason: str | None = None
    review_feedback: list[StageFeedback] = field(default_factory=list)
    unresolved_findings: list[dict[str, Any]] = field(default_factory=list)
    resolved_findings: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["review_feedback"] = [feedback.to_dict() for feedback in self.review_feedback]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StageState":
        payload = dict(data)
        payload["review_feedback"] = [StageFeedback.from_dict(item) for item in data.get("review_feedback", [])]
        return cls(**payload)


@dataclass
class PipelineState:
    pipeline_id: str
    source: str
    work_item_id: str
    current_stage: str
    stages: dict[str, StageState]
    workflow_template: str = DEFAULT_TEMPLATE_NAME
    stage_order: list[str] = field(default_factory=lambda: list(STAGE_ORDER))
    stage_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    work_item_classification: dict[str, Any] = field(default_factory=dict)
    version: int = 1
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    work_item: dict[str, Any] = field(default_factory=dict)
    repo_context: dict[str, Any] = field(default_factory=dict)
    refinement: dict[str, Any] = field(default_factory=dict)
    ai_gen_comments: list[dict[str, Any]] = field(default_factory=list)
    team_comments: list[dict[str, Any]] = field(default_factory=list)
    epic_context: dict[str, Any] = field(default_factory=dict)
    pipeline_context: dict[str, Any] = field(default_factory=dict)
    activity: list[dict[str, Any]] = field(default_factory=list)
    draft_work_items: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["stages"] = {name: stage.to_dict() for name, stage in self.stages.items()}
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PipelineState":
        stages = {name: StageState.from_dict(stage) for name, stage in data.get("stages", {}).items()}
        return cls(
            pipeline_id=data["pipeline_id"],
            source=data.get("source", "azure_devops"),
            work_item_id=str(data.get("work_item_id", "")),
            current_stage=data.get("current_stage", "ba"),
            stages=stages,
            workflow_template=data.get("workflow_template", DEFAULT_TEMPLATE_NAME),
            stage_order=list(data.get("stage_order", STAGE_ORDER)),
            stage_metadata=data.get("stage_metadata", {}),
            work_item_classification=data.get("work_item_classification", {}),
            version=int(data.get("version", 1)),
            created_at=data.get("created_at", utc_now()),
            updated_at=data.get("updated_at", utc_now()),
            work_item=data.get("work_item", {}),
            repo_context=data.get("repo_context", {}),
            refinement=data.get("refinement", {}),
            ai_gen_comments=data.get("ai_gen_comments", []),
            team_comments=data.get("team_comments", []),
            epic_context=data.get("epic_context", {}),
            pipeline_context=data.get("pipeline_context", {}),
            activity=data.get("activity", []),
            draft_work_items=data.get("draft_work_items", []),
        )


def create_initial_pipeline_state(
    pipeline_id: str,
    source: str,
    work_item_id: str,
    work_item: dict[str, Any],
    repo_context: dict[str, Any] | None = None,
    refinement: dict[str, Any] | None = None,
    ai_gen_comments: list[dict[str, Any]] | None = None,
    team_comments: list[dict[str, Any]] | None = None,
    epic_context: dict[str, Any] | None = None,
    pipeline_context: dict[str, Any] | None = None,
    activity: list[dict[str, Any]] | None = None,
    workflow_template: str = DEFAULT_TEMPLATE_NAME,
    stage_order: list[str] | None = None,
    stage_metadata: dict[str, dict[str, Any]] | None = None,
    work_item_classification: dict[str, Any] | None = None,
) -> PipelineState:
    """Create the initial locked/unlocked stage map for a new pipeline."""

    active_order = list(stage_order or STAGE_ORDER)
    metadata = stage_metadata or {name: {"name": name} for name in active_order}
    stages = {
        name: StageState(stage=name, status="pending" if index == 0 else "locked")
        for index, name in enumerate(active_order)
    }
    return PipelineState(
        pipeline_id=pipeline_id,
        source=source,
        work_item_id=str(work_item_id),
        current_stage=active_order[0] if active_order else "critic",
        stages=stages,
        workflow_template=workflow_template,
        stage_order=active_order,
        stage_metadata=metadata,
        work_item_classification=work_item_classification or {},
        work_item=work_item,
        repo_context=repo_context or {},
        refinement=refinement or {},
        ai_gen_comments=ai_gen_comments or [],
        team_comments=team_comments or [],
        epic_context=epic_context or {},
        pipeline_context=pipeline_context or {},
        activity=activity or [],
        draft_work_items=[],
    )
