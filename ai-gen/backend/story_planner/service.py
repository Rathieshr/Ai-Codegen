from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.refinement.provider import get_refinement_provider

from .devops_mapping import build_acceptance_html, build_creation_preview, build_story_description
from .models import PlannerSession, TaskDraft, utc_now


class StoryPlannerService:
    def __init__(self) -> None:
        self._sessions: dict[str, PlannerSession] = {}
        _data_dir = os.environ.get("AI_GEN_DATA_DIR", str(Path(__file__).parent.parent.parent / "data"))
        self._sessions_dir = Path(_data_dir) / "story_planner_sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_expired_sessions()
        self._load_all_sessions()

    def start_session(
        self,
        requirement: str,
        work_item_id: int | None = None,
        work_item_type: str = "",
    ) -> dict[str, Any]:
        normalized = " ".join(str(requirement or "").split()).strip()
        if not normalized:
            raise ValueError("Requirement is required.")
        session_id = f"storyplan_{uuid4().hex[:12]}"
        normalized_type = _clean_text(work_item_type)
        planner_kind = _planner_kind(normalized_type)
        story = _refine_story_with_phi(normalized, planner_kind=planner_kind)
        prompts = _planner_prompts(planner_kind)
        session = PlannerSession(
            session_id=session_id,
            requirement=normalized,
            current_stage="refined_story",
            source_work_item_id=work_item_id if isinstance(work_item_id, int) and work_item_id > 0 else None,
            source_work_item_type=normalized_type,
            planner_kind=planner_kind,
            title=story["title"],
            description=story["description"],
            business_value=story["business_value"],
            question=prompts["refined_question"],
            user_input_hint=prompts["refined_hint"],
        )
        self._sessions[session_id] = session
        self._save_session(session)
        return session.to_dict()

    def get_session(self, session_id: str) -> dict[str, Any]:
        return self._session(session_id).to_dict()

    def get_creation_preview(self, session_id: str) -> dict[str, Any]:
        session = self._session(session_id)
        if not session.tasks_approved:
            raise ValueError("Approve tasks before previewing Azure DevOps work items.")
        return {
            "session_id": session.session_id,
            "current_stage": session.current_stage,
            "preview": build_creation_preview(session),
        }

    def store_creation_result(
        self,
        session_id: str,
        story: dict[str, Any] | None,
        tasks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        session = self._session(session_id)
        story_payload = story or {}
        session.created_story_id = story_payload.get("azure_work_item_id")
        session.created_story_status = _clean_text(story_payload.get("status")) or "pending"
        session.created_story_error = _clean_text(story_payload.get("error")) or None
        task_results: list[dict[str, Any]] = []
        indexed = {task.id: task for task in session.tasks}
        for item in tasks:
            task_id = _clean_text(item.get("id"))
            status = _clean_text(item.get("status")) or "pending"
            azure_id = item.get("azure_work_item_id")
            error = _clean_text(item.get("error")) or None
            title = _clean_text(item.get("title"))
            if task_id and task_id in indexed:
                indexed[task_id].status = status
                indexed[task_id].azure_work_item_id = azure_id if isinstance(azure_id, int) else None
                indexed[task_id].error = error
                title = indexed[task_id].title
            task_results.append(
                {
                    "id": task_id,
                    "title": title,
                    "status": status,
                    "azure_work_item_id": azure_id if isinstance(azure_id, int) else None,
                    "error": error,
                }
            )
        session.created_tasks = task_results
        if session.created_story_status == "created" and all(task.get("status") == "created" for task in task_results):
            session.current_stage = "success"
        else:
            session.current_stage = "azure_devops_creation"
        session.error_message = ""
        self._refresh_stage_prompts(session)
        self._save_session(session)
        return session.to_dict()

    def edit_stage(self, session_id: str, stage: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = self._session(session_id)
        if stage == "refined_story":
            session.title = _clean_text(payload.get("title")) or session.title
            session.description = _clean_text(payload.get("description")) or session.description
            session.business_value = _clean_text(payload.get("business_value")) or session.business_value
            session.story_approved = False
            session.acceptance_approved = False
            session.tasks_approved = False
            session.acceptance_criteria = []
            session.tasks = []
            session.code_generation_prompt = ""
        elif stage == "acceptance_criteria":
            session.acceptance_criteria = _normalize_acceptance(payload.get("acceptance_criteria"))
            session.acceptance_approved = False
            session.tasks_approved = False
            session.tasks = []
            session.code_generation_prompt = ""
        elif stage == "tasks":
            session.tasks = _normalize_tasks(payload.get("tasks"))
            session.tasks_approved = False
            session.code_generation_prompt = ""
        else:
            raise ValueError(f"Unsupported stage for edit: {stage}")
        session.error_message = ""
        self._refresh_stage_prompts(session)
        self._save_session(session)
        return session.to_dict()

    def regenerate_stage(self, session_id: str, stage: str, user_input: str = "") -> dict[str, Any]:
        session = self._session(session_id)
        note = _clean_text(user_input)
        if stage == "refined_story":
            session.story_approved = False
            session.acceptance_approved = False
            session.tasks_approved = False
            session.acceptance_criteria = []
            session.tasks = []
            session.code_generation_prompt = ""
            story = _refine_story_with_phi(
                _merge_requirement_with_feedback(session.requirement, note),
                planner_kind=session.planner_kind,
            )
            session.title = story["title"]
            session.description = story["description"]
            session.business_value = story["business_value"]
            session.current_stage = "refined_story"
        elif stage == "acceptance_criteria":
            session.acceptance_approved = False
            session.tasks_approved = False
            session.tasks = []
            session.code_generation_prompt = ""
            session.acceptance_criteria = _generate_acceptance_criteria_with_phi(session, note)
            session.current_stage = "acceptance_criteria"
        elif stage == "tasks":
            session.tasks_approved = False
            session.code_generation_prompt = ""
            session.tasks = _generate_story_breakdown_with_phi(session, note) if session.planner_kind == "epic" else _generate_tasks_with_phi(session, note)
            session.current_stage = "tasks"
        else:
            raise ValueError(f"Unsupported stage for regeneration: {stage}")
        session.error_message = ""
        self._refresh_stage_prompts(session)
        self._save_session(session)
        return session.to_dict()

    def approve_stage(self, session_id: str, stage: str) -> dict[str, Any]:
        session = self._session(session_id)
        if stage == "refined_story":
            session.story_approved = True
            # Type-specific: Epic generates feature list; Feature generates user stories; Story generates AC
            if session.planner_kind == "epic":
                session.acceptance_criteria = _generate_epic_features_with_phi(session)
            elif session.planner_kind == "feature":
                session.acceptance_criteria = _generate_feature_stories_with_phi(session)
            else:
                session.acceptance_criteria = _generate_acceptance_criteria_with_phi(session)
            session.current_stage = "acceptance_criteria"
        elif stage == "acceptance_criteria":
            if not session.acceptance_criteria:
                raise ValueError("Acceptance criteria must exist before approval.")
            session.acceptance_approved = True
            # Type-specific: Epic generates user stories from approved Features; Feature/Story generate delivery tasks.
            session.tasks = _generate_story_breakdown_with_phi(session) if session.planner_kind == "epic" else _generate_tasks_with_phi(session)
            session.current_stage = "tasks"
        elif stage == "tasks":
            if not session.tasks:
                raise ValueError("Tasks must exist before approval.")
            session.tasks_approved = True
            session.code_generation_prompt = _build_code_prompt_with_phi(session)
            session.current_stage = "azure_devops_creation"
        else:
            raise ValueError(f"Unsupported stage for approval: {stage}")
        session.error_message = ""
        self._refresh_stage_prompts(session)
        self._save_session(session)
        return session.to_dict()

    def create_work_items(self, session_id: str) -> dict[str, Any]:
        session = self._session(session_id)
        if not session.tasks_approved or not session.code_generation_prompt:
            raise ValueError("Approve tasks before creating Azure DevOps work items.")
        session.created_story_status = "creating"
        created_tasks: list[dict[str, Any]] = []
        if session.planner_kind == "user_story":
            if not session.source_work_item_id:
                raise ValueError("Current User Story id is required before creating child tasks.")
            session.created_story_id = session.source_work_item_id
            session.created_story_status = "created"
            session.created_story_error = None
        else:
            try:
                story_create = _create_story_work_item(session)
                session.created_story_id = story_create["id"]
                session.created_story_status = "created"
                session.created_story_error = None
            except Exception as error:  # noqa: BLE001
                session.created_story_id = None
                session.created_story_status = "failed"
                session.created_story_error = str(error)
                session.created_tasks = [
                    {
                        "title": task.title,
                        "status": "pending",
                        "azure_work_item_id": None,
                    }
                    for task in session.tasks
                ]
                session.error_message = str(error)
                session.current_stage = "azure_devops_creation"
                self._refresh_stage_prompts(session)
                self._save_session(session)
                return session.to_dict()

        for task in session.tasks:
            task.status = "creating"
            try:
                task_item = _create_child_task_work_item(session, task, session.created_story_id)
                task.status = "created"
                task.azure_work_item_id = task_item["id"]
                task.error = None
                created_tasks.append(
                    {
                        "title": task.title,
                        "status": "created",
                        "azure_work_item_id": task_item["id"],
                    }
                )
            except Exception as error:  # noqa: BLE001
                task.status = "failed"
                task.error = str(error)
                created_tasks.append(
                    {
                        "title": task.title,
                        "status": "failed",
                        "azure_work_item_id": None,
                        "error": str(error),
                    }
                )
        session.created_tasks = created_tasks
        session.current_stage = "success"
        session.error_message = ""
        self._refresh_stage_prompts(session)
        self._save_session(session)
        return session.to_dict()

    def _session(self, session_id: str) -> PlannerSession:
        if session_id not in self._sessions:
            # Try to load from disk (handles server restarts)
            self._load_session_from_disk(session_id)
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError(f"Unknown planning session: {session_id}")
        session.updated_at = utc_now()
        return session

    def list_sessions(self, work_item_id: str | int | None = None) -> list[dict[str, Any]]:
        """Return a summary of all known sessions, newest-first. Optionally filter by source work item."""
        self._load_all_sessions()
        results = []
        for session in self._sessions.values():
            if work_item_id is not None and str(session.source_work_item_id or "") != str(work_item_id):
                continue
            results.append({
                "session_id": session.session_id,
                "title": session.title,
                "requirement": session.requirement[:120],
                "current_stage": session.current_stage,
                "planner_kind": session.planner_kind,
                "source_work_item_id": session.source_work_item_id,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
                "story_approved": session.story_approved,
                "acceptance_approved": session.acceptance_approved,
                "tasks_approved": session.tasks_approved,
            })
        results.sort(key=lambda s: s.get("updated_at") or "", reverse=True)
        return results

    def _save_session(self, session: PlannerSession) -> None:
        """Persist a session to disk as JSON."""
        try:
            path = self._sessions_dir / f"{session.session_id}.json"
            path.write_text(json.dumps(session.to_dict(), ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def _load_session_from_disk(self, session_id: str) -> None:
        """Load a single session from disk into the in-memory cache."""
        try:
            path = self._sessions_dir / f"{session_id}.json"
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                session = PlannerSession(**{k: v for k, v in data.items() if k in PlannerSession.__dataclass_fields__})
                self._sessions[session_id] = session
        except Exception:  # noqa: BLE001
            pass

    def _load_all_sessions(self) -> None:
        """Load all session files from disk that aren't already in memory."""
        try:
            for path in self._sessions_dir.glob("storyplan_*.json"):
                session_id = path.stem
                if session_id not in self._sessions:
                    self._load_session_from_disk(session_id)
        except OSError:
            pass

    def _cleanup_expired_sessions(self, ttl_days: int = 7) -> None:
        """Delete session files older than ttl_days days (B: 7-day TTL)."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
        try:
            for path in self._sessions_dir.glob("storyplan_*.json"):
                try:
                    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                    if mtime < cutoff:
                        path.unlink(missing_ok=True)
                        self._sessions.pop(path.stem, None)
                except OSError:
                    pass
        except OSError:
            pass

    def _refresh_stage_prompts(self, session: PlannerSession) -> None:
        prompts = _planner_prompts(session.planner_kind)
        if session.current_stage == "refined_story":
            session.question = prompts["refined_question"]
            session.user_input_hint = prompts["refined_hint"]
        elif session.current_stage == "acceptance_criteria":
            session.question = prompts["criteria_question"]
            session.user_input_hint = prompts["criteria_hint"]
        elif session.current_stage == "tasks":
            session.question = prompts["tasks_question"]
            session.user_input_hint = prompts["tasks_hint"]
        elif session.current_stage == "azure_devops_creation":
            session.question = "Create the approved Azure DevOps work items when you are ready."
            session.user_input_hint = ""
        elif session.current_stage == "success":
            session.question = "Azure DevOps work item creation is complete."
            session.user_input_hint = ""


# ── Planner type helpers ──────────────────────────────────────────────────────

_PLANNER_PROMPTS: dict[str, dict[str, str]] = {
    "epic": {
        "refined_question": "Does this Epic goal capture the business objective and delivery scope?",
        "refined_hint": "Clarify the target users, strategic impact, or scope boundaries.",
        "criteria_question": "Do these key features cover the full scope of the Epic?",
        "criteria_hint": "Add a missing feature or clarify a scope boundary.",
        "tasks_question": "Do these user stories represent a complete delivery breakdown for each feature?",
        "tasks_hint": "Add a missing story or identify a gap in coverage.",
    },
    "feature": {
        "refined_question": "Does this Feature refinement capture the user need and delivery scope?",
        "refined_hint": "Clarify the target user segment, integration points, or scope boundaries.",
        "criteria_question": "Do these user stories cover the full scope of the Feature?",
        "criteria_hint": "Add a missing user story or clarify a scope item.",
        "tasks_question": "Do these implementation tasks cover the delivery of all user stories?",
        "tasks_hint": "Add a missing task or scope correction here.",
    },
}
_PLANNER_PROMPTS["user_story"] = {
    "refined_question": "Does this refined user story match your intent?",
    "refined_hint": "Add missing details or corrections here before regenerating.",
    "criteria_question": "Are these acceptance criteria clear and testable?",
    "criteria_hint": "Add the missing rule or expected outcome here.",
    "tasks_question": "Do these proposed tasks cover the work needed to deliver the story?",
    "tasks_hint": "Call out a missing task or scope correction here.",
}
_PLANNER_PROMPTS["story"] = _PLANNER_PROMPTS["user_story"]


def _planner_prompts(planner_kind: str) -> dict[str, str]:
    return _PLANNER_PROMPTS.get(planner_kind, _PLANNER_PROMPTS["user_story"])


def _refine_story_with_phi(requirement: str, planner_kind: str = "story") -> dict[str, str]:
    human_requirement = _human_requirement_text(requirement)
    if planner_kind == "epic":
        system = "You refine requirements into Azure DevOps-ready Epic goals. Return strict JSON only."
        task_text = "Refine this requirement into an Epic goal with a clear strategic objective."
        schema = {
            "title": "short Epic title",
            "description": "As a business, we want <epic goal> so we can <strategic outcome>.",
            "business_value": "strategic business value",
        }
    elif planner_kind == "feature":
        system = "You refine requirements into Azure DevOps-ready Feature definitions. Return strict JSON only."
        task_text = "Refine this requirement into a Feature with clear user need and delivery scope."
        schema = {
            "title": "short Feature title",
            "description": "As a <user segment>, I need <feature capability> so I can <user outcome>.",
            "business_value": "clear feature business value",
        }
    else:
        system = "You refine requirements into Azure DevOps-ready user stories. Return strict JSON only."
        task_text = "Refine this requirement into a user story."
        schema = {
            "title": "short user story title",
            "description": "As a <actor>, I want <capability> so I can <value>.",
            "business_value": "clear business value",
        }
    parsed = _probe_phi_json(
        system,
        {
            "task": task_text,
            "requirement": requirement,
            "primary_title": _structured_field(requirement, "Title") or human_requirement,
            "description": _structured_field(requirement, "Description"),
            "acceptance_criteria": _structured_field(requirement, "Acceptance Criteria"),
            "expected_json_schema": schema,
        },
        max_tokens=350,
    )
    story = {
        "title": _clean_text(parsed.get("title")),
        "description": _clean_text(parsed.get("description")),
        "business_value": _clean_text(parsed.get("business_value")),
    }
    if story["title"] and story["description"] and story["business_value"]:
        return story
    return _refine_story(human_requirement, planner_kind=planner_kind)


def _planner_kind(work_item_type: str) -> str:
    normalized = _clean_text(work_item_type).lower().replace("_", " ")
    if normalized == "epic":
        return "epic"
    if normalized == "feature":
        return "feature"
    if normalized in {"user story", "story"}:
        return "user_story"
    return "story"


def _refine_story(requirement: str, planner_kind: str = "story") -> dict[str, str]:
    normalized = " ".join(requirement.split()).strip()
    actor_match = re.search(r"as\s+a[n]?\s+(?P<actor>.*?),(?:\s*i\s+want|\s*i'd like|\s*i\s+need)", normalized, flags=re.IGNORECASE)
    intent_match = re.search(r"i\s+(?:want|need|would like)\s+(?P<intent>.*?)(?:\s+so\s+i\s+can\s+(?P<value>.*))?$", normalized, flags=re.IGNORECASE)
    actor = actor_match.group("actor").strip() if actor_match else "user"
    intent = intent_match.group("intent").strip(" .") if intent_match else normalized.strip(" .")
    value = (intent_match.group("value") or "").strip(" .") if intent_match else ""
    subject = _subject_from_intent(intent)
    if planner_kind == "epic":
        title = subject
        description = f"Deliver {subject.lower()} with clear product capabilities, release scope, and measurable business outcomes."
        business_value = value or f"Enable the business to launch and scale {subject.lower()} with visible delivery readiness."
    elif planner_kind == "feature":
        title = subject
        description = f"As a {actor}, I need {intent} so I can {value or 'complete the target workflow with confidence'}."
        business_value = value or f"Improve the {subject.lower()} capability for {actor}."
    else:
        title = f"{subject} for {actor.title()}"
        description = f"As a {actor}, I want {intent} so I can {value or 'complete the workflow successfully'}."
        business_value = value or f"Improve the {subject.lower()} experience for {actor}."
    return {"title": title, "description": description, "business_value": business_value}


def _generate_epic_features_with_phi(session: PlannerSession, note: str = "") -> list[str]:
    """Generate a list of key Feature names for an Epic (stored in acceptance_criteria field)."""
    parsed = _probe_phi_json(
        "You decompose business Epics into high-level product Features for Azure DevOps. Return strict JSON only.",
        {
            "task": "Generate the key Features needed to deliver this Epic.",
            "epic": {
                "title": session.title,
                "description": session.description,
                "business_value": session.business_value,
            },
            "requirement": session.requirement,
            "clarification": note,
            "rules": [
                "Each feature must be a deliverable product capability, not a task.",
                "Feature names should be concise (5-10 words) and user-facing.",
                "Generate 3-6 features that together cover the full Epic scope.",
            ],
            "expected_json_schema": {
                "features": ["Feature 1 name", "Feature 2 name"]
            },
        },
        max_tokens=400,
    )
    features = parsed.get("features")
    if isinstance(features, list) and len(features) >= 2:
        return [_clean_text(str(f)) for f in features if f]
    # deterministic fallback
    title = session.title or "the Epic"
    return [
        f"Core {title} — Foundation & Setup",
        f"Core {title} — User Flows & Interactions",
        f"Core {title} — Backend & Data Integration",
        f"Core {title} — Notifications & Reporting",
        f"Core {title} — QA, Testing & Release",
    ]


def _generate_feature_stories_with_phi(session: PlannerSession, note: str = "") -> list[str]:
    """Generate a list of User Story names for a Feature (stored in acceptance_criteria field)."""
    parsed = _probe_phi_json(
        "You decompose product Features into Azure DevOps User Stories. Return strict JSON only.",
        {
            "task": "Generate the User Stories needed to deliver this Feature.",
            "feature": {
                "title": session.title,
                "description": session.description,
                "business_value": session.business_value,
            },
            "requirement": session.requirement,
            "clarification": note,
            "rules": [
                "Each story must follow: As a <user>, I want <action> so I can <outcome>.",
                "Stories should be independently deliverable and testable.",
                "Generate 3-6 stories that together cover the Feature scope.",
            ],
            "expected_json_schema": {
                "stories": ["Story 1 title", "Story 2 title"]
            },
        },
        max_tokens=400,
    )
    stories = parsed.get("stories")
    if isinstance(stories, list) and len(stories) >= 2:
        return [_clean_text(str(s)) for s in stories if s]
    # deterministic fallback
    title = session.title or "the Feature"
    return [
        f"View and navigate {title}",
        f"Input and validate data for {title}",
        f"Submit and confirm {title} action",
        f"Handle errors and edge cases for {title}",
    ]


def _generate_story_breakdown_with_phi(session: PlannerSession, note: str = "") -> list[TaskDraft]:
    """Generate Azure DevOps User Story drafts from the approved Epic Feature list."""
    features = _normalize_acceptance(session.acceptance_criteria)
    parsed = _probe_phi_json(
        "You decompose approved Epic Features into Azure DevOps User Stories. Return strict JSON only.",
        {
            "task": "Generate user stories for each approved Feature in this Epic.",
            "epic": {
                "title": session.title,
                "description": session.description,
                "business_value": session.business_value,
            },
            "approved_features": features,
            "requirement": session.requirement,
            "clarification": note,
            "rules": [
                "Generate stories from the approved_features list only.",
                "Each story must be independently deliverable and testable.",
                "Each story description must follow: As a <user>, I want <capability> so I can <outcome>.",
                "Generate 2-3 user stories per approved Feature when scope is broad.",
                "Do not generate implementation tasks.",
            ],
            "expected_json_schema": {
                "stories": [
                    {
                        "feature": "approved feature name",
                        "title": "short user story title",
                        "description": "As a <user>, I want <capability> so I can <outcome>.",
                        "estimated_effort": "S|M|L",
                    }
                ]
            },
        },
        max_tokens=700,
    )
    stories = _normalize_story_breakdown(parsed.get("stories"))
    if len(stories) >= max(2, min(len(features), 2)):
        return [_with_new_task_id(story) for story in stories]
    return _generate_story_breakdown(session, note)


def _normalize_story_breakdown(value: Any) -> list[TaskDraft]:
    if not isinstance(value, list):
        return []
    stories: list[TaskDraft] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        feature = _clean_text(item.get("feature"))
        title = _clean_text(item.get("title"))
        description = _clean_text(item.get("description"))
        if not title or not description:
            continue
        if feature and feature.lower() not in title.lower():
            title = f"{feature}: {title}"
        stories.append(
            TaskDraft(
                id=f"story_{uuid4().hex[:8]}",
                title=title,
                description=description,
                estimated_effort=_clean_text(item.get("estimated_effort")),
            )
        )
    return stories


def _generate_story_breakdown(session: PlannerSession, note: str = "") -> list[TaskDraft]:
    features = _normalize_acceptance(session.acceptance_criteria) or [session.title or "Epic Capability"]
    stories: list[TaskDraft] = []
    for feature in features:
        actor = _actor_for_feature(feature)
        stories.extend(
            [
                TaskDraft(
                    id=f"story_{uuid4().hex[:8]}",
                    title=f"{feature}: discover and start the journey",
                    description=(
                        f"As a {actor}, I want to discover and start {feature.lower()} from the product experience "
                        f"so I can understand the available capability and begin the right workflow."
                    ),
                    estimated_effort="M",
                ),
                TaskDraft(
                    id=f"story_{uuid4().hex[:8]}",
                    title=f"{feature}: complete and validate the outcome",
                    description=(
                        f"As a {actor}, I want to complete {feature.lower()} with validation, confirmation, and error handling "
                        f"so I can trust the outcome before release."
                    ),
                    estimated_effort="M",
                ),
            ]
        )
    if note:
        stories.append(
            TaskDraft(
                id=f"story_{uuid4().hex[:8]}",
                title=f"{session.title}: clarified delivery coverage",
                description=f"As a product team, we want the Epic plan to include this clarification so delivery covers it: {note.strip()}",
                estimated_effort="S",
            )
        )
    return stories


def _actor_for_feature(feature: str) -> str:
    lowered = feature.lower()
    if any(word in lowered for word in ["admin", "operation", "report", "visibility"]):
        return "operations user"
    if any(word in lowered for word in ["seller", "merchant", "property", "hotel"]):
        return "business user"
    return "customer"


def _generate_acceptance_criteria_with_phi(session: PlannerSession, note: str = "") -> list[str]:
    parsed = _probe_phi_json(
        "You generate clear testable Azure DevOps acceptance criteria. Return strict JSON only.",
        {
            "task": "Generate acceptance criteria for the approved user story.",
            "requirement": session.requirement,
            "story": {
                "title": session.title,
                "description": session.description,
                "business_value": session.business_value,
            },
            "clarification": note,
            "expected_json_schema": {
                "acceptance_criteria": [
                    "Given <context>, when <action>, then <observable result>."
                ]
            },
        },
        max_tokens=350,
    )
    criteria = _normalize_acceptance(parsed.get("acceptance_criteria"))
    if len(criteria) >= 2:
        return criteria
    return _generate_acceptance_criteria(session, note)


def _generate_acceptance_criteria(session: PlannerSession, note: str = "") -> list[str]:
    text = " ".join([session.requirement, session.description, note]).lower()
    criteria: list[str] = []
    if "otp" in text:
        criteria.append("Given a customer enters a valid phone number, when they request OTP login, then the system sends a one-time password and shows the OTP verification step.")
        criteria.append("Given a customer enters a valid OTP within 120 seconds, when they submit it, then the customer is authenticated and redirected to their account.")
        criteria.append("Given a customer enters an invalid OTP three times, when the retry limit is reached, then the system blocks further OTP attempts and shows a clear retry message.")
    else:
        criteria.append("Given the user starts the flow, when they complete the required input, then the system accepts valid data and continues the journey.")
        criteria.append("Given invalid or missing input, when the user submits the form, then the system shows clear validation feedback without losing entered data.")
        criteria.append("Given the flow completes successfully, when the user submits valid information, then the system confirms success and moves to the next step.")
    if note:
        criteria.append(f"Include this clarified behavior: {note.strip()}.")
    return _dedupe_text(criteria)


def _generate_tasks_with_phi(session: PlannerSession, note: str = "") -> list[TaskDraft]:
    parsed = _probe_phi_json(
        "You break approved user stories into focused Azure DevOps child tasks. Return strict JSON only.",
        {
            "task": "Generate specific, detailed implementation, QA, and supporting tasks for this approved story.",
            "work_item_type": session.source_work_item_type or "User Story",
            "requirement": session.requirement,
            "story": {
                "title": session.title,
                "description": session.description,
                "business_value": session.business_value,
            },
            "acceptance_criteria": session.acceptance_criteria,
            "clarification": note,
            "rules": [
                "Each task title must reference the specific feature or screen from the story title.",
                "Each task description must mention concrete implementation details (e.g. API endpoint, screen name, validation rule).",
                "Do not use generic titles like 'Build UI flow' or 'Implement validation'.",
                "Generate at least 3 tasks: one for UI/frontend, one for backend/API, one for testing.",
            ],
            "expected_json_schema": {
                "tasks": [
                    {
                        "title": "specific task title referencing the feature",
                        "description": "concrete implementation detail",
                        "estimated_effort": "S|M|L",
                    }
                ]
            },
        },
        max_tokens=600,
    )
    tasks = _normalize_tasks(parsed.get("tasks"))
    if len(tasks) >= 2:
        return [_with_new_task_id(task) for task in tasks]
    return _generate_tasks(session, note)


def _generate_tasks(session: PlannerSession, note: str = "") -> list[TaskDraft]:
    """Deterministic fallback task generator — uses actual story title and description for specificity."""
    title = session.title or "the feature"
    description = session.description or session.requirement or title
    # Pull first acceptance criterion for test task context
    first_ac = session.acceptance_criteria[0] if session.acceptance_criteria else f"the {title} flow works correctly"
    tasks = [
        TaskDraft(
            id=f"task_{uuid4().hex[:8]}",
            title=f"Implement UI for: {title}",
            description=(
                f"Build the user-facing screens and navigation for '{title}'. "
                f"Cover: {description[:200]}. "
                f"Include required inputs, state transitions, loading and error states."
            ),
            estimated_effort="M",
        ),
        TaskDraft(
            id=f"task_{uuid4().hex[:8]}",
            title=f"Backend / API integration for: {title}",
            description=(
                f"Implement the backend or API layer required for '{title}'. "
                f"Cover validation, business rules, error responses and data persistence as described: {description[:200]}."
            ),
            estimated_effort="M",
        ),
        TaskDraft(
            id=f"task_{uuid4().hex[:8]}",
            title=f"Test end-to-end: {title}",
            description=(
                f"Write and run tests covering happy path, edge cases, and failure scenarios for '{title}'. "
                f"Verify: {first_ac}"
            ),
            estimated_effort="S",
        ),
    ]
    if note:
        tasks.append(
            TaskDraft(
                id=f"task_{uuid4().hex[:8]}",
                title=f"Clarification task: {title}",
                description=f"Ensure the implementation covers this clarified requirement: {note.strip()}",
                estimated_effort="S",
            )
        )
    return tasks


def _build_code_prompt_with_phi(session: PlannerSession) -> str:
    parsed = _probe_phi_json(
        "You write concise code-generation prompts for implementation models. Return strict JSON only.",
        {
            "task": "Create the final code-generation prompt for implementing this approved story.",
            "story": {
                "title": session.title,
                "description": session.description,
                "business_value": session.business_value,
            },
            "acceptance_criteria": session.acceptance_criteria,
            "tasks": [task.to_dict() for task in session.tasks],
            "expected_json_schema": {
                "code_generation_prompt": "markdown prompt containing only the implementation brief",
            },
            "rules": [
                "Do not include debug metadata.",
                "Do not include approval history.",
                "Keep the prompt focused on implementation.",
            ],
        },
        max_tokens=500,
    )
    prompt = str(parsed.get("code_generation_prompt") or "").strip()
    if prompt and "# Task" in prompt:
        return prompt
    if prompt:
        return f"# Task\n{prompt}".strip()
    return _build_code_prompt(session)


def _build_code_prompt(session: PlannerSession) -> str:
    sections = [
        "# Task",
        session.description,
        "",
        "# Business Value",
        f"- {session.business_value}",
        "",
        "# Acceptance Criteria",
    ]
    sections.extend(f"- {item}" for item in session.acceptance_criteria)
    sections.extend(["", "# Proposed Tasks"])
    sections.extend(f"- {task.title}: {task.description}" for task in session.tasks)
    sections.extend(
        [
            "",
            "# Implementation Notes",
            "- Keep the change scoped to the approved story and acceptance criteria.",
            "- Preserve validation and authentication safety rules.",
            "- Return clean, production-ready code and explain any important tradeoffs briefly.",
        ]
    )
    return "\n".join(sections).strip()


def _probe_phi_json(system_prompt: str, payload: dict[str, Any], max_tokens: int) -> dict[str, Any]:
    provider = get_refinement_provider()
    if provider is None or not provider.is_enabled():
        return {}
    probe = getattr(provider, "probe_json", None)
    try:
        if callable(probe):
            result = probe(
                system_prompt,
                json.dumps(payload, ensure_ascii=True),
                max_tokens=max_tokens,
                timeout_seconds=_story_planner_phi_timeout_seconds(),
                response_format_enabled=False,
                allow_retry_without_response_format=False,
            )
            parsed = result.get("parsed_json") if isinstance(result, dict) else {}
            return parsed if isinstance(parsed, dict) else {}
        raw = provider.refine_json(system_prompt, json.dumps(payload, ensure_ascii=True), max_tokens=max_tokens)
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _story_planner_phi_timeout_seconds() -> int:
    try:
        return max(3, int(os.getenv("AI_GEN_STORY_PLANNER_PHI_TIMEOUT_SECONDS", "10")))
    except (TypeError, ValueError):
        return 10


def _with_new_task_id(task: TaskDraft) -> TaskDraft:
    task.id = f"task_{uuid4().hex[:8]}"
    task.status = "pending"
    task.azure_work_item_id = None
    task.error = None
    return task


def _structured_field(requirement: str, label: str) -> str:
    pattern = rf"(?:^|\n)\s*{re.escape(label)}\s*:\s*(?P<value>.*?)(?=\n\s*[A-Z][A-Za-z /]*\s*:|\Z)"
    match = re.search(pattern, str(requirement or ""), flags=re.IGNORECASE | re.DOTALL)
    return _clean_text(match.group("value")) if match else ""


def _human_requirement_text(requirement: str) -> str:
    title = _structured_field(requirement, "Title")
    description = _structured_field(requirement, "Description")
    acceptance = _structured_field(requirement, "Acceptance Criteria")
    comments = _structured_field(requirement, "Discussion Notes")
    parts = [item for item in [title, description, acceptance, comments] if item]
    if parts:
        return _clean_text(" ".join(parts))
    cleaned = re.sub(r"\bWork Item Type\s*:\s*\w+\b", " ", str(requirement or ""), flags=re.IGNORECASE)
    cleaned = re.sub(r"\bTitle\s*:\s*", " ", cleaned, flags=re.IGNORECASE)
    return _clean_text(cleaned)


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalize_acceptance(value: Any) -> list[str]:
    if isinstance(value, str):
        items = [line.strip() for line in value.splitlines() if line.strip()]
        return _dedupe_text(items)
    if isinstance(value, list):
        return _dedupe_text([_clean_text(item) for item in value if _clean_text(item)])
    return []


def _normalize_tasks(value: Any) -> list[TaskDraft]:
    if not isinstance(value, list):
        return []
    tasks: list[TaskDraft] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        title = _clean_text(item.get("title"))
        description = _clean_text(item.get("description"))
        if not title or not description:
            continue
        tasks.append(
            TaskDraft(
                id=_clean_text(item.get("id")) or f"task_{uuid4().hex[:8]}",
                title=title,
                description=description,
                estimated_effort=_clean_text(item.get("estimated_effort")),
                status=_clean_text(item.get("status")) or "pending",
                azure_work_item_id=item.get("azure_work_item_id"),
                error=_clean_text(item.get("error")) or None,
            )
        )
    return tasks


def _merge_requirement_with_feedback(requirement: str, feedback: str) -> str:
    if not feedback:
        return requirement
    return f"{requirement} Clarification: {feedback.strip()}"


def _subject_from_intent(intent: str) -> str:
    text = re.sub(r"\bso i can\b.*$", "", str(intent), flags=re.IGNORECASE).strip(" .")
    text = re.sub(r"^(?:as a .*?,\s*)?i\s+(?:want|need|would like)\s+", "", text, flags=re.IGNORECASE)
    text = text.strip(" .")
    if not text:
        return "Story Delivery"
    words = text.split()
    return " ".join(word.capitalize() for word in words[:6])


def _dedupe_text(items: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = _clean_text(item)
        if normalized and normalized.lower() not in seen:
            seen.add(normalized.lower())
            output.append(normalized)
    return output


def _devops_base_url() -> str:
    org = os.getenv("AZURE_DEVOPS_ORG", "").strip()
    project = os.getenv("AZURE_DEVOPS_PROJECT", "").strip()
    if not org or not project:
        raise ValueError("AZURE_DEVOPS_ORG and AZURE_DEVOPS_PROJECT must be configured.")
    if org.startswith("http://") or org.startswith("https://"):
        base = org.rstrip("/")
    else:
        base = f"https://dev.azure.com/{org}"
    return f"{base}/{urllib.parse.quote(project)}"


def _devops_auth_header() -> str:
    pat = os.getenv("AZURE_DEVOPS_PAT", "").strip()
    if not pat:
        raise ValueError("AZURE_DEVOPS_PAT must be configured.")
    token = base64.b64encode(f":{pat}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _create_story_work_item(session: PlannerSession) -> dict[str, Any]:
    ops = [
        {"op": "add", "path": "/fields/System.Title", "value": session.title},
        {"op": "add", "path": "/fields/System.Description", "value": build_story_description(session)},
        {"op": "add", "path": "/fields/Microsoft.VSTS.Common.AcceptanceCriteria", "value": build_acceptance_html(session.acceptance_criteria)},
    ]
    return _create_work_item("User Story", ops)


def _create_child_task_work_item(session: PlannerSession, task: TaskDraft, parent_id: int) -> dict[str, Any]:
    description_html = f"<p>{_escape_html(task.description)}</p>"
    ops = [
        {"op": "add", "path": "/fields/System.Title", "value": task.title},
        {"op": "add", "path": "/fields/System.Description", "value": description_html},
        {
            "op": "add",
            "path": "/relations/-",
            "value": {
                "rel": "System.LinkTypes.Hierarchy-Reverse",
                "url": f"{_devops_base_url().rsplit('/', 1)[0]}/_apis/wit/workItems/{parent_id}",
            },
        },
    ]
    return _create_work_item("Task", ops)


def _create_work_item(work_item_type: str, operations: list[dict[str, Any]]) -> dict[str, Any]:
    base_url = _devops_base_url()
    url = f"{base_url}/_apis/wit/workitems/${urllib.parse.quote(work_item_type)}?api-version=7.1"
    request = urllib.request.Request(
        url,
        data=json.dumps(operations).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json-patch+json",
            "Authorization": _devops_auth_header(),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return {"id": int(payload["id"]), "url": str(payload.get("url", ""))}
    except urllib.error.HTTPError as error:
        body = ""
        try:
            body = error.read().decode("utf-8")
        except Exception:
            body = ""
        raise ValueError(f"Azure DevOps returned HTTP {error.code}: {body or error.reason}") from error
story_planner_service = StoryPlannerService()
