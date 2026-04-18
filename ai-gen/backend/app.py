"""FastAPI backend for generating Codex-ready business context."""

import os
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI
from pydantic import BaseModel, Field

from backend.execution_corrector import build_corrected_execution_prompt, generate_retry_plan
from backend.execution_mode import detect_prompt_mode, score_execution_confidence
from backend.execution_validator import ExecutionContext, snapshot_selected_files, validate_execution
from backend.intent_detector import detect_intent
from backend.model_router import detect_execution_target, get_available_targets
from backend.repo_context.bug_localizer import detect_bug_surface, score_bug_hotspots
from backend.repo_context.cross_flow import build_flow_relationships, get_related_flows
from backend.repo_context.indexer import bootstrap_repo_index, update_changed_files
from backend.repo_context.manager import RepoContextManager, merge_effective_context
from backend.repo_context.models import SessionContext
from backend.repo_context.storage import read_json
from backend.repo_context.retrieval_bias import collect_session_bias_signals, rank_logic_units_with_bias
from backend.status import get_status
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

logic_store = LogicStore()
context_builder = ContextBuilder(logic_store=logic_store)
repo_context_manager = RepoContextManager(
    Path(os.getenv("AI_GEN_REPO_CONTEXT_ROOT", ".ai_gen_repo_context"))
)


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


@app.get("/health")
def health() -> dict[str, str]:
    """Lightweight readiness check for local CLI calls."""

    return {"status": "ok"}


@app.get("/capabilities")
def capabilities() -> dict:
    """Return lightweight routing capabilities."""

    return get_status()


@app.post("/context", response_model=ContextResponse)
def build_context(request: ContextRequest) -> ContextResponse:
    """Return a compact prompt that Codex can use for code generation."""

    intent = detect_intent(request.query)
    repo_state = _prepare_repo_context(request, intent)
    result = context_builder.build_prompt(
        user_query=request.query,
        max_tokens=request.max_tokens,
        logic_bias_scores=repo_state.get("logic_bias_scores"),
        bug_context=repo_state.get("bug_context"),
    )
    constraints = _extract_constraints(result["optimized_prompt"])
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
        query=request.query,
        intent=intent,
        matched_logic=result["matched_logic"][0] if result.get("matched_logic") else None,
        detected_flow=repo_state.get("detected_flow"),
        retrieval_bias_applied=bool(repo_state.get("retrieval_bias_applied")),
        likely_bug_hotspots=repo_state.get("likely_bug_hotspots", []),
        planning_enabled=bool(result.get("planning_enabled")),
        related_flows=repo_state.get("related_flows", []),
    )
    selected_files = select_execution_files(
        current_file=request.current_file or request.file_path,
        open_files=request.open_files,
        likely_bug_hotspots=repo_state.get("likely_bug_hotspots", []),
        detected_flow=repo_state.get("detected_flow"),
    )
    result["optimized_prompt"] = _mode_specific_prompt(
        mode=prompt_mode["mode"],
        query=request.query,
        selected_files=selected_files,
        detected_flow=repo_state.get("detected_flow"),
        related_flows=repo_state.get("related_flows", []),
        constraints=constraints,
        likely_bug_hotspots=repo_state.get("likely_bug_hotspots", []),
        fallback_prompt=result["optimized_prompt"],
    )
    result["token_estimate"] = _estimate_tokens(result["optimized_prompt"])
    route = detect_execution_target(
        query=request.query,
        intent=intent,
        context_size=result["token_estimate"],
        routing_mode=request.routing_mode,
    )
    _update_repo_session(request, route["target"], result["token_estimate"], repo_state)
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


def _prepare_repo_context(request: ContextRequest, intent: str) -> dict:
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
            request.query,
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
        ranked_logic = rank_logic_units_with_bias(effective.get("effective_logic_units", []), bias_signals, request.query)
        logic_bias_scores = {logic_id: score for logic_id, score in ranked_logic if score > 0}
        bug_surface = detect_bug_surface(request.query) if intent == "bug_fix" else None
        likely_bug_hotspots = (
            score_bug_hotspots(
                query=request.query,
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


def _update_repo_session(request: ContextRequest, execution_target: str, token_estimate: int, repo_state: dict) -> None:
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
            current_task=request.query,
            last_query=request.query,
            last_execution_target=execution_target,
            last_prompt_token_estimate=token_estimate,
            created_at=existing.get("created_at") or SessionContext(session_id, repo_id, branch_name).created_at,
        )
        repo_context_manager.save_session(session)
    except OSError:
        return


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
