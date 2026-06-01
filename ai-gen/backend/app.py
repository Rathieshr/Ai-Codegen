"""FastAPI backend for generating Codex-ready business context."""

import os
import json
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from backend.execution_corrector import build_corrected_execution_prompt, generate_retry_plan
from backend.handoff.storage import list_handoffs, load_handoff_markdown
from backend.execution_mode import detect_prompt_mode, score_execution_confidence
from backend.execution_validator import ExecutionContext, snapshot_selected_files, validate_execution
from backend.intent_detector import detect_intent
from backend.model_router import detect_execution_target, get_available_targets
from backend.orchestrator.react_controller import PipelineController
from backend.refinement.provider import get_refiner_status, get_refinement_provider
from backend.refinement.refinement_decider import should_use_refiner
from backend.refinement.schema_validator import validate_task_refinement
from backend.refinement.task_refiner import refine_task
from backend.repo_context.bug_localizer import detect_bug_surface, score_bug_hotspots
from backend.repo_context.cross_flow import build_flow_relationships, get_related_flows
from backend.repo_context.indexer import bootstrap_repo_index, update_changed_files
from backend.repo_context.manager import RepoContextManager, merge_effective_context
from backend.repo_context.models import SessionContext
from backend.repo_context.storage import read_json
from backend.repo_context.retrieval_bias import collect_session_bias_signals, rank_logic_units_with_bias
from backend.status import get_status
from backend.work_item_optimizer import optimize_work_item_request
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
print(f"ai-gen backend starting in {os.getenv('AI_GEN_BACKEND_MODE', 'local')} mode")

logic_store = LogicStore()
context_builder = ContextBuilder(logic_store=logic_store)
repo_context_manager = RepoContextManager(
    Path(os.getenv("AI_GEN_REPO_CONTEXT_ROOT", ".ai_gen_repo_context"))
)
pipeline_controller = PipelineController(Path(os.getenv("AI_GEN_PIPELINE_ROOT", ".ai_gen_pipelines")))


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


class PipelineStageRequest(BaseModel):
    stage: str
    regenerate: bool = False
    feedback_comment: Optional[str] = None
    feedback_author: Optional[str] = None
    ai_gen_comments: list[dict[str, Any]] = Field(default_factory=list)


class PipelineApproveRequest(BaseModel):
    stage: str
    approved_by: Optional[str] = None


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


@app.get("/health")
def health() -> dict[str, str]:
    """Lightweight readiness check for local CLI calls."""

    return {"status": "ok"}


@app.get("/capabilities")
def capabilities() -> dict:
    """Return lightweight routing capabilities."""

    return get_status()


@app.get("/refinement/health")
def refinement_health() -> dict[str, Any]:
    """Return non-secret refiner configuration status."""

    return get_refiner_status()


@app.post("/refinement/test")
def refinement_test(request: RefinementTestRequest) -> dict[str, Any]:
    provider = get_refinement_provider()
    status = get_refiner_status()
    result = {
        "provider": status.get("provider"),
        "configured": bool(status.get("configured")),
        "phi_used": False,
        "phi_status": "not_configured" if not provider else "skipped",
        "raw_response_preview": "",
        "parsed_json": {},
        "parse_error": "",
        "validated_refinement": {},
        "fallback_used": False,
    }
    if provider is None or not provider.is_enabled():
        return result

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
    probe = getattr(provider, "probe_json", None)
    if not callable(probe):
        refined = refine_task(request.query, request.context)
        result["phi_used"] = bool(refined.get("phi_used"))
        result["phi_status"] = refined.get("phi_status", "skipped")
        result["validated_refinement"] = refined.get("refinement", {})
        result["fallback_used"] = refined.get("refinement_source") != "phi"
        return result

    probe_result = probe(
        system_prompt=(
            "You are ai-gen semantic refinement engine. Return strict JSON only using canonical engineering metadata."
        ),
        user_prompt=json.dumps(payload, ensure_ascii=True),
        max_tokens=800,
    )
    raw_preview = str(probe_result.get("raw_content", ""))[:1500]
    parsed_json = probe_result.get("parsed_json") if isinstance(probe_result.get("parsed_json"), dict) else {}
    validated = validate_task_refinement(parsed_json or {})
    has_validated = any(validated.get(key) for key in ("base_flows", "variants", "surfaces", "fields", "validations", "scope_hints", "unknowns"))
    result.update(
        {
            "phi_used": bool(probe_result.get("http_status")),
            "phi_status": "used" if has_validated else ("unusable_response" if probe_result.get("http_status") else "unavailable"),
            "raw_response_preview": raw_preview,
            "parsed_json": parsed_json,
            "parse_error": str(probe_result.get("parse_error") or ""),
            "validated_refinement": validated,
            "fallback_used": not has_validated,
        }
    )
    return result


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
    )


@app.post("/assist/pipeline/{pipeline_id}/run-epic-plan")
def run_pipeline_epic_plan(pipeline_id: str, request: PipelineStageRequest) -> dict:
    """Run the full Epic Planning flow in one user action."""

    return pipeline_controller.run_epic_plan(
        pipeline_id,
        ai_gen_comments=request.ai_gen_comments,
    )


@app.post("/assist/pipeline/{pipeline_id}/approve-stage")
def approve_pipeline_stage(pipeline_id: str, request: PipelineApproveRequest) -> dict:
    """Approve a generated stage and unlock the next one."""

    return pipeline_controller.approve_stage(pipeline_id, request.stage, approved_by=request.approved_by)


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


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "backend.app:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )
