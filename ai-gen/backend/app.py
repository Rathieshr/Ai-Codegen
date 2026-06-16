"""FastAPI backend for generating Codex-ready business context."""

import os
import json
import inspect
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from backend.auth import ApiKeyMiddleware, get_api_key_status, validate_approver_role
from backend.guardrails import guard_stage_output, has_blocking_violation
from backend.ado import AdoAutomation, AdoClient

logger = logging.getLogger("ai_gen.app")

from backend.execution_corrector import build_corrected_execution_prompt, generate_retry_plan
from backend.handoff.storage import list_handoffs, load_handoff_markdown
from backend.execution_mode import detect_prompt_mode, score_execution_confidence
from backend.execution_validator import ExecutionContext, snapshot_selected_files, validate_execution
from backend.intent_detector import detect_intent
from backend.model_router import detect_execution_target, get_available_targets
from backend.orchestrator.react_controller import PipelineController
from backend.project_intelligence import project_intelligence_service
from backend.refinement.provider import get_refiner_status, get_refinement_provider
from backend.refinement.refinement_decider import should_use_refiner
from backend.refinement.schema_validator import validate_task_refinement
from backend.refinement.task_refiner import refine_epic_stage, refine_task
from backend.repo_context.bug_localizer import detect_bug_surface, score_bug_hotspots
from backend.repo_context.cross_flow import build_flow_relationships, get_related_flows
from backend.repo_context.indexer import bootstrap_repo_index, update_changed_files
from backend.repo_context.manager import RepoContextManager, merge_effective_context
from backend.repo_context.models import SessionContext
from backend.repo_context.storage import read_json
from backend.repo_context.retrieval_bias import collect_session_bias_signals, rank_logic_units_with_bias
from backend.status import get_status
from backend.story_planner import story_planner_service
from backend.work_item_optimizer import optimize_work_item_request
from backend.audit import get_events as audit_get_events, get_summary as audit_get_summary
from context_builder.builder import ContextBuilder
from context_builder.execution_packets import (
    build_execution_packet,
    build_exploration_packet,
    build_response_packet,
    select_execution_files,
)
from logic_store.store import LogicStore


app = FastAPI(
    title="ai-gen Context API",
    description="Builds compact business logic-aware prompts before Codex runs.",
    version="0.1.0",
)
# CORS — restrict origins via env var in production
# Example: AI_GEN_CORS_ORIGINS=https://dev.azure.com,https://app.example.com
_cors_origins_raw = os.getenv("AI_GEN_CORS_ORIGINS", "*")
_cors_origins: list[str] = (
    [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
    if _cors_origins_raw.strip() != "*"
    else ["*"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*", "X-Api-Key"],
)
# API key auth — add AFTER CORS so OPTIONS pre-flights pass through
app.add_middleware(ApiKeyMiddleware)
print(f"ai-gen backend starting in {os.getenv('AI_GEN_BACKEND_MODE', 'local')} mode")

logic_store = LogicStore()
context_builder = ContextBuilder(logic_store=logic_store)
repo_context_manager = RepoContextManager(
    Path(os.getenv("AI_GEN_REPO_CONTEXT_ROOT", ".ai_gen_repo_context"))
)
pipeline_controller = PipelineController(Path(os.getenv("AI_GEN_PIPELINE_ROOT", ".ai_gen_pipelines")))
ado_automation = AdoAutomation()

class ContextRequest(BaseModel):
    """Request body accepted by POST /context."""

    query: str = Field(..., min_length=1, description="Natural language developer task.")
    file_path: Optional[str] = Field(default=None, description="Optional current editor file path.")
    selected_text: Optional[str] = Field(default=None, description="Optional editor selection.")
    workspace_root: Optional[str] = Field(default=None, description="Optional workspace root.")
    repo_id: Optional[str] = Field(default=None, description="Optional shared repo context id.")
    branch_name: Optional[str] = Field(default=None, description="Optional branch name for repo context overlays.")
    session_id: Optional[str] = Field(default=None, description="Optional live IDE/user session id.")
    ide: Optional[str] = Field(default=None, description="Optional IDE client name.")
    open_files: list[str] = Field(default_factory=list, description="Optional open files from the IDE.")
    current_file: Optional[str] = Field(default=None, description="Optional current file path from the IDE.")
    git_remote: Optional[str] = Field(default=None, description="Optional git remote from the IDE.")
    routing_mode: str = Field(default="auto", description="Optional execution routing mode.")
    source: Optional[str] = Field(default=None, description="Optional request source such as azure_devops.")
    work_item: Optional[dict[str, Any]] = Field(default=None, description="Optional normalized work item payload.")
    max_tokens: int = Field(
        default=900,
        ge=150,
        le=4000,
        description="Approximate token budget for injected context.",
    )


class ContextResponse(BaseModel):
    """Response returned by POST /context."""

    optimized_prompt: str
    matched_logic: list[str]
    token_estimate: int
    execution_target: str
    execution_reason: str
    available_targets: dict[str, bool]
    planning_enabled: bool
    plan: dict
    plan_summary: str
    resolved_repo_id: Optional[str] = None
    resolved_branch_name: Optional[str] = None
    retrieval_bias_applied: bool = False
    session_bias_summary: Optional[dict] = None
    repo_identity_mode: Optional[str] = None
    repo_identity_source: Optional[str] = None
    indexing_performed: bool = False
    incremental_update_performed: bool = False
    changed_files_count: int = 0
    detected_flow: Optional[str] = None
    related_flows: list[str] = Field(default_factory=list)
    flow_files_count: int = 0
    bug_surface: Optional[str] = None
    likely_bug_hotspots: list[dict] = Field(default_factory=list)
    prompt_mode: str = "explore"
    prompt_mode_reason: str = ""
    execution_confidence: float = 0.0
    execution_confidence_level: str = "low"
    execution_confidence_signals: list[str] = Field(default_factory=list)
    selected_execution_files: list[str] = Field(default_factory=list)
    execution_validation: Optional[dict] = None
    drift_detected: bool = False
    constraint_violations: list[str] = Field(default_factory=list)
    risky_changes: list[str] = Field(default_factory=list)
    work_item_optimized: bool = False
    work_item_task_summary: Optional[str] = None
    work_item_surface: Optional[str] = None
    work_item_scope: list[str] = Field(default_factory=list)
    semantic_mapping_applied: bool = False
    refinement_used: bool = False
    refinement_source: str = "none"
    refinement_provider: Optional[str] = None
    refinement_reason: str = ""
    phi_used: bool = False
    phi_status: str = "skipped"
    phi_raw_response_preview: str = ""
    refined_base_flows: list[str] = Field(default_factory=list)
    refined_variants: list[str] = Field(default_factory=list)
    refined_surfaces: list[str] = Field(default_factory=list)
    refined_base_flow: Optional[str] = None
    refined_variant: Optional[str] = None
    refined_surface: Optional[str] = None
    refined_fields: list[str] = Field(default_factory=list)
    refined_validations: list[str] = Field(default_factory=list)
    refined_scope: list[str] = Field(default_factory=list)
    refined_actors: list[str] = Field(default_factory=list)
    refined_states: list[str] = Field(default_factory=list)
    refinement_unknowns: list[str] = Field(default_factory=list)
    refinement_confidence: Optional[str] = None


class ExecutionValidationRequest(BaseModel):
    """Request body accepted by POST /execution/validate."""

    repo_root: str = Field(..., min_length=1)
    selected_files: list[str] = Field(default_factory=list)
    allowed_flows: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    likely_breakpoints: list[str] = Field(default_factory=list)
    baseline_hashes: dict[str, str] = Field(default_factory=dict)
    changed_files: Optional[list[str]] = None
    prompt_mode: str = "execute"
    query: str = ""
    detected_flow: Optional[str] = None
    related_flows: list[str] = Field(default_factory=list)


class ExecutionSnapshotRequest(BaseModel):
    """Request body accepted by POST /execution/snapshot."""

    repo_root: str = Field(..., min_length=1)
    selected_files: list[str] = Field(default_factory=list)


class PipelineCreateRequest(BaseModel):
    source: str = Field(default="azure_devops")
    work_item: dict[str, Any] = Field(default_factory=dict)
    repo_context: Optional[dict[str, Any]] = None
    refinement: Optional[dict[str, Any]] = None
    ai_gen_comments: list[dict[str, Any]] = Field(default_factory=list)
    team_comments: list[dict[str, Any]] = Field(default_factory=list)
    epic_context: Optional[dict[str, Any]] = None


class PipelineStageRequest(BaseModel):
    stage: str
    regenerate: bool = False
    feedback_comment: Optional[str] = None
    feedback_author: Optional[str] = None
    ai_gen_comments: list[dict[str, Any]] = Field(default_factory=list)
    team_comments: list[dict[str, Any]] = Field(default_factory=list)


class PipelineApproveRequest(BaseModel):
    stage: str
    approved_by: Optional[str] = None
    approver_role: Optional[str] = Field(
        default=None,
        description="Role of the approver (product/developer/qa/lead/admin). "
                    "Used for role-based gate enforcement when AI_GEN_ROLE_ENFORCEMENT=1.",
    )


class PipelineSkipRequest(BaseModel):
    stage: str
    reason: str


class PipelineStageFeedbackRequest(BaseModel):
    stage: str
    comment: str
    author: Optional[str] = None


class DraftWorkItemApproveRequest(BaseModel):
    draft_ids: list[str] = Field(default_factory=list)


class DraftWorkItemCreateRequest(BaseModel):
    draft_ids: list[str] = Field(default_factory=list)
    create_child_tasks: bool = True
    user_identity: Optional[dict[str, Any]] = None


class DraftWorkItemsCreatedRequest(BaseModel):
    created_items: list[dict[str, Any]] = Field(default_factory=list)


class RefinementTestRequest(BaseModel):
    query: str = Field(..., min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)
    mode: str = "refine"
    include_model_field: Optional[bool] = None
    api_version: Optional[str] = None
    max_tokens: int = Field(default=300, ge=1, le=1000)


class RefinementRawHttpTestRequest(BaseModel):
    query: str = Field(default="ping", min_length=1)
    mode: str = Field(default="with_model")
    include_model_field: Optional[bool] = None
    api_version: Optional[str] = None
    max_tokens: int = Field(default=50, ge=1, le=1000)


class RefinementSmokeTestRequest(BaseModel):
    query: str = Field(default="WhatsApp Hotel Booking Platform", min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)
    include_model_field: Optional[bool] = None
    api_version: Optional[str] = None


class StoryPlannerStartRequest(BaseModel):
    requirement: str = Field(..., min_length=1)
    work_item_id: Optional[int] = None
    work_item_type: str = ""


class StoryPlannerEditRequest(BaseModel):
    stage: str
    payload: dict[str, Any] = Field(default_factory=dict)


class StoryPlannerStageRequest(BaseModel):
    stage: str
    user_input: str = ""


class StoryPlannerCreationResultRequest(BaseModel):
    story: dict[str, Any] = Field(default_factory=dict)
    tasks: list[dict[str, Any]] = Field(default_factory=list)


class ProjectIntelligenceProfileRequest(BaseModel):
    profile: dict[str, Any] = Field(default_factory=dict)


class ProjectIntelligenceDescriptionRequest(BaseModel):
    description: str = ""


class ProjectIntelligencePromptRequest(BaseModel):
    story: dict[str, Any] = Field(default_factory=dict)
    profile: Optional[dict[str, Any]] = None


class ProjectIntelligenceReadmeRequest(BaseModel):
    readme_content: str = ""
    repository: dict[str, Any] = Field(default_factory=dict)
    profile: Optional[dict[str, Any]] = None


class ProjectIntelligenceRefinementRequest(BaseModel):
    profile: dict[str, Any] = Field(default_factory=dict)
    knowledge_profile: dict[str, Any] = Field(default_factory=dict)
    epic: dict[str, Any] = Field(default_factory=dict)
    feature: dict[str, Any] = Field(default_factory=dict)
    story: dict[str, Any] = Field(default_factory=dict)


@app.get("/health")
def health() -> dict[str, str]:
    """Lightweight readiness check for local CLI calls."""

    return {"status": "ok"}


@app.get("/capabilities")
def capabilities() -> dict:
    """Return lightweight routing capabilities including auth status."""

    status = get_status()
    status["auth"] = get_api_key_status()
    return status


@app.get("/project-intelligence/profile")
def get_project_intelligence_profile() -> dict:
    return project_intelligence_service.get_profile()


@app.post("/project-intelligence/profile")
def save_project_intelligence_profile(request: ProjectIntelligenceProfileRequest) -> dict:
    return project_intelligence_service.save_profile(request.profile)


@app.post("/project-intelligence/analyze-description")
def analyze_project_description(request: ProjectIntelligenceDescriptionRequest) -> dict:
    return project_intelligence_service.analyze_description(request.description)


@app.post("/project-intelligence/generate-story-prompts")
def generate_project_story_prompts(request: ProjectIntelligencePromptRequest) -> dict:
    return project_intelligence_service.generate_story_prompts(request.story, request.profile)


@app.post("/project-intelligence/analyze-readme")
def analyze_project_readme(request: ProjectIntelligenceReadmeRequest) -> dict:
    return project_intelligence_service.analyze_readme(request.readme_content, request.repository, request.profile)


@app.post("/project-intelligence/refine-epic")
def refine_project_epic(request: ProjectIntelligenceRefinementRequest) -> dict:
    return project_intelligence_service.refine_epic(request.epic, request.profile, request.knowledge_profile)


@app.post("/project-intelligence/refine-feature")
def refine_project_feature(request: ProjectIntelligenceRefinementRequest) -> dict:
    return project_intelligence_service.refine_feature(request.feature, request.profile, request.knowledge_profile)


@app.post("/project-intelligence/refine-story")
def refine_project_story(request: ProjectIntelligenceRefinementRequest) -> dict:
    return project_intelligence_service.refine_story(request.story, request.profile, request.knowledge_profile)


@app.post("/story-planner/sessions")
def start_story_planner_session(request: StoryPlannerStartRequest) -> dict:
    return story_planner_service.start_session(
        request.requirement,
        work_item_id=request.work_item_id,
        work_item_type=request.work_item_type,
    )


@app.get("/story-planner/sessions/{session_id}")
def get_story_planner_session(session_id: str) -> dict:
    return story_planner_service.get_session(session_id)


@app.post("/story-planner/sessions/{session_id}/edit")
def edit_story_planner_stage(session_id: str, request: StoryPlannerEditRequest) -> dict:
    return story_planner_service.edit_stage(session_id, request.stage, request.payload)


@app.post("/story-planner/sessions/{session_id}/regenerate")
def regenerate_story_planner_stage(session_id: str, request: StoryPlannerStageRequest) -> dict:
    return story_planner_service.regenerate_stage(session_id, request.stage, request.user_input)


@app.post("/story-planner/sessions/{session_id}/approve")
def approve_story_planner_stage(session_id: str, request: StoryPlannerStageRequest) -> dict:
    return story_planner_service.approve_stage(session_id, request.stage)


@app.post("/story-planner/sessions/{session_id}/creation-preview")
def preview_story_planner_work_items(session_id: str) -> dict:
    return story_planner_service.get_creation_preview(session_id)


@app.post("/story-planner/sessions/{session_id}/creation-result")
def store_story_planner_creation_result(session_id: str, request: StoryPlannerCreationResultRequest) -> dict:
    return story_planner_service.store_creation_result(session_id, request.story, request.tasks)


@app.post("/story-planner/sessions/{session_id}/create-work-items")
def create_story_planner_work_items(session_id: str) -> dict:
    return story_planner_service.create_work_items(session_id)


@app.get("/refinement/health")
def refinement_health() -> dict[str, Any]:
    """Return non-secret refiner health status."""

    provider = get_refinement_provider()
    if provider is not None and hasattr(provider, "health_snapshot"):
        return {
            **provider.health_snapshot(),
            "provider": "azure_phi",
            "configured": provider.is_enabled(),
        }
    status = get_refiner_status()
    return {
        "deployment": status.get("deployment"),
        "health": "unhealthy" if status.get("configured") else "not_configured",
        "last_success": None,
        "last_failure": None,
        "average_latency_ms": 0,
        "consecutive_failures": 0,
        "provider": status.get("provider"),
        "configured": status.get("configured"),
    }


@app.get("/refinement/config")
def refinement_config() -> dict[str, Any]:
    provider = get_refinement_provider()
    if provider is not None and hasattr(provider, "safe_config"):
        return provider.safe_config()
    return _fallback_refinement_config()


@app.get("/refinement/debug-curl")
def refinement_debug_curl(mode: str = "ping") -> dict[str, Any]:
    provider = get_refinement_provider()
    if provider is not None and hasattr(provider, "debug_curl"):
        return {"mode": mode, "curl": provider.debug_curl(mode)}
    return {"mode": mode, "curl": ""}


@app.post("/refinement/raw-http-test")
def refinement_raw_http_test(request: RefinementRawHttpTestRequest) -> dict[str, Any]:
    provider = get_refinement_provider()
    if provider is None or not provider.is_enabled() or not hasattr(provider, "raw_http_test"):
        return {
            **_fallback_refinement_config(),
            "mode": request.mode,
            "http_status": None,
            "response_headers": {},
            "response_body_preview": "",
            "elapsed_ms": 0,
            "failure_reason": "missing_config",
            "failure_message": "Provider is not fully configured.",
        }

    normalized_mode = (request.mode or "with_model").strip().lower()
    include_model_field = request.include_model_field
    if include_model_field is None:
        include_model_field = normalized_mode != "without_model"
    system_prompt, user_prompt, max_tokens = _raw_http_test_prompt(request.query, request.max_tokens)
    timeout_seconds = _provider_timeout_for_mode("ping", provider.status_snapshot())
    return provider.raw_http_test(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=max_tokens,
        timeout_seconds=timeout_seconds,
        include_model_field=include_model_field,
        api_version_override=request.api_version,
    )


@app.post("/refinement/test")
def refinement_test(request: RefinementTestRequest) -> dict[str, Any]:
    provider = get_refinement_provider()
    safe_status = provider.status_snapshot() if provider is not None and hasattr(provider, "status_snapshot") else _fallback_refinement_config()
    mode = str(getattr(request, "mode", "refine") or "refine").strip().lower()
    include_model_field = getattr(request, "include_model_field", None)
    api_version = getattr(request, "api_version", None)
    provider_timeout_seconds = _provider_timeout_for_mode(mode, safe_status)
    diagnostic_timeout_seconds = _diagnostic_timeout_seconds(safe_status, provider_timeout_seconds)
    result = {
        "mode": mode,
        **safe_status,
        "phi_used": False,
        "phi_status": "not_configured" if not provider else "skipped",
        "raw_response_preview": "",
        "parsed_json": {},
        "parse_error": "",
        "validated_refinement": {},
        "fallback_used": False,
        "elapsed_ms": 0,
        "timeout_seconds": provider_timeout_seconds,
        "provider_timeout_seconds": provider_timeout_seconds,
        "diagnostic_timeout_seconds": diagnostic_timeout_seconds,
        "attempted_url_preview": str(safe_status.get("final_url_preview") or ""),
        "attempted_method": str(safe_status.get("method") or "POST"),
        "max_tokens": 0,
        "response_format_enabled": False,
        "include_model_field": include_model_field if include_model_field is not None else safe_status.get("include_model_field"),
        "json_mode_attempted": False,
        "json_mode_retry_without_response_format": False,
        "attempts": [],
        "failure_reason": "",
        "failure_message": "",
    }
    if provider is None or not provider.is_enabled():
        return result

    system_prompt, user_prompt, max_tokens = _refinement_test_prompt(request, mode)
    probe = getattr(provider, "probe_json", None)
    if not callable(probe):
        refined = refine_task(request.query, request.context)
        result["phi_used"] = bool(refined.get("phi_used"))
        result["phi_status"] = refined.get("phi_status", "skipped")
        result["validated_refinement"] = refined.get("refinement", {})
        result["fallback_used"] = refined.get("refinement_source") != "phi"
        return result

    probe_result = _run_refinement_probe_with_timeout(
        probe=probe,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=max_tokens,
        timeout_seconds=provider_timeout_seconds,
        diagnostic_timeout_seconds=diagnostic_timeout_seconds,
        response_format_enabled=False if mode == "ping" else None,
        allow_retry_without_response_format=False if mode == "ping" else True,
        include_model_field=include_model_field,
        api_version_override=api_version,
    )
    raw_preview = str(probe_result.get("raw_content", ""))[:1500]
    parsed_json = probe_result.get("parsed_json") if isinstance(probe_result.get("parsed_json"), dict) else {}
    if mode == "ping":
        validated = {}
        has_validated = parsed_json.get("status") == "ok"
    elif mode == "small_refine":
        validated = parsed_json
        has_validated = bool(parsed_json)
    else:
        validated = validate_task_refinement(parsed_json or {})
        has_validated = any(validated.get(key) for key in ("base_flows", "variants", "surfaces", "fields", "validations", "scope_hints", "unknowns"))
    parse_error = str(probe_result.get("parse_error") or "")
    failure_reason = str(probe_result.get("failure_reason") or "")
    failure_message = str(probe_result.get("failure_message") or "")
    if parse_error == "DiagnosticTimeout" or failure_reason == "diagnostic_timeout":
        phi_status = "diagnostic_timeout"
    elif parse_error == "TimeoutError" or failure_reason == "provider_timeout":
        phi_status = "provider_timeout"
    elif mode == "ping" and has_validated:
        phi_status = "success"
    else:
        phi_status = "used" if has_validated else ("unusable_response" if probe_result.get("http_status") else "unavailable")
    result.update(
        {
            "phi_used": bool(probe_result.get("http_status")),
            "phi_status": phi_status,
            "raw_response_preview": raw_preview,
            "parsed_json": parsed_json,
            "parse_error": parse_error,
            "validated_refinement": validated,
            "fallback_used": not has_validated,
            "elapsed_ms": int(probe_result.get("elapsed_ms") or 0),
            "timeout_seconds": int(probe_result.get("timeout_seconds") or provider_timeout_seconds),
            "provider_timeout_seconds": provider_timeout_seconds,
            "diagnostic_timeout_seconds": diagnostic_timeout_seconds,
            "attempted_url_preview": str(probe_result.get("attempted_url_preview") or ""),
            "attempted_method": str(probe_result.get("attempted_method") or "POST"),
            "max_tokens": int(probe_result.get("max_tokens") or max_tokens),
            "response_format_enabled": bool(probe_result.get("response_format_enabled")),
            "include_model_field": probe_result.get("include_model_field", include_model_field if include_model_field is not None else safe_status.get("include_model_field")),
            "json_mode_attempted": bool(probe_result.get("json_mode_attempted")),
            "json_mode_retry_without_response_format": bool(probe_result.get("json_mode_retry_without_response_format")),
            "attempts": probe_result.get("attempts") if isinstance(probe_result.get("attempts"), list) else [],
            "failure_reason": failure_reason,
            "failure_message": failure_message,
            "backend_status": probe_result.get("backend_status") or safe_status.get("backend_status"),
            "provider": probe_result.get("provider") or safe_status.get("provider"),
            "configured": bool(probe_result.get("configured", safe_status.get("configured"))),
            "enabled": bool(probe_result.get("enabled", safe_status.get("enabled"))),
            "endpoint_present": bool(probe_result.get("endpoint_present", safe_status.get("endpoint_present"))),
            "api_key_present": bool(probe_result.get("api_key_present", safe_status.get("api_key_present"))),
            "model": probe_result.get("model") or safe_status.get("model"),
            "api_version": probe_result.get("api_version") or safe_status.get("api_version"),
            "endpoint_host": str(probe_result.get("endpoint_host") or safe_status.get("endpoint_host") or ""),
            "endpoint_path": str(probe_result.get("endpoint_path") or safe_status.get("endpoint_path") or ""),
            "final_url_preview": str(probe_result.get("final_url_preview") or safe_status.get("final_url_preview") or ""),
            "method": str(probe_result.get("method") or safe_status.get("method") or "POST"),
        }
    )
    return result


@app.post("/refinement/smoke-test")
def refinement_smoke_test(request: RefinementSmokeTestRequest) -> dict[str, Any]:
    provider = get_refinement_provider()
    if provider is None or not provider.is_enabled():
        return {
            "provider": "azure_phi",
            "configured": False,
            "deployment": get_refiner_status().get("deployment"),
            "tests": [],
        }

    ping = _run_refinement_probe_with_timeout(
        probe=provider.probe_json,
        system_prompt="Return strict JSON only.",
        user_prompt='Return this exact JSON: {"status":"ok"}',
        max_tokens=50,
        timeout_seconds=_provider_timeout_for_mode("ping", provider.status_snapshot()),
        diagnostic_timeout_seconds=_diagnostic_timeout_seconds(provider.status_snapshot(), _provider_timeout_for_mode("ping", provider.status_snapshot())),
        response_format_enabled=False,
        allow_retry_without_response_format=False,
        include_model_field=request.include_model_field,
        api_version_override=request.api_version,
    )
    small = _run_refinement_probe_with_timeout(
        probe=provider.probe_json,
        system_prompt="Return strict JSON only.",
        user_prompt=f'Return JSON with: {{"domain":"","features":[]}}\\n\\nInput: {request.query}',
        max_tokens=220,
        timeout_seconds=_provider_timeout_for_mode("small_refine", provider.status_snapshot()),
        diagnostic_timeout_seconds=_diagnostic_timeout_seconds(provider.status_snapshot(), _provider_timeout_for_mode("small_refine", provider.status_snapshot())),
        response_format_enabled=False,
        allow_retry_without_response_format=False,
        include_model_field=request.include_model_field,
        api_version_override=request.api_version,
    )
    feature = refine_epic_stage(
        "feature_generation",
        request.context.get("work_item") if isinstance(request.context.get("work_item"), dict) else {"title": request.query, "description": request.context.get("description", "")},
        upstream={"generated_features": []},
        effective_context={"effective_text": str(request.query)},
    )
    return {
        "provider": "azure_phi",
        "configured": provider.is_enabled(),
        "deployment": provider.health_snapshot().get("deployment"),
        "health": provider.health_snapshot().get("health"),
        "tests": [
            {
                "name": "ping",
                "phi_status": "success" if isinstance(ping.get("parsed_json"), dict) and ping.get("parsed_json", {}).get("status") == "ok" else ping.get("failure_reason") or ping.get("status"),
                "elapsed_ms": ping.get("elapsed_ms"),
                "failure_reason": ping.get("failure_reason"),
                "attempts": ping.get("attempts", []),
            },
            {
                "name": "small_json_extraction",
                "phi_status": "success" if isinstance(small.get("parsed_json"), dict) and small.get("parsed_json") else small.get("failure_reason") or small.get("status"),
                "elapsed_ms": small.get("elapsed_ms"),
                "failure_reason": small.get("failure_reason"),
                "attempts": small.get("attempts", []),
            },
            {
                "name": "feature_generation",
                "provider_used": feature.get("provider_used"),
                "phi_status": feature.get("phi_status"),
                "elapsed_ms": None,
                "parsed": feature.get("parsed"),
            },
        ],
    }


def _refinement_test_prompt(request: RefinementTestRequest, mode: str) -> tuple[str, str, int]:
    max_tokens = max(1, int(getattr(request, "max_tokens", 300) or 300))
    if mode == "ping":
        return (
            "Return strict JSON only.",
            'Return this exact JSON: {"status":"ok"}',
            min(max_tokens, 50),
        )
    if mode == "small_refine":
        return (
            "Return strict JSON only.",
            (
                'Return JSON with: {"domain":"","features":[]}\n\n'
                f'Input: {request.query}'
            ),
            min(max_tokens, 300),
        )
    payload = {
        "query": request.query,
        "context": request.context,
        "expected_json_schema": {
            "base_flows": [],
            "variants": [],
            "surfaces": [],
            "fields": [],
            "validations": [],
            "scope_hints": [],
            "actors": [],
            "states": [],
            "unknowns": [],
            "confidence": "low|medium|high",
        },
    }
    return (
        "You are ai-gen semantic refinement engine. Return strict JSON only using canonical engineering metadata.",
        json.dumps(payload, ensure_ascii=True),
        min(max_tokens, 300),
    )


def _raw_http_test_prompt(query: str, max_tokens: int) -> tuple[str, str, int]:
    normalized_query = (query or "ping").strip() or "ping"
    if normalized_query.lower() == "ping":
        return (
            "Return JSON only.",
            'Return exactly {"status":"ok"}',
            min(max_tokens, 50),
        )
    return (
        "Return JSON only.",
        normalized_query,
        max_tokens,
    )


def _run_refinement_probe_with_timeout(
    probe: Any,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    timeout_seconds: int,
    diagnostic_timeout_seconds: int,
    response_format_enabled: Optional[bool] = None,
    allow_retry_without_response_format: bool = True,
    include_model_field: Optional[bool] = None,
    api_version_override: Optional[str] = None,
) -> dict[str, Any]:
    def invoke_probe() -> dict[str, Any]:
        kwargs = {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "max_tokens": max_tokens,
            "timeout_seconds": timeout_seconds,
            "response_format_enabled": response_format_enabled,
            "allow_retry_without_response_format": allow_retry_without_response_format,
            "include_model_field": include_model_field,
            "api_version_override": api_version_override,
        }
        try:
            signature = inspect.signature(probe)
        except (TypeError, ValueError):
            signature = None
        if signature is None:
            return probe(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
            )
        accepts_var_kwargs = any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())
        if accepts_var_kwargs:
            filtered_kwargs = {key: value for key, value in kwargs.items() if value is not None}
        else:
            filtered_kwargs = {
                key: value
                for key, value in kwargs.items()
                if key in signature.parameters and value is not None
            }
        return probe(**filtered_kwargs)

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(invoke_probe)
    try:
        result = future.result(timeout=diagnostic_timeout_seconds)
    except FutureTimeoutError:
        future.cancel()
        print(f"ai-gen phi probe hard_timeout seconds={diagnostic_timeout_seconds}")
        return {
            "backend_status": "ok",
            "provider": "azure_phi",
            "configured": True,
            "enabled": True,
            "endpoint_present": True,
            "api_key_present": True,
            "model": None,
            "api_version": None,
            "endpoint_host": "",
            "endpoint_path": "",
            "final_url_preview": "",
            "method": "POST",
            "http_status": None,
            "raw_content": "",
            "parsed_json": {},
            "parse_error": "DiagnosticTimeout",
            "elapsed_ms": diagnostic_timeout_seconds * 1000,
            "timeout_seconds": diagnostic_timeout_seconds,
            "attempted_url_preview": "",
            "attempted_method": "POST",
            "max_tokens": max_tokens,
            "response_format_enabled": bool(response_format_enabled),
            "json_mode_attempted": bool(response_format_enabled),
            "json_mode_retry_without_response_format": False,
            "failure_reason": "diagnostic_timeout",
            "failure_message": "Azure Phi diagnostic wrapper timed out before the provider returned.",
            "attempts": [
                {
                    "attempt_number": 1,
                    "url_preview": "",
                    "method": "POST",
                    "response_format_enabled": bool(response_format_enabled),
                    "http_status": None,
                    "status": "diagnostic_timeout",
                    "elapsed_ms": diagnostic_timeout_seconds * 1000,
                    "timeout_seconds": diagnostic_timeout_seconds,
                    "raw_response_preview": "",
                    "error_type": "DiagnosticTimeout",
                    "error_message": "Azure Phi diagnostic wrapper timed out before the provider returned.",
                }
            ],
        }
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    if isinstance(result, dict):
        return result
    return {
        "backend_status": "ok",
        "provider": "azure_phi",
        "configured": True,
        "http_status": None,
        "raw_content": "",
        "parsed_json": {},
        "parse_error": "NonDictProbeResult",
        "failure_reason": "parse_error",
        "failure_message": "Provider probe returned a non-dictionary result.",
    }


def _fallback_refinement_config() -> dict[str, Any]:
    status = get_refiner_status()
    timeout_seconds = _safe_int_env("AI_GEN_REFINER_TIMEOUT_SECONDS", 60)
    ping_timeout_seconds = _safe_int_env("AI_GEN_REFINER_PING_TIMEOUT_SECONDS", 60)
    diagnostic_timeout_seconds = max(_safe_int_env("AI_GEN_REFINER_DIAGNOSTIC_TIMEOUT_SECONDS", 180), timeout_seconds + 1)
    return {
        "backend_status": "ok",
        "provider": status.get("provider"),
        "configured": bool(status.get("configured")),
        "enabled": bool(status.get("enabled")),
        "endpoint_present": bool(status.get("endpoint_present")),
        "api_key_present": bool(status.get("api_key_present")),
        "model": status.get("model"),
        "api_version": status.get("api_version"),
        "endpoint_host": "",
        "endpoint_path": "",
        "final_url_preview": "",
        "method": "POST",
        "timeout_seconds": timeout_seconds,
        "ping_timeout_seconds": ping_timeout_seconds,
        "diagnostic_timeout_seconds": diagnostic_timeout_seconds,
        "include_model_field": os.getenv("AI_GEN_REFINER_INCLUDE_MODEL_FIELD", "true").strip().lower() not in {"0", "false", "no"},
        "max_tokens": _safe_int_env("AI_GEN_REFINER_MAX_TOKENS", 300),
        "response_format_enabled": os.getenv("AI_GEN_REFINER_RESPONSE_FORMAT_ENABLED", "1") != "0",
        "missing_env": [],
    }


def _safe_int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or str(default))
    except ValueError:
        return default


def _provider_timeout_for_mode(mode: str, safe_status: dict[str, Any]) -> int:
    if mode == "ping":
        env_value = _safe_int_env("AI_GEN_REFINER_PING_TIMEOUT_SECONDS", 60)
        return max(1, int(env_value or safe_status.get("ping_timeout_seconds") or 60))
    env_value = _safe_int_env("AI_GEN_REFINER_TIMEOUT_SECONDS", 60)
    return max(1, int(env_value or safe_status.get("timeout_seconds") or 60))


def _diagnostic_timeout_seconds(safe_status: dict[str, Any], provider_timeout_seconds: int) -> int:
    configured = max(1, _safe_int_env("AI_GEN_REFINER_DIAGNOSTIC_TIMEOUT_SECONDS", int(safe_status.get("diagnostic_timeout_seconds") or 180)))
    return max(configured, provider_timeout_seconds + 1)


@app.post("/context", response_model=ContextResponse)
def build_context(request: ContextRequest) -> ContextResponse:
    """Return a compact prompt that Codex can use for code generation."""

    print(f"ai-gen /context query={request.query[:120]!r}")
    work_item_context = _optimize_azure_work_item(request)
    effective_query = work_item_context.get("normalized_query") or request.query
    intent = detect_intent(effective_query)
    repo_state = _prepare_repo_context(request, intent, effective_query)
    result = context_builder.build_prompt(
        user_query=effective_query,
        max_tokens=request.max_tokens,
        logic_bias_scores=repo_state.get("logic_bias_scores"),
        bug_context=repo_state.get("bug_context"),
    )
    constraints = _extract_constraints(result["optimized_prompt"])
    initial_confidence = score_execution_confidence(
        intent=intent,
        matched_logic=result["matched_logic"][0] if result.get("matched_logic") else None,
        detected_flow=repo_state.get("detected_flow"),
        related_flows=repo_state.get("related_flows", []),
        planning_enabled=bool(result.get("planning_enabled")),
        retrieval_bias_applied=bool(repo_state.get("retrieval_bias_applied")),
        likely_bug_hotspots=repo_state.get("likely_bug_hotspots", []),
        critical_constraints=constraints,
    )
    refinement_allowed, refinement_reason = should_use_refiner(
        source=request.source,
        intent=intent,
        detected_flow=repo_state.get("detected_flow"),
        confidence_level=initial_confidence["level"],
        query=effective_query,
        work_item=request.work_item,
    )
    refinement_result = {
        "semantic_mapping_applied": False,
        "refinement_used": False,
        "refinement_source": "none",
        "refinement_reason": refinement_reason,
        "phi_used": False,
        "phi_status": "skipped",
        "phi_raw_response_preview": "",
        "refinement": {},
    }
    if refinement_allowed:
        refinement_result = refine_task(
            effective_query,
            {
                "source": request.source,
                "work_item": request.work_item,
                "intent": intent,
                "detected_flow": repo_state.get("detected_flow"),
                "constraints": constraints,
                "repo_hints": repo_state.get("session_bias_summary") or {},
            },
        )
    merged_refinement = _merge_refinement(
        repo_state=repo_state,
        work_item_context=work_item_context,
        confidence_level=initial_confidence["level"],
        refinement_result=refinement_result,
    )
    semantic_mapping_applied = _has_semantic_mapping(merged_refinement)
    confidence = score_execution_confidence(
        intent=intent,
        matched_logic=result["matched_logic"][0] if result.get("matched_logic") else None,
        detected_flow=repo_state.get("detected_flow"),
        related_flows=repo_state.get("related_flows", []),
        planning_enabled=bool(result.get("planning_enabled")),
        retrieval_bias_applied=bool(repo_state.get("retrieval_bias_applied")),
        likely_bug_hotspots=repo_state.get("likely_bug_hotspots", []),
        critical_constraints=constraints,
    )
    prompt_mode = detect_prompt_mode(
        query=effective_query,
        intent=intent,
        matched_logic=result["matched_logic"][0] if result.get("matched_logic") else None,
        detected_flow=merged_refinement.get("base_flow") or repo_state.get("detected_flow"),
        retrieval_bias_applied=bool(repo_state.get("retrieval_bias_applied")),
        likely_bug_hotspots=repo_state.get("likely_bug_hotspots", []),
        planning_enabled=bool(result.get("planning_enabled")),
        related_flows=repo_state.get("related_flows", []),
    )
    print(f"ai-gen execution mode={prompt_mode['mode']} reason={prompt_mode['reason']}")
    selected_files = select_execution_files(
        current_file=request.current_file or request.file_path,
        open_files=request.open_files,
        likely_bug_hotspots=repo_state.get("likely_bug_hotspots", []),
        detected_flow=repo_state.get("detected_flow"),
    )
    result["optimized_prompt"] = _mode_specific_prompt(
        mode=prompt_mode["mode"],
        query=effective_query,
        selected_files=selected_files,
        detected_flow=merged_refinement.get("base_flow") or repo_state.get("detected_flow"),
        related_flows=repo_state.get("related_flows", []),
        constraints=constraints,
        likely_bug_hotspots=repo_state.get("likely_bug_hotspots", []),
        fallback_prompt=result["optimized_prompt"],
        work_item_context=work_item_context,
        refined_metadata=merged_refinement,
    )
    result["token_estimate"] = _estimate_tokens(result["optimized_prompt"])
    route = detect_execution_target(
        query=effective_query,
        intent=intent,
        context_size=result["token_estimate"],
        routing_mode=request.routing_mode,
    )
    _update_repo_session(request, route["target"], result["token_estimate"], repo_state, effective_query)
    result.update(
        {
            "execution_target": route["target"],
            "execution_reason": route["reason"],
            "available_targets": get_available_targets(),
            "resolved_repo_id": repo_state.get("repo_id"),
            "resolved_branch_name": repo_state.get("branch_name"),
            "retrieval_bias_applied": bool(repo_state.get("retrieval_bias_applied")),
            "session_bias_summary": repo_state.get("session_bias_summary"),
            "repo_identity_mode": repo_state.get("identity_mode"),
            "repo_identity_source": repo_state.get("identity_source"),
            "indexing_performed": bool(repo_state.get("indexing_performed")),
            "incremental_update_performed": bool(repo_state.get("incremental_update_performed")),
            "changed_files_count": int(repo_state.get("changed_files_count", 0)),
            "detected_flow": repo_state.get("detected_flow"),
            "related_flows": repo_state.get("related_flows", []),
            "flow_files_count": int(repo_state.get("flow_files_count", 0)),
            "bug_surface": repo_state.get("bug_surface"),
            "likely_bug_hotspots": repo_state.get("likely_bug_hotspots", []),
            "prompt_mode": prompt_mode["mode"],
            "prompt_mode_reason": prompt_mode["reason"],
            "execution_confidence": confidence["score"],
            "execution_confidence_level": confidence["level"],
            "execution_confidence_signals": confidence["signals"],
            "selected_execution_files": selected_files,
            "execution_validation": None,
            "drift_detected": False,
            "constraint_violations": [],
            "risky_changes": [],
            "work_item_optimized": bool(work_item_context),
            "work_item_task_summary": work_item_context.get("task_summary"),
            "work_item_surface": work_item_context.get("technical_surface"),
            "work_item_scope": work_item_context.get("likely_scope", []),
            "semantic_mapping_applied": semantic_mapping_applied,
            "refinement_used": semantic_mapping_applied,
            "refinement_source": refinement_result.get("refinement_source") or ("canonical_normalizer" if semantic_mapping_applied else "none"),
            "refinement_provider": refinement_result.get("refinement_provider"),
            "refinement_reason": refinement_result.get("refinement_reason", ""),
            "phi_used": bool(refinement_result.get("phi_used")),
            "phi_status": refinement_result.get("phi_status", "skipped"),
            "phi_raw_response_preview": refinement_result.get("phi_raw_response_preview", ""),
            "refined_base_flows": merged_refinement.get("base_flows", []),
            "refined_variants": merged_refinement.get("variants", []),
            "refined_surfaces": merged_refinement.get("surfaces", []),
            "refined_base_flow": merged_refinement.get("base_flow"),
            "refined_variant": merged_refinement.get("variant"),
            "refined_surface": merged_refinement.get("surface"),
            "refined_fields": merged_refinement.get("fields", []),
            "refined_validations": merged_refinement.get("validations", []),
            "refined_scope": merged_refinement.get("scope_hints", []) or merged_refinement.get("first_pass_scope", []),
            "refined_actors": merged_refinement.get("actors", []),
            "refined_states": merged_refinement.get("states", []),
            "refinement_unknowns": merged_refinement.get("unknowns", []),
            "refinement_confidence": merged_refinement.get("confidence") or refinement_result.get("refinement", {}).get("confidence"),
        }
    )
    return ContextResponse(**result)


@app.post("/execution/snapshot")
def execution_snapshot(request: ExecutionSnapshotRequest) -> dict:
    """Capture selected-file hashes before execute-mode work starts."""

    return {
        "baseline_hashes": snapshot_selected_files(request.repo_root, request.selected_files),
    }


@app.post("/execution/validate")
def validate_execution_result(request: ExecutionValidationRequest) -> dict:
    """Validate post-execution changes for execute-mode handoffs."""

    if request.prompt_mode != "execute":
        result = {
            "drift_detected": False,
            "drift_score": 0.0,
            "out_of_scope_files": [],
            "constraint_violations": [],
            "risky_changes": [],
            "summary": "Validation skipped because prompt mode is not execute.",
        }
        return {
            "execution_validation": result,
            "drift_detected": False,
            "constraint_violations": [],
            "risky_changes": [],
            "retry_required": False,
            "retry_plan": {},
            "corrected_execution_prompt": "",
        }

    context = ExecutionContext(
        selected_files=request.selected_files,
        allowed_flows=request.allowed_flows,
        constraints=request.constraints,
        likely_breakpoints=request.likely_breakpoints,
        baseline_hashes=request.baseline_hashes,
    )
    result = validate_execution(
        context=context,
        repo_root=request.repo_root,
        changed_files=request.changed_files,
    )
    retry_plan = generate_retry_plan(
        validation_result=result,
        original_execution_context={
            "constraints": request.constraints,
            "likely_breakpoints": request.likely_breakpoints,
        },
        selected_files=request.selected_files,
        detected_flow=request.detected_flow,
        related_flows=request.related_flows or request.allowed_flows,
    )
    previous_issues = _previous_execution_issues(result)
    corrected_prompt = build_corrected_execution_prompt(
        query=request.query or "Retry execution",
        retry_plan=retry_plan,
        detected_flow=request.detected_flow,
        related_flows=request.related_flows or request.allowed_flows,
        previous_issues=previous_issues,
    )
    return {
        "execution_validation": result,
        "drift_detected": result["drift_detected"],
        "constraint_violations": result["constraint_violations"],
        "risky_changes": result["risky_changes"],
        "retry_required": retry_plan["retry_required"],
        "retry_plan": retry_plan,
        "corrected_execution_prompt": corrected_prompt,
    }


@app.post("/assist/pipeline/create")
def create_assistant_pipeline(request: PipelineCreateRequest) -> dict:
    """Create a new structured assistant pipeline."""

    return pipeline_controller.create_pipeline(
        work_item=request.work_item,
        source=request.source,
        repo_context=request.repo_context,
        refinement=request.refinement,
        ai_gen_comments=request.ai_gen_comments,
        team_comments=request.team_comments,
        epic_context=request.epic_context,
    )


@app.post("/assist/pipeline/{pipeline_id}/run-stage")
def run_pipeline_stage(pipeline_id: str, request: PipelineStageRequest) -> dict:
    """Run a single stage in the structured assistant pipeline."""

    if request.regenerate and (request.feedback_comment or "").strip():
        pipeline_controller.add_stage_feedback(
            pipeline_id,
            request.stage,
            request.feedback_comment or "",
            author=request.feedback_author,
        )
    return pipeline_controller.run_stage(
        pipeline_id,
        request.stage,
        regenerate=request.regenerate,
        ai_gen_comments=request.ai_gen_comments,
        team_comments=request.team_comments if request.team_comments else None,
    )


@app.post("/assist/pipeline/{pipeline_id}/run-epic-plan")
def run_pipeline_epic_plan(pipeline_id: str, request: PipelineStageRequest) -> dict:
    """Run the full Epic Planning flow in one user action."""

    return pipeline_controller.run_epic_plan(
        pipeline_id,
        ai_gen_comments=request.ai_gen_comments,
        team_comments=request.team_comments if request.team_comments else None,
    )


@app.post("/assist/pipeline/{pipeline_id}/run-feature-plan")
def run_pipeline_feature_plan(pipeline_id: str, request: PipelineStageRequest) -> dict:
    """Run the full Feature Planning flow in one user action (feature_analysis → story_generation → review)."""
    return pipeline_controller.run_feature_plan(
        pipeline_id,
        ai_gen_comments=request.ai_gen_comments,
        team_comments=request.team_comments if request.team_comments else None,
    )


@app.post("/assist/pipeline/{pipeline_id}/approve-stage")
def approve_pipeline_stage(pipeline_id: str, request: PipelineApproveRequest) -> dict:
    """Approve a generated stage and unlock the next one."""

    # --- Role-based gate check ---
    role_result = validate_approver_role(request.stage, request.approver_role)
    if not role_result["allowed"]:
        return JSONResponse(
            status_code=403,
            content={
                "error": "Forbidden",
                "detail": role_result["reason"],
                "required_roles": role_result["required_roles"],
                "stage": request.stage,
            },
        )

    # --- Guardrail: screen current stage output before approving ---
    try:
        pipeline_state = pipeline_controller.get_pipeline(pipeline_id)
        stage_output = (pipeline_state.get("stages") or {}).get(request.stage, {}).get("output") or {}
        constraints = (
            pipeline_state.get("repo_context") or {}
        ).get("constraints") or []
        violations = guard_stage_output(request.stage, stage_output, constraints)
        if has_blocking_violation(violations):
            return JSONResponse(
                status_code=422,
                content={
                    "error": "GuardrailBlock",
                    "detail": "Stage output failed safety guardrails and cannot be approved.",
                    "violations": [v.to_dict() for v in violations if v.severity == "block"],
                },
            )
    except Exception as guard_err:
        logger.warning("ai-gen guardrail check failed (non-blocking): %s", guard_err)

    result = pipeline_controller.approve_stage(
        pipeline_id,
        request.stage,
        approved_by=request.approved_by,
    )

    # Attach advisory guardrail warnings to response (non-blocking)
    try:
        warn_violations = [v.to_dict() for v in violations if v.severity == "warn"]  # type: ignore[possibly-undefined]
        if warn_violations:
            if isinstance(result, dict):
                result.setdefault("guardrail_warnings", warn_violations)
    except Exception:
        pass

    return result


@app.post("/assist/pipeline/{pipeline_id}/skip-stage")
def skip_pipeline_stage(pipeline_id: str, request: PipelineSkipRequest) -> dict:
    """Skip a stage with an explicit reason."""

    return pipeline_controller.skip_stage(pipeline_id, request.stage, request.reason)


@app.post("/assist/pipeline/{pipeline_id}/stage-feedback")
def add_pipeline_stage_feedback(pipeline_id: str, request: PipelineStageFeedbackRequest) -> dict:
    """Store reviewer clarification for a stage so regeneration can reuse it."""

    return pipeline_controller.add_stage_feedback(
        pipeline_id,
        request.stage,
        request.comment,
        author=request.author,
    )


# ── Phase 2: VS Code Live Feedback ───────────────────────────────────────────

class VsCodeEventRequest(BaseModel):
    """Event pushed from the VS Code extension into the pipeline."""

    event_type: str = Field(
        ...,
        description=(
            "Type of VS Code event: 'file_saved' | 'test_run' | "
            "'code_generated' | 'user_comment' | 'mark_ready'"
        ),
    )
    stage: Optional[str] = Field(default=None, description="Pipeline stage this event relates to.")
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Event-specific payload (file path, content hash, comment text, etc.)",
    )
    author: Optional[str] = Field(default=None, description="VS Code username or machine identifier.")


@app.post("/assist/pipeline/{pipeline_id}/vscode-event")
def record_vscode_event(pipeline_id: str, request: VsCodeEventRequest) -> dict:
    """Accept a live event from VS Code and attach it to the pipeline.

    Supports:
    - ``file_saved``: records file path + content hash for drift tracking.
    - ``user_comment``: appends a clarification from the developer.
    - ``mark_ready``: shortcut to approve the active stage directly from VS Code.
    - ``test_run`` / ``code_generated``: logged as activity for audit trail.
    """
    import time as _time

    event = {
        "source": "vscode",
        "event_type": request.event_type,
        "stage": request.stage,
        "author": request.author or "vscode",
        "payload": request.payload,
        "timestamp": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
    }

    if request.event_type == "user_comment" and request.stage:
        comment = str(request.payload.get("comment") or "").strip()
        if comment:
            pipeline_controller.add_stage_feedback(
                pipeline_id,
                request.stage,
                comment,
                author=request.author or "vscode",
            )

    if request.event_type == "mark_ready" and request.stage:
        try:
            return pipeline_controller.approve_stage(
                pipeline_id,
                request.stage,
                approved_by=request.author or "vscode",
            )
        except Exception as exc:
            return JSONResponse(
                status_code=400,
                content={"error": "ApprovalFailed", "detail": str(exc)},
            )

    try:
        state = pipeline_controller.get_pipeline(pipeline_id)
        if isinstance(state, dict):
            activity = state.get("activity") or []
            activity.append(event)
            state["activity"] = activity
        return state
    except Exception as exc:
        logger.warning("vscode-event: could not load pipeline %s: %s", pipeline_id, exc)
        return {"recorded": True, "event": event}


@app.get("/assist/pipeline/{pipeline_id}/pending-review")
def get_pending_review(pipeline_id: str) -> dict:
    """Return stages that are generated but not yet approved.

    The VS Code extension polls this every 30 seconds and surfaces a
    notification badge when a stage is ready for human review.
    """
    try:
        state = pipeline_controller.get_pipeline(pipeline_id)
    except Exception as exc:
        return JSONResponse(
            status_code=404,
            content={"error": "PipelineNotFound", "detail": str(exc)},
        )

    stages: dict = state.get("stages") or {}
    pending_stages = []
    for stage_name, stage_state in stages.items():
        if not isinstance(stage_state, dict):
            continue
        status = stage_state.get("status", "")
        approved = stage_state.get("approved", False)
        has_findings = bool(stage_state.get("unresolved_findings"))
        if status in {"generated", "needs_revision"} and not approved:
            pending_stages.append({
                "stage": stage_name,
                "status": status,
                "has_unresolved_findings": has_findings,
                "handoff_id": stage_state.get("handoff_id"),
                "version": stage_state.get("version", 1),
            })

    return {
        "pipeline_id": pipeline_id,
        "work_item_id": state.get("work_item_id"),
        "current_stage": state.get("current_stage"),
        "pending_stages": pending_stages,
        "has_pending": bool(pending_stages),
        "guardrail_warnings": state.get("guardrail_warnings", []),
    }


# ── Phase 3: ADO Automation ───────────────────────────────────────────────────

class AdoAutomationRequest(BaseModel):
    stage: str = Field(..., description="The pipeline stage to trigger ADO automation for.")
    approved_by: Optional[str] = None


class AdoWebhookRequest(BaseModel):
    """ADO Service Hook payload (common fields only — rest in ``raw``)."""

    eventType: Optional[str] = None
    resource: Optional[dict[str, Any]] = None
    resourceVersion: Optional[str] = None
    publisherId: Optional[str] = None
    message: Optional[dict[str, Any]] = None

    model_config = {"extra": "allow"}


@app.post("/assist/pipeline/{pipeline_id}/trigger-ado-automation")
def trigger_ado_automation(pipeline_id: str, request: AdoAutomationRequest) -> dict:
    """Trigger ADO side effects (state update, comment, PR) for an approved stage.

    Called automatically from the approve-stage endpoint when
    ``AI_GEN_ADO_AUTO=1`` is set, or manually by the ADO extension.
    """
    if not ado_automation.is_available:
        return JSONResponse(
            status_code=503,
            content={
                "error": "AdoNotConfigured",
                "detail": "ADO_PAT, ADO_ORG_URL and ADO_PROJECT must be set to enable automation.",
            },
        )
    try:
        pipeline_state = pipeline_controller.get_pipeline(pipeline_id)
    except Exception as exc:
        return JSONResponse(
            status_code=404,
            content={"error": "PipelineNotFound", "detail": str(exc)},
        )

    result = ado_automation.run_for_stage(
        pipeline_id=pipeline_id,
        stage=request.stage,
        pipeline_state=pipeline_state,
    )
    status_code = 207 if result.has_failures else 200
    return JSONResponse(status_code=status_code, content=result.to_dict())


@app.get("/assist/pipeline/{pipeline_id}/ado-automation-status")
def get_ado_automation_status(pipeline_id: str) -> dict:
    """Return ADO automation availability and configuration status."""
    return {
        "pipeline_id": pipeline_id,
        "ado_configured": ado_automation.is_available,
        "auto_trigger_enabled": os.getenv("AI_GEN_ADO_AUTO", "0") == "1",
        "supported_stages": list(
            {"ba", "ui", "dev_packet", "fix_packet", "test_checklist",
             "test_planning", "critic", "epic_analysis", "story_generation"}
        ),
    }


@app.post("/webhooks/ado")
def ado_service_hook(request: AdoWebhookRequest) -> dict:
    """Receive Azure DevOps service hook events.

    Supported event types
    ---------------------
    ``workitem.updated``
        When a work item state changes in ADO, sync the pipeline state.
    ``git.pullrequest.merged``
        When a PR is merged, advance the pipeline to the next stage.

    Set up in ADO:
    Project Settings → Service Hooks → Web Hooks → Subscribe to events.
    Point to: ``POST https://<your-backend>/webhooks/ado``
    """
    event_type = str(request.eventType or "").strip()
    resource = request.resource or {}

    logger.info("ADO webhook received: event_type=%s", event_type)

    if event_type == "workitem.updated":
        work_item_id = str(
            resource.get("workItemId")
            or (resource.get("fields") or {}).get("System.Id", {}).get("newValue", "")
            or ""
        ).strip()
        new_state = str(
            (resource.get("fields") or {}).get("System.State", {}).get("newValue", "")
        ).strip()
        if work_item_id and new_state:
            logger.info("ADO webhook: work_item=%s state→%s", work_item_id, new_state)
        return {"received": True, "event_type": event_type, "work_item_id": work_item_id}

    if event_type == "git.pullrequest.merged":
        pr_id = str(resource.get("pullRequestId", "")).strip()
        source_branch = str(resource.get("sourceRefName", "")).strip()
        logger.info("ADO webhook: PR #%s merged from %s", pr_id, source_branch)
        return {"received": True, "event_type": event_type, "pr_id": pr_id}

    # Unknown event — acknowledge but do nothing
    return {"received": True, "event_type": event_type, "action": "ignored"}


# ── Phase 5: Open Questions Loop ──────────────────────────────────────────────

class QuestionAnswer(BaseModel):
    question: str
    answer: str


class AnswerQuestionsRequest(BaseModel):
    stage: str = Field(..., description="Stage the questions belong to (e.g. 'ba', 'bug_analysis').")
    answers: list[QuestionAnswer] = Field(default_factory=list)


@app.post("/assist/pipeline/{pipeline_id}/answer-questions")
def answer_open_questions(pipeline_id: str, request: AnswerQuestionsRequest) -> dict:
    """Submit user answers to open questions and trigger stage re-run.

    The sidebar shows each ``open_question`` item as a text input.
    When the user submits, this endpoint:
      1. Stores the answers in pipeline stage feedback
      2. Sets stage status back to 'pending' so it can be re-run
      3. Returns the updated pipeline state

    The next ``run_stage`` call will pick up the answers via
    ``effective_context.question_answers`` and pass them to the assistant.
    """
    if not request.answers:
        return JSONResponse(
            status_code=400,
            content={"error": "NoAnswers", "detail": "At least one answer is required."},
        )

    # Store each answer as stage feedback so the assistant picks it up
    for qa in request.answers:
        combined = f"Q: {qa.question}\nA: {qa.answer}"
        pipeline_controller.add_stage_feedback(
            pipeline_id,
            request.stage,
            combined,
            author="user_answer",
        )

    # Re-run the stage with the answers injected
    try:
        updated = pipeline_controller.run_stage(
            pipeline_id,
            request.stage,
            regenerate=True,
        )
        return updated
    except Exception as exc:
        # Return the pipeline as-is if re-run fails; answers are already stored
        logger.warning("answer-questions re-run failed: %s", exc)
        try:
            return pipeline_controller.get_pipeline(pipeline_id)
        except Exception:
            return JSONResponse(
                status_code=500,
                content={"error": "ReRunFailed", "detail": str(exc)},
            )


# ── Phase 5: SDLC Prompt Builder ──────────────────────────────────────────────

@app.get("/assist/pipeline/{pipeline_id}/prompts")
def get_pipeline_prompts(pipeline_id: str) -> dict:
    """Return the UI prompt and coding dev prompt for the current pipeline.

    SDLC order:
      - ``ui_prompt``  is available after BA stage is approved
      - ``dev_prompt`` is available after UI stage is approved

    The ADO extension shows:
      - 'Copy UI Prompt' button (available after BA approval)
      - 'Copy Dev Prompt' button (available after UI approval)
    """
    from backend.prompt_builder import build_ui_prompt, build_dev_prompt

    try:
        state = pipeline_controller.get_pipeline(pipeline_id)
    except Exception as exc:
        return JSONResponse(
            status_code=404,
            content={"error": "PipelineNotFound", "detail": str(exc)},
        )

    stages = state.get("stages") or {}
    work_item = state.get("work_item") or {}

    # Collect approved stage outputs
    ba_out = (stages.get("ba") or {}).get("output") or {}
    ui_out = (stages.get("ui") or stages.get("ui_optional") or {}).get("output") or {}
    dev_out = (stages.get("dev_packet") or stages.get("task_analysis") or {}).get("output") or {}
    test_out = (stages.get("test_planning") or stages.get("test_checklist") or {}).get("output") or {}
    repo_ctx = state.get("repo_context") or {}
    epic_ctx = _extract_epic_context(state)

    ba_approved = bool((stages.get("ba") or {}).get("approved"))
    ui_approved = bool(
        (stages.get("ui") or {}).get("approved")
        or (stages.get("ui_optional") or {}).get("approved")
    )

    ui_prompt = ""
    dev_prompt = ""

    if ba_approved and ba_out:
        ui_prompt = build_ui_prompt(
            ba_output=ba_out,
            ui_output=ui_out or None,
            work_item=work_item,
            epic_context=epic_ctx,
        )

    if ui_approved and ba_out:
        dev_prompt = build_dev_prompt(
            ba_output=ba_out,
            dev_output=dev_out or None,
            ui_output=ui_out or None,
            repo_context=repo_ctx,
            work_item=work_item,
            epic_context=epic_ctx,
            test_output=test_out or None,
        )

    return {
        "pipeline_id": pipeline_id,
        "ba_approved": ba_approved,
        "ui_approved": ui_approved,
        "ui_prompt": ui_prompt,
        "dev_prompt": dev_prompt,
        "ui_prompt_available": ba_approved and bool(ba_out),
        "dev_prompt_available": ui_approved and bool(ba_out),
    }


# ── Phase 5: Bug Suggestion (critic-triggered) ────────────────────────────────

class SuggestBugRequest(BaseModel):
    stage: str = Field(default="critic", description="Stage that produced the blocking findings.")
    work_item_id: Optional[str] = None


@app.post("/assist/pipeline/{pipeline_id}/suggest-bug")
def suggest_bug_from_findings(pipeline_id: str, request: SuggestBugRequest) -> dict:
    """Generate a structured bug draft from critic blocking findings.

    Called when the critic stage produces blocking findings. Returns a
    ``bug_draft`` dict that the ADO extension renders as a preview before
    the user chooses to create it in ADO.

    This is Option C: critic blocking findings → suggest bug creation.
    The user still manually decides whether to create the ADO Bug work item.
    """
    from backend.assistants.bug_assistant import run_bug_assistant

    try:
        state = pipeline_controller.get_pipeline(pipeline_id)
    except Exception as exc:
        return JSONResponse(
            status_code=404,
            content={"error": "PipelineNotFound", "detail": str(exc)},
        )

    stages = state.get("stages") or {}
    critic_stage = stages.get(request.stage) or stages.get("critic") or {}
    critic_output = critic_stage.get("output") or {}
    critic_findings = critic_output.get("findings") or []

    blocking = [f for f in critic_findings if f.get("severity") in {"blocking", "high"}]
    if not blocking:
        return JSONResponse(
            status_code=400,
            content={
                "error": "NoBlockingFindings",
                "detail": "No blocking findings found. Bug suggestion requires at least one blocking critic finding.",
            },
        )

    work_item = state.get("work_item") or {}
    epic_ctx = _extract_epic_context(state)
    effective_context = {"epic_context": epic_ctx}

    bug_draft = run_bug_assistant(
        work_item=work_item,
        critic_findings=blocking,
        effective_context=effective_context,
    )
    return {
        "pipeline_id": pipeline_id,
        "source_stage": request.stage,
        "finding_count": len(blocking),
        "bug_draft": bug_draft,
        "create_instructions": (
            "Review the bug draft above, then use the 'Create Bug' button "
            "to create it as an ADO Bug work item under this Epic/Story."
        ),
    }


def _extract_epic_context(state: dict) -> dict:
    """Pull epic_context from pipeline state if available."""
    ctx = state.get("epic_context") or {}
    if ctx:
        return ctx
    # Fall back to pipeline context epic fields
    pc = state.get("pipeline_context") or {}
    epic_title = str(pc.get("epic_title") or "").strip()
    epic_ac = str(pc.get("epic_acceptance_criteria") or "").strip()
    if epic_title or epic_ac:
        return {"title": epic_title, "acceptance_criteria": epic_ac}
    return {}


@app.get("/assist/pipeline/{pipeline_id}")
def get_assistant_pipeline(pipeline_id: str) -> dict:
    """Return the current structured pipeline state."""

    return pipeline_controller.get_pipeline(pipeline_id)


@app.get("/assist/pipeline")
def get_assistant_pipeline_for_work_item(work_item_id: str) -> dict:
    """Return the latest structured pipeline state for a work item."""

    return pipeline_controller.get_pipeline_for_work_item(work_item_id) or {}


@app.get("/assist/pipeline/{pipeline_id}/draft-work-items")
def get_pipeline_draft_work_items(pipeline_id: str) -> dict:
    """Return the current draft work items for a planning-oriented pipeline."""

    return pipeline_controller.get_draft_work_items(pipeline_id)


@app.post("/assist/pipeline/{pipeline_id}/draft-work-items/approve")
def approve_pipeline_draft_work_items(pipeline_id: str, request: DraftWorkItemApproveRequest) -> dict:
    """Approve selected draft work items before creation."""

    return pipeline_controller.approve_draft_work_items(pipeline_id, request.draft_ids)


@app.post("/assist/pipeline/{pipeline_id}/draft-work-items/create")
def create_pipeline_draft_work_items(pipeline_id: str, request: DraftWorkItemCreateRequest) -> dict:
    """Return Azure DevOps work item creation payloads for selected drafts."""

    return pipeline_controller.create_draft_work_items(
        pipeline_id,
        request.draft_ids,
        create_child_tasks=request.create_child_tasks,
    )


@app.post("/assist/pipeline/{pipeline_id}/draft-work-items/created")
def mark_pipeline_draft_work_items_created(pipeline_id: str, request: DraftWorkItemsCreatedRequest) -> dict:
    """Record created Azure DevOps work item ids against draft ids."""

    return pipeline_controller.mark_draft_work_items_created(pipeline_id, request.created_items)


@app.post("/assist/pipeline/{pipeline_id}/work-item-creation-result")
def store_pipeline_work_item_creation_result(pipeline_id: str, request: DraftWorkItemsCreatedRequest) -> dict:
    """Record Azure DevOps creation results for generated work item drafts."""

    return pipeline_controller.mark_draft_work_items_created(pipeline_id, request.created_items)


@app.get("/handoffs/{handoff_id}")
def get_handoff_by_id(handoff_id: str) -> dict:
    """Return a single stored handoff artifact."""

    handoff = pipeline_controller.load_handoff(handoff_id)
    return _serialize_handoff(handoff)


@app.get("/handoffs/{handoff_id}/markdown", response_class=PlainTextResponse)
def get_handoff_markdown(handoff_id: str) -> str:
    """Return the markdown form of a stored handoff artifact."""

    return load_handoff_markdown(handoff_id) or ""


@app.get("/handoffs")
def get_handoffs(work_item_id: str, stage: Optional[str] = None, status: Optional[str] = None) -> dict:
    """List stored handoffs, optionally filtered by stage and status."""

    if stage:
        handoff = pipeline_controller.latest_handoff(work_item_id, stage, status=status)
        return {"items": [_serialize_handoff(handoff)] if handoff else []}

    handoffs = list_handoffs(work_item_id)
    if status:
        handoffs = [item for item in handoffs if item.get("status") == status]
    return {"items": [_serialize_handoff(handoff) for handoff in handoffs]}


def _serialize_handoff(handoff: Optional[dict]) -> dict:
    if not handoff:
        return {}
    content = handoff.get("content") if isinstance(handoff.get("content"), dict) else {}
    serialized = dict(handoff)
    serialized["execution_packet"] = content.get("execution_packet", "")
    serialized["selected_files"] = list(content.get("selected_files", [])) if isinstance(content.get("selected_files"), list) else []
    serialized["constraints"] = list(handoff.get("constraints", []))
    serialized["open_questions"] = list(handoff.get("open_questions", []))
    serialized["refinement"] = handoff.get("refinement", {}) if isinstance(handoff.get("refinement"), dict) else {}
    return serialized


def _prepare_repo_context(request: ContextRequest, intent: str, query: str) -> dict:
    """Best-effort repo identity resolution, auto-init, and bias calculation."""

    workspace_root = request.workspace_root or ""
    if not (request.repo_id or workspace_root):
        return {}
    try:
        resolved = repo_context_manager.resolve_or_register_repo(
            repo_id=request.repo_id,
            repo_root=workspace_root or None,
            git_remote=request.git_remote,
            branch_name=request.branch_name,
        )
        repo_id = resolved["repo_id"]
        branch_name = resolved["branch_name"]
        session_id = request.session_id or f"session_{uuid4().hex[:12]}"
        index_state = _refresh_repo_index(repo_id, branch_name, workspace_root)
        session = repo_context_manager.load_session(repo_id, session_id)
        base = repo_context_manager.load_base_context(repo_id)
        branch = repo_context_manager.load_branch_overlay(repo_id, branch_name)
        effective = merge_effective_context(base, branch, session)
        current_file = request.current_file or request.file_path
        initial_bias = collect_session_bias_signals(effective, current_file, request.open_files)
        detected_flow = _infer_detected_flow(
            query,
            initial_bias.get("current_flow", ""),
            effective.get("file_index", []),
            index_state.get("detected_flows", []),
        )
        relationships = build_flow_relationships(
            effective.get("effective_logic_units", []),
            effective.get("effective_graph", {}),
        )
        related_flows = get_related_flows(detected_flow, relationships, max_depth=1)
        bias_signals = collect_session_bias_signals(effective, current_file, request.open_files, related_flows=related_flows)
        ranked_logic = rank_logic_units_with_bias(effective.get("effective_logic_units", []), bias_signals, query)
        logic_bias_scores = {logic_id: score for logic_id, score in ranked_logic if score > 0}
        bug_surface = detect_bug_surface(query) if intent == "bug_fix" else None
        likely_bug_hotspots = (
            score_bug_hotspots(
                query=query,
                detected_flow=detected_flow,
                related_flows=related_flows,
                file_index=effective.get("file_index", []),
                changed_files=effective.get("changed_files", {}),
                current_file=current_file,
                open_files=request.open_files,
            )
            if intent == "bug_fix"
            else []
        )
        all_related_flows = sorted(
            set(
                index_state.get("detected_flows", [])
                + related_flows
                + ([detected_flow] if detected_flow else [])
            )
        )
        return {
            **resolved,
            "session_id": session_id,
            "effective_context": effective,
            "logic_bias_scores": logic_bias_scores,
            "retrieval_bias_applied": bool(logic_bias_scores),
            **index_state,
            "session_bias_summary": {
                "current_file": current_file,
                "open_files_count": len(request.open_files),
                "changed_files_count": len(bias_signals.get("changed_files", [])),
                "module": bias_signals.get("current_module", ""),
                "flow": bias_signals.get("current_flow", ""),
            },
            "detected_flow": detected_flow or None,
            "related_flows": all_related_flows,
            "flow_files_count": _flow_files_count(effective, detected_flow),
            "bug_surface": bug_surface,
            "likely_bug_hotspots": likely_bug_hotspots,
            "bug_context": {
                "related_flows": related_flows,
                "likely_bug_hotspots": likely_bug_hotspots,
            },
        }
    except (OSError, ValueError):
        return {}


def _refresh_repo_index(repo_id: str, branch_name: str, workspace_root: str) -> dict:
    """Bootstrap or refresh repo index without making /context depend on it."""

    if not workspace_root:
        return {}
    try:
        paths = repo_context_manager.paths(repo_id)
        file_index = read_json(paths.file_index, default=[])
        summaries = read_json(paths.summaries, default=[])
        if not file_index or not summaries:
            result = bootstrap_repo_index(repo_id, workspace_root, storage_root=repo_context_manager.storage_root)
            return {
                "indexing_performed": True,
                "incremental_update_performed": False,
                "changed_files_count": 0,
                "indexing_partial": result.get("partial", False),
                "detected_flows": result.get("detected_flows", []),
            }
        result = update_changed_files(repo_id, branch_name, workspace_root, storage_root=repo_context_manager.storage_root)
        return {
            "indexing_performed": False,
            "incremental_update_performed": bool(result.get("updated_files")),
            "changed_files_count": len(result.get("changed_files", [])),
            "detected_flows": result.get("detected_flows", []),
        }
    except OSError:
        return {}


def _flow_files_count(effective_context: dict, flow: str) -> int:
    if not flow:
        return 0
    return sum(
        1 for record in effective_context.get("file_index", [])
        if record.get("flow") == flow
    )


def _mode_specific_prompt(
    mode: str,
    query: str,
    selected_files: list[str],
    detected_flow: Optional[str],
    related_flows: list[str],
    constraints: list[str],
    likely_bug_hotspots: list[dict],
    fallback_prompt: str,
    work_item_context: Optional[dict] = None,
    refined_metadata: Optional[dict] = None,
) -> str:
    """Build the final handoff prompt, falling back to existing formatting if needed."""

    try:
        if mode == "execute":
            return build_execution_packet(
                query=query,
                selected_files=selected_files,
                detected_flow=detected_flow,
                related_flows=related_flows,
                constraints=constraints,
                likely_bug_hotspots=likely_bug_hotspots,
                refined_metadata=_combine_prompt_refinement(work_item_context, refined_metadata),
            )
        if mode == "respond":
            return build_response_packet(
                query=query,
                detected_flow=detected_flow,
                related_flows=related_flows,
                constraints=constraints,
            )
        if mode == "explore":
            return build_exploration_packet(
                query=query,
                detected_flow=detected_flow,
                related_flows=related_flows,
                constraints=constraints,
            )
    except (KeyError, TypeError, ValueError):
        return fallback_prompt
    return fallback_prompt


def _combine_prompt_refinement(work_item_context: Optional[dict], refined_metadata: Optional[dict]) -> dict[str, Any]:
    combined = dict(refined_metadata or {})
    if work_item_context:
        if not combined.get("surface"):
            combined["surface"] = work_item_context.get("technical_surface")
        combined["scope_hints"] = _dedupe(
            list(combined.get("scope_hints", []))
            + list(combined.get("first_pass_scope", []))
            + list(work_item_context.get("likely_scope", []))
        )[:8]
        combined["first_pass_scope"] = list(combined["scope_hints"])
        combined["focus_rules"] = _dedupe(
            list(combined.get("focus_rules", [])) + list(work_item_context.get("inferred_focus_rules", []))
        )[:8]
    return combined


def _extract_constraints(prompt: str) -> list[str]:
    """Extract compact constraints from the existing full prompt."""

    constraints: list[str] = []
    in_constraints = False
    for line in prompt.splitlines():
        stripped = line.strip()
        if stripped in {"## Constraints", "## Critical Constraints", "# Constraints"}:
            in_constraints = True
            continue
        if in_constraints and stripped.startswith("#"):
            break
        if in_constraints and stripped.startswith("- "):
            value = stripped[2:].strip()
            if value and value not in constraints:
                constraints.append(value)
        elif in_constraints and stripped.startswith("If the requested change conflicts"):
            continue
    return constraints


def _estimate_tokens(prompt: str) -> int:
    """Approximate tokens using the same dependency-free word count convention."""

    return len(prompt.split())


def _has_semantic_mapping(refinement: dict[str, Any]) -> bool:
    return any(
        refinement.get(key)
        for key in ("base_flows", "variants", "surfaces", "fields", "validations", "scope_hints", "actors", "states", "unknowns")
    )


def _previous_execution_issues(validation_result: dict) -> list[str]:
    """Summarize validation issues for retry prompt context."""

    issues: list[str] = []
    if validation_result.get("out_of_scope_files"):
        issues.append("scope drift detected")
    if validation_result.get("constraint_violations"):
        issues.append("constraint violation detected")
    if validation_result.get("risky_changes"):
        issues.append("risky changes detected")
    return issues


def _infer_detected_flow(query: str, current_flow: str, file_index: list[dict], indexed_flows: list[str]) -> str:
    """Infer a primary flow from editor context first, then query/index hints."""

    if current_flow:
        return current_flow
    available_flows = _ordered_flows(file_index, indexed_flows)
    normalized_query = query.lower()
    for flow in available_flows:
        if flow and flow in normalized_query:
            return flow
    return available_flows[0] if len(available_flows) == 1 else ""


def _ordered_flows(file_index: list[dict], indexed_flows: list[str]) -> list[str]:
    flows: list[str] = []
    for flow in indexed_flows:
        if flow and flow not in flows:
            flows.append(flow)
    for record in file_index:
        flow = record.get("flow")
        if flow and flow not in flows:
            flows.append(flow)
    return flows


def _update_repo_session(
    request: ContextRequest,
    execution_target: str,
    token_estimate: int,
    repo_state: dict,
    effective_query: Optional[str] = None,
) -> None:
    """Persist optional IDE session metadata without making repo context mandatory."""

    repo_id = repo_state.get("repo_id") or request.repo_id
    if not repo_id:
        return

    try:
        branch_name = repo_state.get("branch_name") or request.branch_name or "default"
        session_id = repo_state.get("session_id") or request.session_id or f"session_{uuid4().hex[:12]}"
        existing = repo_context_manager.load_session(repo_id, session_id) or {}
        session = SessionContext(
            session_id=session_id,
            repo_id=repo_id,
            branch_name=branch_name,
            ide=request.ide or existing.get("ide", ""),
            workspace_root=request.workspace_root or existing.get("workspace_root", ""),
            current_file=request.current_file or request.file_path or existing.get("current_file", ""),
            open_files=request.open_files or existing.get("open_files", []),
            selected_text=request.selected_text or existing.get("selected_text", ""),
            current_task=effective_query or request.query,
            last_query=effective_query or request.query,
            last_execution_target=execution_target,
            last_prompt_token_estimate=token_estimate,
            created_at=existing.get("created_at") or SessionContext(session_id, repo_id, branch_name).created_at,
        )
        repo_context_manager.save_session(session)
    except OSError:
        return


def _optimize_azure_work_item(request: ContextRequest) -> dict:
    """Optimize Azure DevOps work item requests without affecting IDE callers."""

    if (request.source or "").lower() != "azure_devops":
        return {}

    work_item = request.work_item or {}
    title = _work_item_text(work_item, "title") or request.query
    description = _work_item_text(work_item, "description")
    acceptance = (
        _work_item_text(work_item, "acceptanceCriteria")
        or _work_item_text(work_item, "acceptance_criteria")
    )
    tags_value = work_item.get("tags")
    tags = [str(tag) for tag in tags_value if tag] if isinstance(tags_value, list) else []
    return optimize_work_item_request(
        title=title,
        description=description,
        acceptance_criteria=acceptance,
        tags=tags,
        work_item_type=_work_item_text(work_item, "type"),
        area_path=_work_item_text(work_item, "areaPath") or _work_item_text(work_item, "area_path"),
        iteration_path=_work_item_text(work_item, "iterationPath") or _work_item_text(work_item, "iteration_path"),
    )


def _work_item_text(work_item: dict, key: str) -> str:
    value = work_item.get(key)
    return str(value).strip() if value is not None else ""


def _merge_refinement(
    repo_state: dict,
    work_item_context: dict,
    confidence_level: str,
    refinement_result: dict,
) -> dict[str, Any]:
    refinement = dict(refinement_result.get("refinement") or {})
    deterministic_flow = (repo_state.get("detected_flow") or "").strip()
    suggested_flows = list(refinement.get("base_flows", []))
    suggested_flow = (_first_nonempty(suggested_flows) or refinement.get("base_flow") or "").strip()
    final_flow = deterministic_flow
    if not deterministic_flow or confidence_level in {"low", "medium"}:
        final_flow = suggested_flow or deterministic_flow
    elif suggested_flow and suggested_flow != deterministic_flow:
        refinement["flow_suggestion"] = suggested_flow

    if final_flow:
        refinement["base_flows"] = _dedupe([final_flow] + list(refinement.get("base_flows", [])))
        refinement["base_flow"] = final_flow

    if not refinement.get("surface") and not refinement.get("surfaces") and work_item_context.get("technical_surface"):
        refinement["surface"] = work_item_context["technical_surface"]
        refinement["surfaces"] = _dedupe([work_item_context["technical_surface"]])
    elif refinement.get("surface") and not refinement.get("surfaces"):
        refinement["surfaces"] = _dedupe([refinement["surface"]])

    refinement["scope_hints"] = _dedupe(
        list(refinement.get("scope_hints", []))
        + list(refinement.get("first_pass_scope", []))
        + list(work_item_context.get("likely_scope", []))
    )[:8]
    refinement["first_pass_scope"] = list(refinement["scope_hints"])
    refinement["focus_rules"] = _dedupe(
        list(work_item_context.get("inferred_focus_rules", []))
    )[:8]
    refinement["variant"] = _first_nonempty(refinement.get("variants", [])) or refinement.get("variant")
    refinement["surface"] = _first_nonempty(refinement.get("surfaces", [])) or refinement.get("surface")
    repo_state["detected_flow"] = final_flow or repo_state.get("detected_flow")
    return refinement


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in output:
            output.append(normalized)
    return output


def _first_nonempty(values: list[str]) -> str:
    for value in values:
        normalized = str(value).strip()
        if normalized:
            return normalized
    return ""


@app.get("/repo-context/{repo_id}")
def get_repo_context(repo_id: str) -> dict:
    """Return base repo context when available."""

    return repo_context_manager.load_base_context(repo_id)


@app.get("/repo-context/{repo_id}/branch/{branch_name}")
def get_repo_branch_context(repo_id: str, branch_name: str, session_id: Optional[str] = None) -> dict:
    """Return effective base + branch + optional session context."""

    base = repo_context_manager.load_base_context(repo_id)
    branch = repo_context_manager.load_branch_overlay(repo_id, branch_name)
    session = repo_context_manager.load_session(repo_id, session_id) if session_id else None
    return merge_effective_context(base, branch, session)



# ── Audit Trail (A) ────────────────────────────────────────────────────────────

@app.get("/audit/events")
def get_audit_events(pipeline_id: Optional[str] = None, event_type: Optional[str] = None, limit: int = 200) -> dict:
    """Return recent audit events, newest-first. Optionally filter by pipeline_id or event_type."""
    events = audit_get_events(pipeline_id=pipeline_id, event_type=event_type, limit=limit)
    return {"events": events, "count": len(events)}


@app.get("/audit/summary")
def get_audit_summary(pipeline_id: Optional[str] = None) -> dict:
    """Return aggregate counts per event_type across all audit events."""
    return audit_get_summary(pipeline_id=pipeline_id)


# ── Pipeline Metrics (A) ───────────────────────────────────────────────────────

@app.get("/metrics/pipelines")
def get_pipeline_metrics() -> dict:
    """Return aggregate health metrics across all pipelines saved on disk."""
    import glob
    data_dir = pipeline_controller.root
    pipeline_files = sorted(data_dir.glob("pipeline_*.json"))
    total = len(pipeline_files)
    by_template: dict[str, int] = {}
    by_status: dict[str, int] = {}
    approved_count = 0
    recent_errors: list[dict] = []
    for path in pipeline_files:
        raw = read_json(path, default=None)
        if not raw:
            continue
        tpl = str(raw.get("workflow_template") or "unknown")
        by_template[tpl] = by_template.get(tpl, 0) + 1
        for stage_name, stage in (raw.get("stages") or {}).items():
            status = str(stage.get("status") or "unknown")
            by_status[status] = by_status.get(status, 0) + 1
            if stage.get("approved"):
                approved_count += 1
            for finding in (stage.get("unresolved_findings") or []):
                if finding.get("severity") == "blocking":
                    recent_errors.append({
                        "pipeline_id": raw.get("pipeline_id"),
                        "stage": stage_name,
                        "message": finding.get("message"),
                    })
    return {
        "total_pipelines": total,
        "by_workflow_template": by_template,
        "stage_status_counts": by_status,
        "total_approved_stages": approved_count,
        "blocking_findings_count": len(recent_errors),
        "blocking_findings_sample": recent_errors[:10],
    }


# ── Story Planner Session List (B) ─────────────────────────────────────────────

@app.get("/story-planner/sessions")
def list_story_planner_sessions(work_item_id: Optional[str] = None) -> dict:
    """List all story planner sessions, optionally filtered by work_item_id."""
    sessions = story_planner_service.list_sessions(work_item_id=work_item_id)
    return {"sessions": sessions, "count": len(sessions)}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "backend.app:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )
