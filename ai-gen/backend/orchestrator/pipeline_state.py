"""State models for the structured assistant pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

STAGE_ORDER = ["ba", "ui", "dev", "test", "critic"]


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
    version: int = 1
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    work_item: dict[str, Any] = field(default_factory=dict)
    repo_context: dict[str, Any] = field(default_factory=dict)
    refinement: dict[str, Any] = field(default_factory=dict)

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
            version=int(data.get("version", 1)),
            created_at=data.get("created_at", utc_now()),
            updated_at=data.get("updated_at", utc_now()),
            work_item=data.get("work_item", {}),
            repo_context=data.get("repo_context", {}),
            refinement=data.get("refinement", {}),
        )


def create_initial_pipeline_state(
    pipeline_id: str,
    source: str,
    work_item_id: str,
    work_item: dict[str, Any],
    repo_context: dict[str, Any] | None = None,
    refinement: dict[str, Any] | None = None,
) -> PipelineState:
    """Create the initial locked/unlocked stage map for a new pipeline."""

    stages = {
        "ba": StageState(stage="ba", status="pending"),
        "ui": StageState(stage="ui", status="locked"),
        "dev": StageState(stage="dev", status="locked"),
        "test": StageState(stage="test", status="locked"),
        "critic": StageState(stage="critic", status="locked"),
    }
    return PipelineState(
        pipeline_id=pipeline_id,
        source=source,
        work_item_id=str(work_item_id),
        current_stage="ba",
        stages=stages,
        work_item=work_item,
        repo_context=repo_context or {},
        refinement=refinement or {},
    )
