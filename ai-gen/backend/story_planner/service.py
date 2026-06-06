from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
from uuid import uuid4

from backend.refinement.provider import get_refinement_provider

from .devops_mapping import build_acceptance_html, build_creation_preview, build_story_description
from .models import PlannerSession, TaskDraft, utc_now


class StoryPlannerService:
    def __init__(self) -> None:
        self._sessions: dict[str, PlannerSession] = {}

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
        story = _refine_story_with_phi(normalized)
        normalized_type = _clean_text(work_item_type)
        planner_kind = _planner_kind(normalized_type)
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
            question="Does this refined user story match your intent?",
            user_input_hint="Add missing details or corrections here before regenerating.",
        )
        self._sessions[session_id] = session
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
            story = _refine_story_with_phi(_merge_requirement_with_feedback(session.requirement, note))
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
            session.tasks = _generate_tasks_with_phi(session, note)
            session.current_stage = "tasks"
        else:
            raise ValueError(f"Unsupported stage for regeneration: {stage}")
        session.error_message = ""
        self._refresh_stage_prompts(session)
        return session.to_dict()

    def approve_stage(self, session_id: str, stage: str) -> dict[str, Any]:
        session = self._session(session_id)
        if stage == "refined_story":
            session.story_approved = True
            session.acceptance_criteria = _generate_acceptance_criteria_with_phi(session)
            session.current_stage = "acceptance_criteria"
        elif stage == "acceptance_criteria":
            if not session.acceptance_criteria:
                raise ValueError("Acceptance criteria must exist before approval.")
            session.acceptance_approved = True
            session.tasks = _generate_tasks_with_phi(session)
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
        return session.to_dict()

    def _session(self, session_id: str) -> PlannerSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError(f"Unknown planning session: {session_id}")
        session.updated_at = utc_now()
        return session

    def _refresh_stage_prompts(self, session: PlannerSession) -> None:
        if session.current_stage == "refined_story":
            session.question = "Does this refined user story match your intent?"
            session.user_input_hint = "Add missing details or corrections here before regenerating."
        elif session.current_stage == "acceptance_criteria":
            session.question = "Are these acceptance criteria clear and testable?"
            session.user_input_hint = "Add the missing rule or expected outcome here."
        elif session.current_stage == "tasks":
            session.question = "Do these proposed tasks cover the work needed to deliver the story?"
            session.user_input_hint = "Call out a missing task or scope correction here."
        elif session.current_stage == "azure_devops_creation":
            session.question = "Create the approved Azure DevOps work items when you are ready."
            session.user_input_hint = ""
        elif session.current_stage == "success":
            session.question = "Azure DevOps work item creation is complete."
            session.user_input_hint = ""


def _refine_story_with_phi(requirement: str) -> dict[str, str]:
    parsed = _probe_phi_json(
        "You refine requirements into Azure DevOps-ready user stories. Return strict JSON only.",
        {
            "task": "Refine this requirement into a user story.",
            "requirement": requirement,
            "expected_json_schema": {
                "title": "short user story title",
                "description": "As a <actor>, I want <capability> so I can <value>.",
                "business_value": "clear business value",
            },
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
    return _refine_story(requirement)


def _planner_kind(work_item_type: str) -> str:
    normalized = _clean_text(work_item_type).lower().replace("_", " ")
    if normalized == "epic":
        return "epic"
    if normalized == "feature":
        return "feature"
    if normalized in {"user story", "story"}:
        return "user_story"
    return "story"


def _refine_story(requirement: str) -> dict[str, str]:
    normalized = " ".join(requirement.split()).strip()
    actor_match = re.search(r"as\s+a[n]?\s+(?P<actor>.*?),(?:\s*i\s+want|\s*i'd like|\s*i\s+need)", normalized, flags=re.IGNORECASE)
    intent_match = re.search(r"i\s+(?:want|need|would like)\s+(?P<intent>.*?)(?:\s+so\s+i\s+can\s+(?P<value>.*))?$", normalized, flags=re.IGNORECASE)
    actor = actor_match.group("actor").strip() if actor_match else "user"
    intent = intent_match.group("intent").strip(" .") if intent_match else normalized.strip(" .")
    value = (intent_match.group("value") or "").strip(" .") if intent_match else ""
    subject = _subject_from_intent(intent)
    title = f"{subject} for {actor.title()}"
    description = f"As a {actor}, I want {intent} so I can {value or 'complete the workflow successfully'}."
    business_value = value or f"Improve the {subject.lower()} experience for {actor}."
    return {"title": title, "description": description, "business_value": business_value}


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
            "task": "Generate implementation, QA, and supporting tasks for this approved story.",
            "story": {
                "title": session.title,
                "description": session.description,
                "business_value": session.business_value,
            },
            "acceptance_criteria": session.acceptance_criteria,
            "clarification": note,
            "expected_json_schema": {
                "tasks": [
                    {
                        "title": "specific task title",
                        "description": "specific task description",
                        "estimated_effort": "S|M|L",
                    }
                ]
            },
        },
        max_tokens=450,
    )
    tasks = _normalize_tasks(parsed.get("tasks"))
    if len(tasks) >= 2:
        return [_with_new_task_id(task) for task in tasks]
    return _generate_tasks(session, note)


def _generate_tasks(session: PlannerSession, note: str = "") -> list[TaskDraft]:
    subject = _subject_from_intent(session.title)
    tasks = [
        TaskDraft(
            id=f"task_{uuid4().hex[:8]}",
            title=f"Build {subject} UI flow",
            description=f"Implement the user-facing screen and navigation for {subject.lower()}, including the required inputs and state transitions.",
            estimated_effort="M",
        ),
        TaskDraft(
            id=f"task_{uuid4().hex[:8]}",
            title=f"Implement {subject} validation and server handling",
            description=f"Implement the backend or API behavior needed for {subject.lower()}, including validation, expiry, retry rules, and success/failure responses.",
            estimated_effort="M",
        ),
        TaskDraft(
            id=f"task_{uuid4().hex[:8]}",
            title=f"Test {subject} end-to-end",
            description=f"Verify happy path, validation failures, expiry behavior, retry limits, and regression coverage for {subject.lower()}.",
            estimated_effort="S",
        ),
    ]
    if note:
        tasks.append(
            TaskDraft(
                id=f"task_{uuid4().hex[:8]}",
                title=f"Apply clarified {subject} behavior",
                description=f"Ensure the implementation covers this clarified detail: {note.strip()}",
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
