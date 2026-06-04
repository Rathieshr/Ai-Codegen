from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskDraft:
    id: str
    title: str
    description: str
    estimated_effort: str = ""
    status: str = "pending"
    azure_work_item_id: int | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "estimated_effort": self.estimated_effort,
            "status": self.status,
            "azure_work_item_id": self.azure_work_item_id,
            "error": self.error,
        }


@dataclass
class PlannerSession:
    session_id: str
    requirement: str
    current_stage: str
    title: str = ""
    description: str = ""
    business_value: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    tasks: list[TaskDraft] = field(default_factory=list)
    code_generation_prompt: str = ""
    question: str = ""
    user_input_hint: str = ""
    story_approved: bool = False
    acceptance_approved: bool = False
    tasks_approved: bool = False
    created_story_id: int | None = None
    created_story_status: str = "pending"
    created_story_error: str | None = None
    created_tasks: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "requirement": self.requirement,
            "current_stage": self.current_stage,
            "story": {
                "title": self.title,
                "description": self.description,
                "business_value": self.business_value,
            },
            "acceptance_criteria": list(self.acceptance_criteria),
            "tasks": [task.to_dict() for task in self.tasks],
            "code_generation_prompt": self.code_generation_prompt,
            "question": self.question,
            "user_input_hint": self.user_input_hint,
            "story_approved": self.story_approved,
            "acceptance_approved": self.acceptance_approved,
            "tasks_approved": self.tasks_approved,
            "created_story_id": self.created_story_id,
            "created_story_status": self.created_story_status,
            "created_story_error": self.created_story_error,
            "created_tasks": list(self.created_tasks),
            "created_summary": created_summary(self),
            "error_message": self.error_message,
            "updated_at": self.updated_at,
        }


def created_summary(session: PlannerSession) -> dict[str, Any]:
    return {
        "story": {
            "azure_work_item_id": session.created_story_id,
            "status": session.created_story_status,
            "error": session.created_story_error,
        },
        "tasks": list(session.created_tasks),
    }
