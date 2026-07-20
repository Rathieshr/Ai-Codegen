"""Phase 2 Project Intelligence preview profile service."""

from __future__ import annotations

import json
import logging
import os
import hashlib
import re
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.artifacts import ArtifactEngine
from backend.engineering_memory import MemoryContextBuilder
from backend.execution import build_execution_package_v2
from backend.intelligence_trace import TraceEngine
from backend.implementation_validation import validate_implementation
from backend.intelligence.capability import buildCapabilityContext
from backend.intelligence.dna import compareDNA, generateDNA, validateDNA
from backend.intelligence.epic_analysis import analyzeEpic, buildCapabilityReview
from backend.intelligence.epic_analysis.epic_analysis import CapabilityCandidate, CapabilityPriority
from backend.intelligence.intent import build_intent
from backend.intelligence.planning import buildPlanningContext
from backend.intelligence.reasoning import generatePlanningArtifact
from backend.intelligence.story_analysis import StoryAnalysisEngine, analyzeFeatureStories
from backend.intelligence.validation import validateArtifact
from backend.prompt_budget import (
    PromptSection,
    budgetProfileForProvider,
    buildPrompt,
    estimateTokens as promptBudgetEstimateTokens,
    probe_json_with_budget,
)
from backend.prompt_builder import build_developer_prompt_v2, build_execution_plan
from backend.qa import AcceptanceCoverageEngine, QAWorkspaceService, TestGapAnalyzer
from backend.pr_review import PRReviewEngine, review_pr
from backend.refinement.provider import get_refiner_status, get_refinement_provider
from backend.repository_intelligence.infrastructure import RepositoryContextCapsuleBuilder
from backend.skills import SkillEngine


logger = logging.getLogger("ai_gen.project_intelligence")

PROJECT_CONTEXT_MIN_TOKENS = 300
PROJECT_CONTEXT_MAX_TOKENS = 800
PROJECT_CONTEXT_DEFAULT_TOKENS = 600
PROJECT_CONTEXT_RETRY_BUDGETS = [600, 450, 300]
PROJECT_CONTEXT_RESERVED_TOKENS = 150
PROJECT_EXECUTION_OPERATIONS = {
    "build_execution_context",
    "build_dev_prompt",
    "build_ui_prompt",
    "build_qa_prompt",
    "build_copilot_context",
    "generate_qa_test_cases",
}
PROJECT_EXECUTION_BUDGET_ATTEMPTS = [
    {"draft_budget": 220, "context_budget": 350},
    {"draft_budget": 160, "context_budget": 250},
    {"draft_budget": 120, "context_budget": 180},
]
PROJECT_EXECUTION_DRAFT_DEFAULT_TOKENS = 200
PROJECT_EXECUTION_DRAFT_MAX_TOKENS = 300
PROJECT_EXECUTION_SCHEMA_BUDGET_TOKENS = 100
PROJECT_PHI_SYSTEM_PROMPT = (
    "Return ONLY valid JSON. No markdown. No explanation. No prose. No code fences. "
    'If unable, return {"error":"..."} as valid JSON.'
)
PROJECT_PHI_INSTRUCTION = (
    "Use the compact project context. Return only the requested JSON keys. "
    "Return ONLY valid JSON with no markdown, no prose, and no code fences. "
    'If unable, return {"error":"..."} as valid JSON.'
)
PROJECT_PROVIDER_PROMPT_CHAR_LIMIT = 4800


KNOWN_REPOSITORY_DOCUMENTS = [
    "README.md",
    "docs/README.md",
    "architecture.md",
    "docs/architecture.md",
    "modules.md",
    "docs/modules.md",
    "flows.md",
    "docs/flows.md",
    "ui-guidelines.md",
    "docs/ui-guidelines.md",
    "coding-standards.md",
    "docs/coding-standards.md",
]

DEFAULT_PROFILE: dict[str, Any] = {
    "onboarding_completed": False,
    "project_id": "",
    "project_name": "",
    "domain": "",
    "project_type": "",
    "project_description": "",
    "connectors": {
        "azure_devops": {
            "organization_url": "",
            "ado_project": "",
            "repository_id": "",
            "repository_name": "",
            "branch": "main",
        },
    },
    "repository_connection": {
        "repository_id": "",
        "repository_name": "",
        "branch": "",
        "status": "Not connected",
        "readme_path": "/README.md",
    },
    "readme_analysis": {
        "summary": "",
        "applications": [],
        "modules": [],
        "flows": [],
        "architecture_notes": [],
    },
    "knowledge_registry": {
        "applications": [],
        "modules": [],
        "module_details": [],
        "flows": [],
        "flow_details": [],
        "components": [],
        "component_details": [],
        "architecture_notes": [],
        "technology_stack": {},
        "standards": [],
        "source_files": [],
    },
    "applications": [],
    "technology_stack": {
        "mobile": [],
        "backend": [],
        "firmware": [],
        "analytics": [],
        "frontend": [],
    },
    "development_standards": {
        "architecture_patterns": [],
        "coding_guidelines": [],
        "security_requirements": [],
        "testing_requirements": [],
    },
    "ui_guidelines": {
        "primary_color": "",
        "secondary_color": "",
        "typography": "",
        "component_library": "",
        "accessibility_rules": [],
    },
    "repository_sources": [],
    "knowledge_profile_preview": {
        "domain": "",
        "systems": [],
        "standards": [],
        "repository_status": "Repository README scan coming next.",
        "readiness": "Basic",
    },
}


class ProjectIntelligenceService:
    def __init__(self) -> None:
        data_dir = Path(os.getenv("AI_GEN_DATA_DIR", str(Path(__file__).parent.parent / "data")))
        self._profile_dir = data_dir / "project_intelligence"
        self._profile_path = self._profile_dir / "profile.json"
        self._profiles_dir = self._profile_dir / "profiles"
        self._session_path = self._profile_dir / "session.json"
        self._knowledge_cache_path = self._profile_dir / "knowledge_cache.json"
        self._artifacts_path = self._profile_dir / "artifacts.json"
        self._capsules_path = self._profile_dir / "context_capsules.json"
        self._profile_path.parent.mkdir(parents=True, exist_ok=True)
        self._profiles_dir.mkdir(parents=True, exist_ok=True)
        self._memory_context_builder = MemoryContextBuilder()
        self._trace_engine = TraceEngine()
        self._skill_engine = SkillEngine()

    def get_profile(self) -> dict[str, Any]:
        if not self._profile_path.exists():
            return _normalize_profile({})
        try:
            return _normalize_profile(json.loads(self._profile_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            return _normalize_profile({})

    def save_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_profile(profile)
        normalized["onboarding_completed"] = True
        self._profile_path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
        if normalized.get("project_id"):
            profile_path = self._profiles_dir / f"{_safe_profile_id(normalized['project_id'])}.json"
            profile_path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
        return normalized

    def get_session(self) -> dict[str, Any]:
        if not self._session_path.exists():
            return {"exists": False, "session": {}}
        try:
            session = json.loads(self._session_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"exists": False, "session": {}}
        return {"exists": True, "session": _normalize_project_session(session)}

    def save_session(self, session: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_project_session(session)
        normalized["saved_at"] = _now_iso()
        self._session_path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
        return {"exists": True, "session": normalized}

    def _memory_context(
        self,
        purpose: str,
        profile: dict[str, Any],
        artifact_type: str,
        work_item: dict[str, Any],
        modules: list[str] | None = None,
        flows: list[str] | None = None,
        acceptance_criteria: list[str] | None = None,
        repository_files: list[str] | None = None,
        capability: str = "",
    ) -> dict[str, Any]:
        project_id = _clean_text(profile.get("project_id")) or _clean_text(profile.get("project_name")) or "default"
        return self._memory_context_builder.build(
            purpose=purpose,
            project_id=project_id,
            artifact_type=artifact_type,
            work_item=work_item,
            modules=modules or [],
            flows=flows or [],
            acceptance_criteria=acceptance_criteria or [],
            repository_files=repository_files or [],
            capability=capability,
        )

    def _trace_decision(
        self,
        *,
        profile: dict[str, Any],
        artifact_type: str,
        artifact: dict[str, Any],
        stage: str,
        source: str,
        decision: str,
        reason: str,
        confidence: float,
        evidence: list[Any] | None = None,
        memory_context: dict[str, Any] | None = None,
        repository_evidence: list[Any] | None = None,
        graph_evidence: list[Any] | None = None,
        validation_result: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        provider_metadata = metadata or {}
        trace = self._trace_engine.record_decision(
            project_id=_clean_text(profile.get("project_id")) or _clean_text(profile.get("project_name")) or "default",
            artifact_type=artifact_type,
            artifact_id=_clean_text(artifact.get("id") or artifact.get("artifactId") or artifact.get("artifact_id") or artifact.get("title")),
            artifact_title=_clean_text(artifact.get("title")),
            stage=stage,
            source=source,
            decision=decision,
            reason=reason,
            confidence=confidence,
            evidence=evidence or [],
            memory_used=(memory_context or {}).get("relevantMemories", []) if isinstance(memory_context, dict) else [],
            repository_evidence=repository_evidence or [],
            graph_evidence=graph_evidence or [],
            validation_result=validation_result or {},
            prompt_version=_clean_text(provider_metadata.get("promptBudgetProfile") or provider_metadata.get("prompt_version") or "deterministic-v1"),
            latency_ms=int(provider_metadata.get("phi_latency_ms") or provider_metadata.get("latency_ms") or provider_metadata.get("elapsed_ms") or 0),
            model=_clean_text(provider_metadata.get("provider_deployment") or provider_metadata.get("model") or provider_metadata.get("provider_used")),
            token_usage={
                "prompt_tokens": provider_metadata.get("phi_prompt_tokens") or provider_metadata.get("prompt_tokens"),
                "completion_tokens": provider_metadata.get("phi_completion_tokens") or provider_metadata.get("completion_tokens"),
                "final_prompt_tokens": provider_metadata.get("final_prompt_tokens"),
            },
            metadata=provider_metadata,
        )
        return {
            "trace_id": trace["id"],
            "trace": trace,
            "trace_summary": {
                "decision": trace["decision"],
                "reason": trace["reason"],
                "confidence": trace["confidence"],
                "stage": trace["stage"],
                "memory_count": len(trace.get("memoryUsed", [])),
                "repository_evidence_count": len(trace.get("repositoryEvidence", [])),
                "graph_evidence_count": len(trace.get("graphEvidence", [])),
            },
        }

    def get_knowledge_cache(self) -> dict[str, Any]:
        cache = self._read_knowledge_cache()
        if not cache:
            return {"exists": False, "cache": {}, **self.knowledge_cache_status()}
        return {"exists": True, "cache": cache, **self.knowledge_cache_status()}

    def get_context_capsules(self) -> dict[str, Any]:
        capsules = self._read_context_capsules()
        return {
            "exists": bool(capsules),
            "capsules": capsules,
            "status": _capsule_status_payload(capsules, self.get_profile(), self._read_knowledge_cache()),
        }

    def refresh_context_capsules(
        self,
        profile: dict[str, Any] | None = None,
        item: dict[str, Any] | None = None,
        capsule_types: list[str] | None = None,
    ) -> dict[str, Any]:
        active_profile = _normalize_profile(profile or self.get_profile())
        cache = self._read_knowledge_cache()
        existing = self._read_context_capsules()
        requested = [kind for kind in (capsule_types or ["project"]) if kind in _context_capsule_types()] or ["project"]
        now = _now_iso()
        capsules = {key: value for key, value in existing.items() if isinstance(value, dict)}
        for capsule_type in requested:
            source_item = item or {}
            capsule = _build_context_capsule(capsule_type, active_profile, source_item, cache, existing.get(capsule_type))
            capsule["created_at"] = now
            capsules[capsule_type] = capsule
        self._write_context_capsules(capsules)
        return {
            "success": True,
            "capsules": capsules,
            "status": _capsule_status_payload(capsules, active_profile, cache),
        }

    def knowledge_cache_status(
        self,
        project_id: str = "",
        repository_id: str = "",
        branch: str = "",
        document_hashes: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        cache = self._read_knowledge_cache()
        profile = self.get_profile()
        if not cache:
            mapping = self.resolve_connector_mapping(profile=profile)
            return _knowledge_status_payload(
                profile=profile,
                mapping=mapping,
                status="missing",
                last_analyzed_at="",
                source_files=[],
                document_hashes={},
                changed_files=[],
                invalidation_reasons=["cached knowledge is missing"],
            )
        mapping = cache.get("repository_mapping") if isinstance(cache.get("repository_mapping"), dict) else {}
        expected_project_id = _clean_text(project_id) or _clean_text(profile.get("project_id")) or _clean_text(cache.get("project_id"))
        expected_repository_id = _clean_text(repository_id) or _clean_text(profile.get("repository_connection", {}).get("repository_id")) or _clean_text(mapping.get("repository_id"))
        expected_branch = _clean_text(branch) or _clean_text(profile.get("repository_connection", {}).get("branch")) or _clean_text(mapping.get("branch"))
        cached_hashes = cache.get("document_hashes") if isinstance(cache.get("document_hashes"), dict) else {}
        changed_files = []
        for path, current_hash in (document_hashes or {}).items():
            cached_hash = cached_hashes.get(path)
            if cached_hash and cached_hash != current_hash:
                changed_files.append(path)
        reasons = []
        if expected_project_id and _clean_text(cache.get("project_id")) and expected_project_id != _clean_text(cache.get("project_id")):
            reasons.append("project id changed")
        if expected_repository_id and _clean_text(mapping.get("repository_id")) and expected_repository_id != _clean_text(mapping.get("repository_id")):
            reasons.append("repository changed")
        if expected_branch and _clean_text(mapping.get("branch")) and expected_branch != _clean_text(mapping.get("branch")):
            reasons.append("branch changed")
        if cache.get("schema_version") != _knowledge_schema_version():
            reasons.append("knowledge schema version changed")
        if changed_files:
            reasons.append("source document hash changed")
        status = "ready"
        if reasons:
            status = "refresh_available" if changed_files and len(reasons) == 1 else "stale"
        return _knowledge_status_payload(
            profile=cache.get("profile") if isinstance(cache.get("profile"), dict) else profile,
            mapping=mapping,
            status=status,
            last_analyzed_at=_clean_text(cache.get("last_analyzed_at")),
            source_files=_string_list(cache.get("source_files")),
            document_hashes=cached_hashes,
            changed_files=changed_files,
            invalidation_reasons=reasons,
        )

    def refresh_knowledge_cache(
        self,
        documents: dict[str, str] | None = None,
        repository: dict[str, Any] | None = None,
        profile: dict[str, Any] | None = None,
        selected_files: list[str] | None = None,
        connector_mapping: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        previous = self._read_knowledge_cache()
        try:
            analyzed = self.analyze_repository_documents(documents, repository, profile, selected_files, connector_mapping)
            mapping = self.resolve_connector_mapping(connector_mapping or (repository or {}).get("connector_mapping"), analyzed)
            document_hashes = _document_hashes(documents or {})
            cache = {
                "schema_version": _knowledge_schema_version(),
                "project_id": _clean_text(analyzed.get("project_id")),
                "project_name": _clean_text(analyzed.get("project_name")),
                "profile": _normalize_profile(analyzed),
                "repository_mapping": mapping,
                "repository": mapping.get("repository_name") or analyzed["repository_connection"]["repository_name"],
                "branch": mapping.get("branch") or analyzed["repository_connection"]["branch"],
                "knowledge_version": _knowledge_version(analyzed, document_hashes),
                "last_analyzed_at": _now_iso(),
                "source_files": _string_list(analyzed.get("source_files")) or analyzed["knowledge_registry"]["source_files"],
                "document_hashes": document_hashes,
                "document_status": [
                    {"path": path, "hash": digest, "lastAnalyzedAt": _now_iso()}
                    for path, digest in sorted(document_hashes.items())
                ],
                "knowledge_registry": analyzed["knowledge_registry"],
                "architecture_summary": _clean_text(analyzed.get("architecture_summary")) or " ".join(analyzed["knowledge_registry"]["architecture_notes"][:3]),
                "modules": analyzed["knowledge_registry"]["modules"],
                "flows": analyzed["knowledge_registry"]["flows"],
                "components": analyzed["knowledge_registry"]["components"],
                "standards": analyzed["knowledge_registry"]["standards"],
                "generated_project_summary": _project_summary(analyzed),
            }
            self._knowledge_cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
            self.refresh_context_capsules(analyzed, capsule_types=["project"])
            self.save_session({
                "active_project": analyzed.get("project_name") or mapping.get("ado_project"),
                "project_id": analyzed.get("project_id"),
                "last_repository": mapping.get("repository_name"),
                "last_repository_id": mapping.get("repository_id"),
                "last_branch": mapping.get("branch"),
                "last_analysis_timestamp": cache["last_analyzed_at"],
                "knowledge_version": cache["knowledge_version"],
            })
            try:
                from backend.project_graph import project_knowledge_graph_service

                project_knowledge_graph_service.ingest({
                    "project": {
                        "id": analyzed.get("project_id"),
                        "title": analyzed.get("project_name") or mapping.get("ado_project"),
                        "description": analyzed.get("project_description"),
                    },
                    "modules": analyzed["knowledge_registry"]["modules"],
                    "flows": analyzed["knowledge_registry"]["flows"],
                    "components": analyzed["knowledge_registry"]["components"],
                    "repository_documents": [
                        {"title": path, "path": path}
                        for path in cache["source_files"]
                    ],
                })
            except Exception as error:  # pragma: no cover - graph updates should not break refresh
                logger.warning("project graph refresh ingest failed: %s", error)
            return {"success": True, "cache": cache, **self.knowledge_cache_status()}
        except Exception as error:  # pragma: no cover - defensive; tests exercise preservation behavior
            return {
                "success": False,
                "error": str(error),
                "message": "Refresh failed. Existing knowledge is still available.",
                "cache": previous or {},
                **self.knowledge_cache_status(),
            }

    def list_artifacts(
        self,
        artifact_type: str = "",
        source_item_id: str = "",
        state: str = "",
        fingerprint: str = "",
    ) -> dict[str, Any]:
        artifacts = self._read_artifacts()
        filtered = [
            artifact for artifact in artifacts
            if (not artifact_type or artifact["artifact_type"] == artifact_type)
            and (not source_item_id or artifact["source_item"].get("id") == str(source_item_id))
            and (not state or artifact["state"] == state)
            and (not fingerprint or artifact["fingerprint"] == fingerprint)
        ]
        filtered.sort(key=lambda item: (item.get("created_on", ""), item.get("version", 0)), reverse=True)
        return {"artifacts": filtered, "count": len(filtered)}

    def find_reusable_artifact(self, artifact_type: str, fingerprint: str, source_item_id: str = "") -> dict[str, Any]:
        candidates = self.list_artifacts(artifact_type, source_item_id, "", fingerprint)["artifacts"]
        reusable = [item for item in candidates if item.get("state") in {"approved", "locked"}]
        if reusable:
            return {"reusable": True, "artifact": reusable[0], "status": "reusable"}
        stale = self.list_artifacts(artifact_type, source_item_id)["artifacts"]
        return {
            "reusable": False,
            "artifact": stale[0] if stale else {},
            "status": "refresh_required" if stale else "missing",
        }

    def save_artifact(self, artifact: dict[str, Any]) -> dict[str, Any]:
        artifacts = self._read_artifacts()
        artifact_type = _clean_text(artifact.get("artifact_type") or artifact.get("type")) or "Artifact"
        source_item = artifact.get("source_item") if isinstance(artifact.get("source_item"), dict) else {}
        source_item_id = _clean_text(source_item.get("id"))
        fingerprint = _clean_text(artifact.get("fingerprint")) or _artifact_fingerprint(
            artifact_type,
            source_item,
            artifact.get("payload"),
        )
        existing_versions = [
            item.get("version", 0)
            for item in artifacts
            if item.get("artifact_type") == artifact_type
            and item.get("source_item", {}).get("id") == source_item_id
        ]
        now = _now_iso()
        record = {
            "artifact_id": _clean_text(artifact.get("artifact_id")) or f"artifact_{hashlib.sha256(f'{artifact_type}|{source_item_id}|{fingerprint}|{now}'.encode('utf-8')).hexdigest()[:12]}",
            "artifact_type": artifact_type,
            "state": _normalize_artifact_state(artifact.get("state") or "draft"),
            "title": _clean_text(artifact.get("title")) or artifact_type,
            "payload": artifact.get("payload") if isinstance(artifact.get("payload"), (dict, list, str)) else {},
            "fingerprint": fingerprint,
            "source_item": {
                "id": source_item_id,
                "type": _clean_text(source_item.get("type")),
                "title": _clean_text(source_item.get("title")),
            },
            "version": max([int(version or 0) for version in existing_versions] or [0]) + 1,
            "created_by": _clean_text(artifact.get("created_by")) or "AI Gen",
            "created_on": now,
            "approved_by": "",
            "approved_on": "",
            "locked_on": "",
            "archived_on": "",
            "history": [],
        }
        artifacts.append(record)
        self._write_artifacts(artifacts)
        try:
            from backend.project_graph import project_knowledge_graph_service

            project_knowledge_graph_service.ingest_artifact(record)
        except Exception as error:  # pragma: no cover - graph updates should not block artifact save
            logger.warning("project graph artifact ingest failed: %s", error)
        return record

    def approve_artifact(self, artifact_id: str, approved_by: str = "") -> dict[str, Any]:
        artifacts = self._read_artifacts()
        now = _now_iso()
        for artifact in artifacts:
            if artifact.get("artifact_id") == artifact_id:
                artifact.setdefault("history", []).append({"state": artifact.get("state"), "changed_on": now})
                artifact["state"] = "locked"
                artifact["approved_by"] = _clean_text(approved_by) or "AI Gen User"
                artifact["approved_on"] = now
                artifact["locked_on"] = now
                self._write_artifacts(artifacts)
                try:
                    from backend.project_graph import project_knowledge_graph_service

                    project_knowledge_graph_service.ingest_artifact(artifact)
                except Exception as error:  # pragma: no cover - graph updates should not block approval
                    logger.warning("project graph artifact approval ingest failed: %s", error)
                return artifact
        raise ValueError(f"Artifact {artifact_id} was not found.")

    def update_artifact_draft(self, artifact_id: str, changes: dict[str, Any], changed_by: str = "") -> dict[str, Any]:
        """Update a draft/review artifact while retaining its complete version history."""
        artifacts = self._read_artifacts()
        now = _now_iso()
        for artifact in artifacts:
            if artifact.get("artifact_id") != artifact_id:
                continue
            state = _normalize_artifact_state(artifact.get("state"))
            if state not in {"draft", "review"}:
                raise ValueError("Only Draft or Review planning artifacts can be edited.")
            expected_version = changes.get("expectedVersion")
            if expected_version is not None and int(expected_version) != int(artifact.get("version") or 1):
                raise ValueError("Planning artifact version changed. Reload the workspace before saving.")
            artifact.setdefault("history", []).append({
                "state": state,
                "title": artifact.get("title"),
                "payload": artifact.get("payload"),
                "version": int(artifact.get("version") or 1),
                "changed_by": _clean_text(changed_by) or "HEI User",
                "changed_on": now,
            })
            title = _clean_text(changes.get("title"))
            description = _clean_text(changes.get("description"))
            payload_changes = changes.get("details") if isinstance(changes.get("details"), dict) else {}
            payload = artifact.get("payload") if isinstance(artifact.get("payload"), dict) else {}
            artifact["title"] = title or artifact.get("title")
            description_change = {"description": description} if "description" in changes else {}
            artifact["payload"] = {**payload, **payload_changes, **description_change}
            requested_status = _clean_text(changes.get("status")).lower()
            if requested_status:
                if requested_status not in {"draft", "review"}:
                    raise ValueError("Draft updates may only use Draft or Review status.")
                artifact["state"] = requested_status
            artifact["version"] = int(artifact.get("version") or 1) + 1
            artifact["updated_on"] = now
            artifact["fingerprint"] = _artifact_fingerprint(
                _clean_text(artifact.get("artifact_type")) or "Artifact",
                artifact.get("source_item") if isinstance(artifact.get("source_item"), dict) else {},
                artifact.get("payload"),
            )
            self._write_artifacts(artifacts)
            return artifact
        raise ValueError(f"Artifact {artifact_id} was not found.")

    def transition_artifact(
        self,
        artifact_id: str,
        action: str,
        actor: str = "",
        comments: str = "",
        expected_version: int | None = None,
        target_version: int | None = None,
    ) -> dict[str, Any]:
        """Apply an audited planning lifecycle transition without rewriting prior versions."""
        normalized_action = _clean_text(action).lower().replace("-", "_").replace(" ", "_")
        transitions = {
            "approve": ({"draft", "review"}, "approved"),
            "reject": ({"draft", "review"}, "rejected"),
            "request_changes": ({"review", "approved", "rejected"}, "draft"),
            "publish": ({"approved"}, "published"),
        }
        if normalized_action not in {*transitions, "rollback"}:
            raise ValueError(f"Unsupported planning lifecycle action: {action}.")
        if normalized_action in {"reject", "request_changes"} and not _clean_text(comments):
            raise ValueError("Comments are required when rejecting planning or requesting changes.")

        artifacts = self._read_artifacts()
        now = _now_iso()
        changed_by = _clean_text(actor) or "HEI User"
        for artifact in artifacts:
            if artifact.get("artifact_id") != artifact_id:
                continue
            state = _normalize_artifact_state(artifact.get("state"))
            version = int(artifact.get("version") or 1)
            if expected_version is not None and int(expected_version) != version:
                raise ValueError("Planning artifact version changed. Reload the workspace before continuing.")
            previous = {
                "state": state,
                "title": artifact.get("title"),
                "payload": deepcopy(artifact.get("payload")),
                "version": version,
                "changed_by": changed_by,
                "changed_on": now,
                "action": normalized_action,
                "comments": _clean_text(comments),
            }
            history = artifact.setdefault("history", [])
            if normalized_action == "rollback":
                if target_version is None:
                    raise ValueError("targetVersion is required for rollback.")
                snapshot = next(
                    (entry for entry in history if int(entry.get("version") or 0) == int(target_version)
                     and "payload" in entry and "title" in entry),
                    None,
                )
                if not snapshot:
                    raise ValueError(f"Planning artifact version {target_version} is not available for rollback.")
                history.append(previous)
                artifact["title"] = snapshot.get("title") or artifact.get("title")
                artifact["payload"] = deepcopy(snapshot.get("payload"))
                artifact["state"] = "draft"
                artifact["rollback_from_version"] = version
                artifact["rollback_to_version"] = int(target_version)
            else:
                allowed, next_state = transitions[normalized_action]
                if state not in allowed:
                    raise ValueError(f"Planning artifact cannot {normalized_action.replace('_', ' ')} from {state.title()} state.")
                history.append(previous)
                artifact["state"] = next_state

            artifact["version"] = version + 1
            artifact["updated_on"] = now
            artifact["last_action"] = normalized_action
            artifact["last_comments"] = _clean_text(comments)
            artifact["last_changed_by"] = changed_by
            if normalized_action == "approve":
                artifact["approved_by"] = changed_by
                artifact["approved_on"] = now
            elif normalized_action == "publish":
                artifact["published_by"] = changed_by
                artifact["published_on"] = now
            elif normalized_action == "reject":
                artifact["rejected_by"] = changed_by
                artifact["rejected_on"] = now
            artifact["fingerprint"] = _artifact_fingerprint(
                _clean_text(artifact.get("artifact_type")) or "Artifact",
                artifact.get("source_item") if isinstance(artifact.get("source_item"), dict) else {},
                artifact.get("payload"),
            )
            self._write_artifacts(artifacts)
            try:
                from backend.project_graph import project_knowledge_graph_service

                project_knowledge_graph_service.ingest_artifact(artifact)
            except Exception as error:  # pragma: no cover - graph updates should not block transitions
                logger.warning("project graph artifact transition ingest failed: %s", error)
            return artifact
        raise LookupError(f"Artifact {artifact_id} was not found.")

    def regenerate_planning_artifact(self, artifact_id: str, changed_by: str = "") -> dict[str, Any]:
        """Regenerate one draft node through the established Intelligence Pipeline."""
        artifacts = self._read_artifacts()
        current = next((item for item in artifacts if item.get("artifact_id") == artifact_id), None)
        if not current:
            raise ValueError(f"Artifact {artifact_id} was not found.")
        state = _normalize_artifact_state(current.get("state"))
        if state not in {"draft", "review"}:
            raise ValueError("Only Draft or Review planning artifacts can be regenerated.")
        payload = current.get("payload") if isinstance(current.get("payload"), dict) else {}
        parent_id = _lineage_parent_id(payload)
        parent = next((item for item in artifacts if item.get("artifact_id") == parent_id), None)
        parent_payload = parent.get("payload") if isinstance((parent or {}).get("payload"), dict) else {}
        work_item = {
            "id": artifact_id,
            "type": _clean_text(current.get("artifact_type")) or "Artifact",
            "title": _clean_text(current.get("title")),
            "description": _clean_text(payload.get("description") or payload.get("businessGoal") or payload.get("summary")),
            "acceptanceCriteria": payload.get("acceptanceCriteria") or payload.get("acceptance_criteria") or [],
        }
        parent_work_item = {
            "id": _clean_text((parent or {}).get("artifact_id") or current.get("source_item", {}).get("id")),
            "type": _clean_text((parent or {}).get("artifact_type") or current.get("source_item", {}).get("type")),
            "title": _clean_text((parent or {}).get("title") or current.get("source_item", {}).get("title")),
            "description": _clean_text(parent_payload.get("description") or parent_payload.get("businessGoal") or parent_payload.get("summary")),
        }
        siblings = [
            {"id": item.get("artifact_id"), "title": item.get("title"), "description": _clean_text((item.get("payload") or {}).get("description"))}
            for item in artifacts
            if item.get("artifact_id") != artifact_id
            and _lineage_parent_id(item.get("payload") if isinstance(item.get("payload"), dict) else {}) == parent_id
        ]
        pipeline = _run_intelligence_pipeline(
            work_item, parent_work_item, self.get_profile(), work_item["type"], siblings,
            {"operation": f"planning_node_{work_item['type'].lower()}_regeneration", "allow_fallback": True},
        )
        generated = next((item for item in pipeline.get("artifacts", []) if isinstance(item, dict)), None)
        if not generated:
            raise ValueError("Planning Intelligence did not return a regenerated artifact.")
        regeneration_diagnostics = dict(pipeline.get("reasoning", {}).get("diagnostics") or {})
        provider_metadata = pipeline.get("providerMetadata") if isinstance(pipeline.get("providerMetadata"), dict) else {}
        if provider_metadata.get("phi_status") != "success":
            regeneration_diagnostics["providerUsed"] = "deterministic_fallback"
        regeneration_diagnostics["providerStatus"] = provider_metadata.get("phi_status") or "not_requested"
        regeneration_diagnostics["fallbackUsed"] = bool(provider_metadata.get("fallback_used") or provider_metadata.get("phi_status") != "success")
        return self.update_artifact_draft(artifact_id, {
            "expectedVersion": current.get("version") or 1,
            "title": generated.get("title") or current.get("title"),
            "description": generated.get("description") or payload.get("description") or "",
            "status": "Review",
            "details": {
                "businessValue": generated.get("businessValue") or payload.get("businessValue"),
                "acceptanceCriteria": generated.get("acceptanceCriteria") or payload.get("acceptanceCriteria") or [],
                "dependencies": generated.get("dependencies") or payload.get("dependencies") or [],
                "risks": generated.get("risks") or payload.get("risks") or [],
                "generatedUsing": generated.get("generatedUsing") or {},
                "confidence": generated.get("confidence") or payload.get("confidence"),
                "validationReport": generated.get("validationReport") or {},
                "validationStatus": generated.get("validationStatus") or "Pending",
                "regenerationDiagnostics": regeneration_diagnostics,
                "regeneratedAt": _now_iso(),
            },
        }, changed_by)

    def regenerate_story_tasks(self, story_artifact_id: str, changed_by: str = "") -> dict[str, Any]:
        """Replace draft task recommendations from one Story without touching approved Tasks."""
        artifacts = self._read_artifacts()
        story = next((item for item in artifacts if item.get("artifact_id") == story_artifact_id), None)
        if not story or "story" not in _clean_text(story.get("artifact_type")).lower():
            raise ValueError(f"Story artifact {story_artifact_id} was not found.")
        payload = story.get("payload") if isinstance(story.get("payload"), dict) else {}
        story_input = {
            "id": story_artifact_id, "type": "Story", "title": story.get("title"),
            "description": payload.get("description"),
            "acceptance_criteria": payload.get("acceptanceCriteria") or payload.get("acceptance_criteria") or [],
            "work_item_dna": payload.get("work_item_dna") or payload.get("dna"),
        }
        existing = [
            item for item in artifacts
            if "task" in _clean_text(item.get("artifact_type")).lower()
            and _lineage_parent_id(item.get("payload") if isinstance(item.get("payload"), dict) else {}) == story_artifact_id
            and _normalize_artifact_state(item.get("state")) != "archived"
        ]
        preserved_titles = {
            _clean_text(item.get("title")).casefold() for item in existing
            if _normalize_artifact_state(item.get("state")) in {"approved", "locked"}
            or _clean_text((item.get("payload") or {}).get("source")).casefold() == "manual"
        }
        refined = self.refine_story(story_input, self.get_profile(), options={
            "existing_children": [{"id": item.get("artifact_id"), "title": item.get("title")} for item in existing],
        })
        proposed = [item for item in refined.get("proposed_tasks", []) if isinstance(item, dict)]
        for item in existing:
            item_payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            if (
                _normalize_artifact_state(item.get("state")) in {"draft", "review"}
                and _clean_text(item_payload.get("source")).casefold() != "manual"
            ):
                self.archive_artifact(_clean_text(item.get("artifact_id")))
        created = []
        for task in proposed:
            title = _clean_text(task.get("title"))
            if not title or title.casefold() in preserved_titles:
                continue
            created.append(self.save_artifact({
                "artifact_type": "Task", "state": "draft", "title": title,
                "source_item": {"id": story_artifact_id, "type": "Story", "title": story.get("title")},
                "created_by": changed_by or "HEI User",
                "payload": {
                    "parentId": story_artifact_id, "description": task.get("description") or task.get("purpose") or "",
                    "acceptanceCriteria": task.get("acceptanceCriteria") or task.get("acceptance_criteria") or [],
                    "dependencies": task.get("dependencies") or [], "risks": task.get("risks") or [],
                    "work_area": task.get("work_area") or task.get("workArea") or "",
                    "category": _planning_task_category(task),
                    "estimate": task.get("estimate") or {"engineeringHours": 0, "engineeringDays": 0, "confidence": 0},
                    "owner": task.get("owner") or "Unassigned", "priority": task.get("priority") or "Medium",
                    "taskStatus": task.get("taskStatus") or "To Do", "source": "ai",
                    "confidence": task.get("confidence") or 0, "generatedUsing": task.get("generatedUsing") or {},
                    "work_item_dna": task.get("work_item_dna") or task.get("dna") or {},
                },
            }))
        return {
            "storyId": story_artifact_id, "generatedTasks": created, "generatedTaskCount": len(created),
            "preservedTaskCount": len(preserved_titles),
            "preservedApprovedTaskCount": sum(
                1 for item in existing if _normalize_artifact_state(item.get("state")) in {"approved", "locked"}
            ),
            "preservedManualTaskCount": sum(
                1 for item in existing if _clean_text((item.get("payload") or {}).get("source")).casefold() == "manual"
            ),
            "providerMetadata": refined.get("provider_metadata") or refined.get("providerMetadata") or {},
        }

    def generate_story_tests(self, story_artifact_id: str, changed_by: str = "") -> dict[str, Any]:
        """Generate and persist a QA Test Suite derived from one Story."""
        artifacts = self._read_artifacts()
        story = next((item for item in artifacts if item.get("artifact_id") == story_artifact_id), None)
        if not story or "story" not in _clean_text(story.get("artifact_type")).lower():
            raise ValueError(f"Story artifact {story_artifact_id} was not found.")
        payload = story.get("payload") if isinstance(story.get("payload"), dict) else {}
        story_input = {
            "id": story_artifact_id, "type": "Story", "title": story.get("title"),
            "description": payload.get("description"),
            "acceptance_criteria": payload.get("acceptanceCriteria") or payload.get("acceptance_criteria") or [],
            "modules": payload.get("repositoryModules") or payload.get("affected_modules") or payload.get("selectedModules") or [],
            "flows": payload.get("affected_flows") or payload.get("selectedFlows") or [],
            "dependencies": payload.get("dependencies") or [],
        }
        suite = self.generate_qa_test_cases(
            story_input,
            self.get_profile(),
            options={"force_provider": "deterministic_fallback"},
        )
        if suite.get("error"):
            raise ValueError(_clean_text(suite.get("message") or suite.get("error")) or "QA Intelligence could not generate tests.")
        artifact = self.save_artifact({
            "artifact_type": "Test Suite", "state": "draft", "title": f"{_clean_text(story.get('title'))} Tests",
            "source_item": {"id": story_artifact_id, "type": "Story", "title": story.get("title")},
            "created_by": changed_by or "HEI User", "payload": {**suite, "parentId": story_artifact_id},
        })
        return {
            "storyId": story_artifact_id, "testSuiteArtifact": artifact,
            "generatedTestCount": int(suite.get("generated_test_count") or len((suite.get("test_suite") or {}).get("test_cases") or [])),
            "providerMetadata": suite.get("provider_metadata") or suite.get("providerMetadata") or {},
        }

    def archive_artifact(self, artifact_id: str) -> dict[str, Any]:
        artifacts = self._read_artifacts()
        now = _now_iso()
        for artifact in artifacts:
            if artifact.get("artifact_id") == artifact_id:
                artifact.setdefault("history", []).append({"state": artifact.get("state"), "changed_on": now})
                artifact["state"] = "archived"
                artifact["archived_on"] = now
                self._write_artifacts(artifacts)
                return artifact
        raise ValueError(f"Artifact {artifact_id} was not found.")

    def get_connector_mapping(self, project_id: str = "") -> dict[str, Any]:
        return self._load_profile_for_project(project_id)["connectors"]["azure_devops"]

    def save_connector_mapping(self, mapping: dict[str, Any], project_id: str = "") -> dict[str, Any]:
        profile = self._load_profile_for_project(project_id)
        if project_id and not profile.get("project_id"):
            profile["project_id"] = project_id
        normalized_mapping = _normalize_azure_devops_connector(mapping, profile["repository_connection"])
        profile["connectors"]["azure_devops"] = normalized_mapping
        profile["repository_connection"] = _repository_connection_from_connector(normalized_mapping, profile["repository_connection"])
        self.save_profile(profile)
        return normalized_mapping

    def resolve_connector_mapping(
        self,
        explicit_mapping: dict[str, Any] | None = None,
        profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        active_profile = _normalize_profile(profile or self.get_profile())
        if explicit_mapping:
            return _normalize_azure_devops_connector(explicit_mapping, active_profile["repository_connection"])
        saved = active_profile["connectors"]["azure_devops"]
        if saved.get("ado_project") or saved.get("repository_id") or saved.get("repository_name"):
            return saved
        return _legacy_azure_devops_connector(active_profile["repository_connection"])

    def _load_profile_for_project(self, project_id: str = "") -> dict[str, Any]:
        if project_id:
            profile_path = self._profiles_dir / f"{_safe_profile_id(project_id)}.json"
            if profile_path.exists():
                try:
                    return _normalize_profile(json.loads(profile_path.read_text(encoding="utf-8")))
                except (OSError, json.JSONDecodeError):
                    pass
        return self.get_profile()

    def _read_knowledge_cache(self) -> dict[str, Any]:
        if not self._knowledge_cache_path.exists():
            return {}
        try:
            cache = json.loads(self._knowledge_cache_path.read_text(encoding="utf-8"))
            return cache if isinstance(cache, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _read_artifacts(self) -> list[dict[str, Any]]:
        if not self._artifacts_path.exists():
            return []
        try:
            payload = json.loads(self._artifacts_path.read_text(encoding="utf-8"))
            records = payload.get("artifacts") if isinstance(payload, dict) else payload
            if not isinstance(records, list):
                return []
            return [_normalize_artifact_record(item) for item in records if isinstance(item, dict)]
        except (OSError, json.JSONDecodeError):
            return []

    def _read_context_capsules(self) -> dict[str, Any]:
        if not self._capsules_path.exists():
            return {}
        try:
            payload = json.loads(self._capsules_path.read_text(encoding="utf-8"))
            capsules = payload.get("capsules") if isinstance(payload, dict) else payload
            return capsules if isinstance(capsules, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_context_capsules(self, capsules: dict[str, Any]) -> None:
        self._capsules_path.write_text(
            json.dumps({"schema_version": "context-capsule-v1", "capsules": capsules}, indent=2),
            encoding="utf-8",
        )

    def _profile_with_capsule(
        self,
        capsule_type: str,
        profile: dict[str, Any],
        item: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        capsule_type = capsule_type if capsule_type in _context_capsule_types() else "project"
        item = item or {}
        cache = self._read_knowledge_cache()
        capsules = self._read_context_capsules()
        current = capsules.get(capsule_type) if isinstance(capsules.get(capsule_type), dict) else {}
        expected_hash = _capsule_source_hash(capsule_type, profile, item, cache)
        if current.get("source_hash") != expected_hash:
            current = _build_context_capsule(capsule_type, profile, item, cache, current)
            capsules[capsule_type] = current
            self._write_context_capsules(capsules)
        return {**profile, "_active_context_capsule": current}

    def _write_artifacts(self, artifacts: list[dict[str, Any]]) -> None:
        self._artifacts_path.write_text(
            json.dumps({"schema_version": "artifact-lifecycle-v1", "artifacts": artifacts}, indent=2),
            encoding="utf-8",
        )

    def analyze_description(self, description: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        base = self.get_profile()
        text = _clean_text(description)
        profile = {
            **base,
            "project_description": text or base["project_description"],
            "applications": _infer_applications(text) or base["applications"],
            "technology_stack": _infer_stack(text) or base["technology_stack"],
            "domain": base["domain"] or _infer_domain(text),
            "project_type": base["project_type"] or _infer_project_type(text),
            "knowledge_profile_preview": {
                "domain": base["domain"] or _infer_domain(text),
                "systems": [app["name"] for app in (_infer_applications(text) or base["applications"])],
                "standards": _infer_standards(text),
                "repository_status": "Repository README scan coming next.",
                "readiness": _readiness(
                    {
                        **base,
                        "project_description": text or base["project_description"],
                        "applications": _infer_applications(text) or base["applications"],
                        "technology_stack": _infer_stack(text) or base["technology_stack"],
                    }
                ),
            },
        }
        deterministic = _normalize_profile(profile)
        phi = _project_phi_json(
            "analyze_description",
            deterministic,
            {"description": text},
            deterministic,
            options,
            ["project_name", "domain", "project_type", "project_description", "applications", "technology_stack", "development_standards", "ui_guidelines"],
        )
        if phi["used"]:
            return _with_provider_metadata(
                _normalize_profile(_merge_known_fields(deterministic, phi["parsed"], deterministic.keys())),
                phi["metadata"],
            )
        if phi["blocked"]:
            return _phi_error_response(phi)
        return _with_provider_metadata(deterministic, phi["metadata"])

    def generate_story_prompts(
        self,
        story: dict[str, Any] | None = None,
        profile: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        active_profile = _normalize_profile(profile or self.get_profile())
        story = story or {}
        title = _clean_text(story.get("title")) or "Approved story"
        description = _clean_text(story.get("description")) or "Implement the approved behavior."
        acceptance = _string_list(story.get("acceptance_criteria"))
        impact = self.analyze_story_impact(story, active_profile)
        context_lines = _profile_context_lines(active_profile)
        acceptance_lines = acceptance or ["Confirm the implementation satisfies the approved story scope."]
        deterministic = {
            "ui_prompt": _prompt(
                "UI Prompt",
                title,
                description,
                context_lines,
                [
                    "Design the screen, states, validations, and accessibility behavior.",
                    "Apply the configured UI guidelines and component library where available.",
                    f"Affected Applications: {', '.join(impact['affected_applications']) or 'Confirm affected UI surface.'}",
                    f"Affected Flows: {', '.join(impact['affected_flows']) or 'Confirm affected user flows.'}",
                    *[f"Acceptance: {item}" for item in acceptance_lines],
                ],
            ),
            "dev_prompt": _prompt(
                "Dev Prompt",
                title,
                description,
                context_lines,
                [
                    "Implement the approved story using the project technology stack.",
                    "Respect existing architecture boundaries and security expectations.",
                    f"Affected Modules: {', '.join(impact['affected_modules']) or 'Confirm affected modules.'}",
                    f"Dependencies: {', '.join(impact['dependencies']) or 'Confirm dependencies.'}",
                    *[f"Acceptance: {item}" for item in acceptance_lines],
                ],
            ),
            "qa_prompt": _prompt(
                "QA Prompt",
                title,
                description,
                context_lines,
                [
                    "Create manual and automation-ready test coverage for the approved story.",
                    "Include happy path, negative, edge, accessibility, and regression checks.",
                    f"Risks: {', '.join(impact['risks']) or 'Confirm delivery risks.'}",
                    f"Integration Points: {', '.join(impact['integration_points']) or 'Confirm integration points.'}",
                    f"Test Areas: {', '.join(impact['affected_flows'] + impact['affected_modules']) or 'Confirm test areas.'}",
                    *[f"Acceptance: {item}" for item in acceptance_lines],
                ],
            ),
        }
        phi = _project_phi_json(
            "generate_story_prompts",
            active_profile,
            story,
            deterministic,
            options,
            ["ui_prompt", "dev_prompt", "qa_prompt"],
        )
        if phi["used"]:
            return _with_provider_metadata({**deterministic, **_pick_string_fields(phi["parsed"], ["ui_prompt", "dev_prompt", "qa_prompt"])}, phi["metadata"])
        if phi["blocked"]:
            return _phi_error_response(phi)
        return _with_provider_metadata(deterministic, phi["metadata"])

    def analyze_readme(
        self,
        readme_content: str,
        repository: dict[str, Any] | None = None,
        profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        active_profile = _normalize_profile(profile or self.get_profile())
        repository = repository or {}
        analysis = _analyze_readme_content(readme_content)
        registry = _merge_knowledge_registry(active_profile["knowledge_registry"], analysis)
        repository_connection = {
            **active_profile["repository_connection"],
            "repository_id": _clean_text(repository.get("id")) or active_profile["repository_connection"]["repository_id"],
            "repository_name": _clean_text(repository.get("name")) or active_profile["repository_connection"]["repository_name"],
            "branch": _clean_text(repository.get("branch")) or active_profile["repository_connection"]["branch"],
            "readme_path": _clean_text(repository.get("readme_path")) or active_profile["repository_connection"]["readme_path"] or "/README.md",
            "status": "README analyzed",
        }
        next_profile = {
            **active_profile,
            "repository_connection": repository_connection,
            "readme_analysis": analysis,
            "knowledge_registry": registry,
            "applications": _merge_applications(active_profile["applications"], registry["applications"]),
            "knowledge_profile_preview": {
                **active_profile["knowledge_profile_preview"],
                "systems": [app["name"] for app in _merge_applications(active_profile["applications"], registry["applications"])],
                "repository_status": "README analyzed",
                "readiness": _readiness({**active_profile, "knowledge_registry": registry}),
            },
        }
        saved = self.save_profile(next_profile)
        saved["onboarding_completed"] = active_profile.get("onboarding_completed", False)
        self._profile_path.write_text(json.dumps(saved, indent=2), encoding="utf-8")
        return saved

    def repository_files(self) -> dict[str, Any]:
        return {"known_files": KNOWN_REPOSITORY_DOCUMENTS}

    def analyze_repository_documents(
        self,
        documents: dict[str, str] | None = None,
        repository: dict[str, Any] | None = None,
        profile: dict[str, Any] | None = None,
        selected_files: list[str] | None = None,
        connector_mapping: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        active_profile = _normalize_profile(profile or self.get_profile())
        repository = repository or {}
        resolved_mapping = self.resolve_connector_mapping(connector_mapping or repository.get("connector_mapping"), active_profile)
        documents = {
            _clean_path(path): content
            for path, content in (documents or {}).items()
            if _clean_path(path) and _clean_text(content)
        }
        if selected_files:
            documents = {path: content for path, content in documents.items() if path in set(selected_files)}
        analysis = _analyze_repository_documents(documents)
        registry = _merge_knowledge_registry(active_profile["knowledge_registry"], analysis)
        repository_connection = {
            **active_profile["repository_connection"],
            "repository_id": _clean_text(repository.get("repository_id")) or _clean_text(repository.get("id")) or resolved_mapping["repository_id"] or active_profile["repository_connection"]["repository_id"],
            "repository_name": _clean_text(repository.get("repository_name")) or _clean_text(repository.get("name")) or resolved_mapping["repository_name"] or active_profile["repository_connection"]["repository_name"],
            "branch": _clean_text(repository.get("branch")) or resolved_mapping["branch"] or active_profile["repository_connection"]["branch"],
            "status": "Repository documents analyzed" if documents else active_profile["repository_connection"]["status"],
            "readme_path": active_profile["repository_connection"]["readme_path"] or "/README.md",
        }
        azure_devops_connector = _normalize_azure_devops_connector(
            {
                **resolved_mapping,
                "repository_id": repository_connection["repository_id"],
                "repository_name": repository_connection["repository_name"],
                "branch": repository_connection["branch"],
            },
            repository_connection,
        )
        next_profile = {
            **active_profile,
            "repository_connection": repository_connection,
            "connectors": {**active_profile["connectors"], "azure_devops": azure_devops_connector},
            "project_description": active_profile["project_description"] or analysis["readme_summary"],
            "readme_analysis": {
                **active_profile["readme_analysis"],
                "summary": analysis["readme_summary"] or active_profile["readme_analysis"]["summary"],
                "applications": _merge_applications(active_profile["readme_analysis"]["applications"], analysis["detected_applications"]),
                "modules": _unique([*active_profile["readme_analysis"]["modules"], *analysis["detected_modules"]]),
                "flows": _unique([*active_profile["readme_analysis"]["flows"], *analysis["detected_flows"]]),
                "architecture_notes": _unique([*active_profile["readme_analysis"]["architecture_notes"], *analysis["architecture_notes"]]),
            },
            "knowledge_registry": registry,
            "applications": _merge_applications(active_profile["applications"], analysis["detected_applications"]),
            "domain": active_profile["domain"] or _infer_domain(" ".join([*documents.values(), analysis["readme_summary"], analysis["architecture_summary"]])),
            "project_type": active_profile["project_type"] or _infer_project_type(" ".join(documents.values())),
            "technology_stack": _merge_stack(active_profile["technology_stack"], analysis["technology_stack"]),
            "development_standards": _merge_development_standards(active_profile["development_standards"], analysis["development_standards"]),
            "ui_guidelines": {
                **active_profile["ui_guidelines"],
                "accessibility_rules": _unique([*active_profile["ui_guidelines"]["accessibility_rules"], *analysis["ui_standards"]]),
            },
            "repository_sources": _unique([*active_profile["repository_sources"], *analysis["source_files"]]),
            "knowledge_profile_preview": {
                **active_profile["knowledge_profile_preview"],
                "systems": [app["name"] for app in _merge_applications(active_profile["applications"], analysis["detected_applications"])],
                "domain": active_profile["domain"] or _infer_domain(" ".join(documents.values())),
                "standards": _unique([*active_profile["knowledge_profile_preview"]["standards"], *analysis["ui_standards"], *analysis["development_standards"]]),
                "repository_status": "Repository documents analyzed" if documents else "Repository documents not found",
                "readiness": _readiness({
                    **active_profile,
                    "project_description": active_profile["project_description"] or analysis["readme_summary"],
                    "knowledge_registry": registry,
                    "applications": _merge_applications(active_profile["applications"], analysis["detected_applications"]),
                    "technology_stack": _merge_stack(active_profile["technology_stack"], analysis["technology_stack"]),
                    "repository_sources": _unique([*active_profile["repository_sources"], *analysis["source_files"]]),
                    "development_standards": _merge_development_standards(active_profile["development_standards"], analysis["development_standards"]),
                }),
            },
        }
        saved = self.save_profile(next_profile)
        saved["onboarding_completed"] = active_profile.get("onboarding_completed", False)
        saved["repository_status"] = "analyzed" if documents else "not_analyzed"
        saved["readme_summary"] = analysis["readme_summary"]
        saved["architecture_summary"] = analysis["architecture_summary"]
        saved["detected_applications"] = analysis["detected_applications"]
        saved["detected_modules"] = analysis["detected_modules"]
        saved["detected_flows"] = analysis["detected_flows"]
        saved["detected_components"] = analysis["detected_components"]
        saved["ui_standards"] = analysis["ui_standards"]
        saved["development_standards_detected"] = analysis["development_standards"]
        saved["source_files"] = analysis["source_files"]
        saved["warnings"] = analysis["warnings"]
        self._profile_path.write_text(json.dumps(saved, indent=2), encoding="utf-8")
        return saved

    def refine_epic(
        self,
        epic: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        active_profile = _normalize_profile(profile or self.get_profile())
        active_profile = _merge_external_knowledge(active_profile, knowledge_profile or {})
        title = _clean_text(epic.get("title")) or "Untitled epic"
        description = _clean_text(epic.get("description"))
        selection = _select_knowledge_context(active_profile, epic, "Epic")
        relevant_profile = _profile_with_relevance(active_profile, selection)
        keywords = _string_list(selection.get("intent", {}).get("keywords")) or _context_keywords(title, description, active_profile)
        epic_analysis = analyzeEpic(epic, relevant_profile, {"intent_keywords": keywords})
        epic_analysis_for_features = dict(epic_analysis)
        capability_context = buildCapabilityContext(
            build_intent(epic),
            {
                "project_profile": relevant_profile,
                "repository_snapshot": _repository_snapshot_from_profile(relevant_profile),
                "knowledge_registry": relevant_profile.get("knowledge_registry") if isinstance(relevant_profile.get("knowledge_registry"), dict) else {},
                "project_id": _clean_text(active_profile.get("project_id") or active_profile.get("projectId") or active_profile.get("project_name") or active_profile.get("projectName") or active_profile.get("name")),
                "work_item_type": "Epic",
            },
        )
        epic_analysis = _apply_capability_discovery_to_epic_analysis(epic_analysis, capability_context)
        capability_review = buildCapabilityReview(epic, epic_analysis, relevant_profile)
        business_goal = _primary_epic_goal(epic_analysis, title, description, active_profile)
        capability_plan = _capability_decomposition_from_epic_analysis(title, business_goal, keywords, relevant_profile, epic_analysis_for_features, options)
        features = [
            {
                **feature,
                **_lineage_metadata(epic, "Epic", "epic_intent + knowledge_registry", selection, float(feature.get("confidence") or 0.84)),
                "analysis_source": "epic_analysis + capability_intelligence + knowledge_registry",
            }
            for feature in capability_plan["recommended_features"]
        ]
        memory_context = self._memory_context(
            "planning",
            relevant_profile,
            "Feature",
            epic,
            modules=_selection_names(selection, "relevant_modules"),
            flows=_selection_names(selection, "relevant_flows"),
            capability=business_goal,
        )
        deterministic = {
            "business_goal": business_goal,
            "business_outcomes": _string_list(epic_analysis.get("desiredOutcomes")) or _business_outcomes(keywords, relevant_profile),
            "users": _users_for_profile(relevant_profile),
            "user_problems": _string_list(epic_analysis.get("businessProblems")) or capability_plan["user_problems"],
            "capability_categories": capability_plan["capability_categories"],
            "applications": _application_names(relevant_profile),
            "constraints": _constraints_for_profile(relevant_profile),
            "risks": _unique([*_risks_for_profile(relevant_profile, keywords), *_string_list(memory_context.get("knownRisks"))]),
            "dependencies": _selection_names(selection, "relevant_dependencies") or _dependencies_for_profile(relevant_profile),
            "memory_context": memory_context,
            "memory_diagnostics": memory_context.get("diagnostics", {}),
            "reusable_capabilities": [
                memory for memory in memory_context.get("relevantMemories", [])
                if memory.get("artifactType") in {"Feature", "Capability"}
            ],
            "known_memory_risks": memory_context.get("knownRisks", []),
            "epic_analysis": epic_analysis,
            "epic_analysis_feature_generation_source": epic_analysis_for_features,
            "epic_analysis_diagnostics": epic_analysis.get("diagnostics", {}),
            "capability_review": capability_review["capabilities"],
            "capability_review_diagnostics": capability_review["diagnostics"],
            "capability_dependency_graph": capability_review["dependencyGraph"],
            "capability_context": capability_context,
            "planning_boundary": epic_analysis.get("planningBoundary") or epic_analysis.get("planning_boundary"),
            "recommended_features": features,
            "capability_diagnostics": capability_plan["diagnostics"],
            "generation_review": _generation_review(relevant_profile, features, _selection_names(selection, "relevant_modules"), keywords),
            **_relevance_metadata(selection),
        }
        epic_dna_analysis = {
            **epic_analysis,
            "planningBoundary": {
                "inScope": _unique([
                    *_string_list((epic_analysis.get("planningBoundary") or {}).get("inScope") if isinstance(epic_analysis.get("planningBoundary"), dict) else []),
                    *[
                        scope
                        for review in capability_review["capabilities"]
                        if isinstance(review, dict)
                        for scope in _string_list(review.get("inScope"))
                    ],
                ]),
                "outOfScope": _unique([
                    *_string_list((epic_analysis.get("planningBoundary") or {}).get("outOfScope") if isinstance(epic_analysis.get("planningBoundary"), dict) else []),
                    *[
                        scope
                        for review in capability_review["capabilities"]
                        if isinstance(review, dict)
                        for scope in _string_list(review.get("outOfScope"))
                    ],
                ]),
            },
        }
        deterministic["work_item_dna"] = generateDNA(
            epic,
            "Epic",
            profile=relevant_profile,
            epic_analysis=epic_dna_analysis,
            validation_report={"score": int((epic_analysis.get("confidence") or 0.72) * 100), "issues": capability_review["diagnostics"].get("validationIssues", [])},
        )
        deterministic["dna_validation"] = validateDNA(None, deterministic["work_item_dna"])
        deterministic["dna_diagnostics"] = _dna_diagnostics(None, deterministic["work_item_dna"])
        phi = _project_phi_json("refine_epic", relevant_profile, epic, deterministic, options, list(deterministic.keys()))
        if phi.get("blocked"):
            return _phi_error_response(phi)
        provider_parsed = phi.get("parsed") if isinstance(phi.get("parsed"), dict) else {}
        if _clean_text(provider_parsed.get("business_goal")):
            deterministic["business_goal"] = _clean_text(provider_parsed.get("business_goal"))
        _append_rejected_phi_feature_diagnostics(deterministic, provider_parsed, title)
        pipeline = _run_epic_feature_pipeline(
            epic,
            features,
            relevant_profile,
            _existing_children_from_options(options),
            {
                **(options or {}),
                "epic_analysis": epic_analysis,
                "provider_metadata": phi.get("metadata", {}),
                "provider_parsed": provider_parsed,
            },
        )
        deterministic["recommended_features"] = _attach_validation_to_items(features, pipeline, "Feature")
        deterministic["recommended_features"] = [
            _with_child_dna(
                feature,
                "Feature",
                deterministic["work_item_dna"],
                relevant_profile,
                capability_review=_capability_review_for_feature(feature, capability_review["capabilities"]),
                validation_report=feature.get("validationReport"),
            )
            for feature in deterministic["recommended_features"]
        ]
        deterministic["generation_review"] = _generation_review(relevant_profile, deterministic["recommended_features"], _selection_names(selection, "relevant_modules"), keywords)
        deterministic.update(_pipeline_payload(pipeline))
        provider_metadata = _intelligence_pipeline_metadata(pipeline)
        deterministic["intelligence_trace"] = self._trace_decision(
            profile=relevant_profile,
            artifact_type="Epic",
            artifact=epic,
            stage="Planning",
            source="Planning Intelligence",
            decision="Generate Feature Recommendations",
            reason="Epic intent, capability review, Knowledge Registry, Engineering Memory, and validation pipeline produced feature recommendations.",
            confidence=float((deterministic.get("work_item_dna") or {}).get("confidence") or 0.84),
            evidence=[
                {"type": "capability_review", "count": len(deterministic.get("capability_review", []))},
                {"type": "modules", "items": _selection_names(selection, "relevant_modules")},
                {"type": "flows", "items": _selection_names(selection, "relevant_flows")},
            ],
            memory_context=memory_context,
            repository_evidence=_selection_names(selection, "relevant_modules") + _selection_names(selection, "relevant_flows"),
            validation_result={"previewPolicy": pipeline.get("previewPolicy"), "reports": pipeline.get("validationReports", [])},
            metadata=provider_metadata,
        )
        return _with_provider_metadata(deterministic, provider_metadata)

    def refine_feature(
        self,
        feature: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        active_profile = _merge_external_knowledge(_normalize_profile(profile or self.get_profile()), knowledge_profile or {})
        parent_dna = _option_parent_dna(options)
        current_dna = feature.get("work_item_dna") if isinstance(feature.get("work_item_dna"), dict) else None
        dna_seed = current_dna or parent_dna or generateDNA(feature, "Feature", profile=active_profile)
        feature_for_generation = _work_item_from_dna(feature, dna_seed)
        title = _clean_text(feature_for_generation.get("title")) or "Untitled feature"
        description = _clean_text(feature_for_generation.get("description"))
        selection = _select_knowledge_context(active_profile, feature_for_generation, "Feature")
        relevant_profile = _profile_with_relevance(active_profile, selection)
        modules = _selection_names(selection, "relevant_modules")
        flows = _selection_names(selection, "relevant_flows")
        story_analysis = analyzeFeatureStories(feature_for_generation, dna_seed, relevant_profile)
        reviewed_journeys = _review_story_journeys(story_analysis.get("userJourneys", []), options)
        story_engine = StoryAnalysisEngine()
        recommended_stories: list[dict[str, Any]] = []
        for journey in reviewed_journeys:
            if str(journey.get("status") or "").lower() not in {"approved", "draft"}:
                continue
            existing_responsibilities = [
                existing.get("business_responsibility") or existing.get("businessResponsibility") or existing.get("title") or ""
                for existing in recommended_stories
            ]
            story_item = story_engine.generate_story_for_journey(journey, dna_seed, existing_responsibilities=existing_responsibilities)
            recommended_stories.append(
                {
                    **story_item,
                    **_lineage_metadata(feature, "Feature", "feature_dna + story_analysis_journey", selection, float(journey.get("confidence") or 0.82)),
                }
            )
        story_plan = _story_plan_from_analysis(story_analysis, recommended_stories)
        memory_context = self._memory_context(
            "planning",
            relevant_profile,
            "Story",
            feature_for_generation,
            modules=modules,
            flows=flows,
            capability=title,
        )
        deterministic = {
            "feature_summary": _sentence(title, description or f"Deliver {title} using project-aware modules and flows."),
            "affected_modules": modules,
            "affected_flows": flows,
            "dependencies": _selection_names(selection, "relevant_dependencies") or _dependencies_for_profile(relevant_profile),
            "risks": _unique([
                *_risks_for_profile(relevant_profile, _string_list(selection.get("intent", {}).get("keywords")) or _context_keywords(title, description, relevant_profile)),
                *_string_list(memory_context.get("knownRisks")),
            ]),
            "memory_context": memory_context,
            "memory_diagnostics": memory_context.get("diagnostics", {}),
            "story_patterns": [
                memory for memory in memory_context.get("relevantMemories", [])
                if memory.get("artifactType") == "Story"
            ],
            "acceptance_criteria_memory_hints": memory_context.get("reusableAcceptanceCriteria", []),
            "story_analysis": story_analysis,
            "story_review": {
                "journeys": reviewed_journeys,
                "actions": ["approve", "reject", "edit", "generate_story", "move_up", "move_down"],
                "generation_rule": "one_story_per_approved_journey",
            },
            "recommended_stories": recommended_stories,
            "story_generation_diagnostics": story_plan["diagnostics"],
            "generation_review": _generation_review(relevant_profile, story_plan["recommended_stories"], modules, _context_keywords(title, description, relevant_profile)),
            **_relevance_metadata(selection),
        }
        deterministic["work_item_dna"] = current_dna or generateDNA(
            _with_selected_evidence(feature_for_generation, modules, flows, deterministic["dependencies"], deterministic["risks"]),
            "Feature",
            profile=relevant_profile,
            parent_dna=parent_dna,
            validation_report={"score": _basic_validation_score(modules, flows), "issues": []},
        )
        dna_validation = validateDNA(parent_dna, deterministic["work_item_dna"])
        deterministic["dna_validation"] = dna_validation
        deterministic["dna_diagnostics"] = _dna_diagnostics(parent_dna, deterministic["work_item_dna"])
        if not dna_validation["valid"]:
            return _dna_error_response(deterministic, dna_validation)
        feature_analysis_options = _feature_analysis_options(options)
        deterministic_pipeline_options = {**feature_analysis_options, "deterministic_only": True}
        pipeline = _run_feature_analysis_pipeline(
            feature_for_generation,
            relevant_profile,
            _existing_children_from_options(options),
            deterministic_pipeline_options,
        )
        deterministic["recommended_stories"] = _attach_validation_to_items(recommended_stories, pipeline, "User Story")
        deterministic["recommended_stories"] = [
            _with_child_dna(story_item, "Story", deterministic["work_item_dna"], relevant_profile, validation_report=story_item.get("validationReport"))
            for story_item in deterministic["recommended_stories"]
        ]
        deterministic["generation_review"] = _generation_review(relevant_profile, deterministic["recommended_stories"], modules, _context_keywords(title, description, relevant_profile))
        deterministic.update(_pipeline_payload(pipeline))
        provider_metadata = _feature_analysis_provider_metadata(
            _run_feature_analysis_ai_enrichment(feature_for_generation, deterministic, relevant_profile, feature_analysis_options)
            if _feature_analysis_ai_requested(feature_analysis_options)
            else _intelligence_pipeline_metadata(pipeline)
        )
        deterministic.update(
            _feature_analysis_payload(
                feature_for_generation,
                deterministic,
                provider_metadata,
                modules,
                flows,
                selection,
                dna_validation,
                ai_requested=_feature_analysis_ai_requested(feature_analysis_options),
            )
        )
        deterministic["intelligence_trace"] = self._trace_decision(
            profile=relevant_profile,
            artifact_type="Feature",
            artifact=feature_for_generation,
            stage="Planning",
            source="Planning Intelligence",
            decision="Generate Story Recommendations",
            reason="Feature DNA, approved journey analysis, selected modules/flows, Engineering Memory, and validation reports produced story recommendations.",
            confidence=float((deterministic.get("work_item_dna") or {}).get("confidence") or 0.82),
            evidence=[
                {"type": "story_journeys", "count": len(reviewed_journeys)},
                {"type": "modules", "items": modules},
                {"type": "flows", "items": flows},
            ],
            memory_context=memory_context,
            repository_evidence=modules + flows,
            validation_result={"reports": pipeline.get("validationReports", []), "dna": dna_validation},
            metadata=provider_metadata,
        )
        return _with_provider_metadata(deterministic, provider_metadata)

    def refine_story(
        self,
        story: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        active_profile = _merge_external_knowledge(_normalize_profile(profile or self.get_profile()), knowledge_profile or {})
        parent_dna = _option_parent_dna(options)
        current_dna = story.get("work_item_dna") if isinstance(story.get("work_item_dna"), dict) else None
        dna_seed = current_dna or parent_dna or generateDNA(story, "Story", profile=active_profile)
        story_for_generation = _work_item_from_dna(story, dna_seed)
        title = _clean_text(story_for_generation.get("title")) or "Untitled story"
        description = _clean_text(story_for_generation.get("description"))
        selection = _select_knowledge_context(active_profile, story_for_generation, "Story")
        relevant_profile = _profile_with_relevance(active_profile, selection)
        modules = _selection_names(selection, "relevant_modules")
        flows = _selection_names(selection, "relevant_flows")
        applications = _application_names(relevant_profile)
        impact = _normalize_story_impact(self.analyze_story_impact(story_for_generation, relevant_profile, relevant_profile["knowledge_registry"]))
        acceptance = _acceptance_criteria(title, flows, modules)
        acceptance_categories = _acceptance_criteria_categories(acceptance)
        acceptance_quality_score = _acceptance_criteria_quality_score(acceptance)
        memory_context = self._memory_context(
            "planning",
            relevant_profile,
            "Task",
            story_for_generation,
            modules=modules,
            flows=flows,
            acceptance_criteria=acceptance,
            capability=title,
        )
        task_plan = _task_intelligence(title, description, acceptance, impact, relevant_profile)
        proposed_tasks = [
            {
                **task,
                **_lineage_metadata(story, "Story", "story_acceptance_criteria + knowledge_registry", selection, float(task.get("confidence") or 0.8)),
            }
            for task in task_plan["tasks"]
        ]
        deterministic = {
            "story_summary": _sentence(title, description or f"Implement {title} within the approved project context."),
            "acceptance_criteria": acceptance,
            "acceptance_criteria_categories": acceptance_categories,
            "acceptance_criteria_quality_score": acceptance_quality_score,
            "affected_applications": applications,
            "affected_modules": modules,
            "affected_flows": flows,
            "dependencies": _selection_names(selection, "relevant_dependencies") or _dependencies_for_profile(relevant_profile),
            "risks": _unique([
                *_risks_for_profile(relevant_profile, _string_list(selection.get("intent", {}).get("keywords")) or _context_keywords(title, description, relevant_profile)),
                *_string_list(memory_context.get("knownRisks")),
            ]),
            "memory_context": memory_context,
            "memory_diagnostics": memory_context.get("diagnostics", {}),
            "task_patterns": [
                memory for memory in memory_context.get("relevantMemories", [])
                if memory.get("artifactType") in {"Task", "Execution Package"}
            ],
            "reusable_acceptance_criteria": memory_context.get("reusableAcceptanceCriteria", []),
            "reusable_tests": memory_context.get("reusableTests", []),
            "ui_considerations": _ui_considerations(relevant_profile, flows),
            "technical_considerations": _technical_considerations(relevant_profile, modules),
            "qa_considerations": _qa_considerations(relevant_profile, flows),
            "proposed_tasks": proposed_tasks,
            "task_intelligence_diagnostics": task_plan["diagnostics"],
            "generation_review": _generation_review(relevant_profile, proposed_tasks, modules, _context_keywords(title, description, relevant_profile)),
            **_relevance_metadata(selection),
        }
        deterministic["work_item_dna"] = current_dna or generateDNA(
            _with_selected_evidence(story_for_generation, modules, flows, deterministic["dependencies"], deterministic["risks"]),
            "Story",
            profile=relevant_profile,
            parent_dna=parent_dna,
            validation_report={"score": acceptance_quality_score, "issues": []},
        )
        dna_validation = validateDNA(parent_dna, deterministic["work_item_dna"])
        deterministic["dna_validation"] = dna_validation
        deterministic["dna_diagnostics"] = _dna_diagnostics(parent_dna, deterministic["work_item_dna"])
        if not dna_validation["valid"]:
            return _dna_error_response(deterministic, dna_validation)
        story_analysis_options = _story_analysis_options(options)
        pipeline = _run_story_analysis_pipeline(story_for_generation, relevant_profile, _existing_children_from_options(options), story_analysis_options)
        deterministic["proposed_tasks"] = _attach_validation_to_items(proposed_tasks, pipeline, "Task")
        deterministic["proposed_tasks"] = [
            _with_child_dna(task, "Task", deterministic["work_item_dna"], relevant_profile, validation_report=task.get("validationReport"))
            for task in deterministic["proposed_tasks"]
        ]
        deterministic["generation_review"] = _generation_review(relevant_profile, deterministic["proposed_tasks"], modules, _context_keywords(title, description, relevant_profile))
        deterministic.update(_pipeline_payload(pipeline))
        story_ai_requested = bool(story_analysis_options.get("story_ai_requested"))
        provider_metadata = _story_analysis_provider_metadata(
            _run_story_analysis_ai_enrichment(story_for_generation, deterministic, relevant_profile, story_analysis_options)
            if story_ai_requested
            else _intelligence_pipeline_metadata(pipeline)
        )
        deterministic.update(
            _story_analysis_payload(
                story_for_generation,
                deterministic,
                provider_metadata,
                modules,
                flows,
                selection,
                dna_validation,
                ai_requested=story_ai_requested,
            )
        )
        deterministic["intelligence_trace"] = self._trace_decision(
            profile=relevant_profile,
            artifact_type="Story",
            artifact=story_for_generation,
            stage="Planning",
            source="Planning Intelligence",
            decision="Generate Task Recommendations",
            reason="Story DNA, acceptance criteria, selected modules/flows, Engineering Memory, and validation reports produced implementation tasks.",
            confidence=float((deterministic.get("work_item_dna") or {}).get("confidence") or 0.8),
            evidence=[
                {"type": "acceptance_criteria", "count": len(acceptance)},
                {"type": "modules", "items": modules},
                {"type": "flows", "items": flows},
            ],
            memory_context=memory_context,
            repository_evidence=modules + flows,
            validation_result={"reports": pipeline.get("validationReports", []), "dna": dna_validation},
            metadata=provider_metadata,
        )
        return _with_provider_metadata(deterministic, provider_metadata)

    def generate_qa_test_cases(
        self,
        story: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
        impact_analysis: dict[str, Any] | None = None,
        execution_package: dict[str, Any] | None = None,
        execution_plan: dict[str, Any] | str | None = None,
        implementation_validation: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        active_profile = _merge_external_knowledge(_normalize_profile(profile or self.get_profile()), knowledge_profile or {})
        title = _clean_text(story.get("title")) or "Untitled story"
        description = _clean_text(story.get("description"))
        keywords = _context_keywords(title, description, active_profile)
        impact = _normalize_story_impact(
            impact_analysis or self.analyze_story_impact(story, active_profile, active_profile["knowledge_registry"])
        )
        modules = _string_list(story.get("modules")) or _string_list(story.get("affected_modules")) or impact["affected_modules"]
        flows = _string_list(story.get("flows")) or _string_list(story.get("affected_flows")) or impact["affected_flows"]
        dependencies = _string_list(story.get("dependencies")) or impact["dependencies"] or _impact_dependencies(active_profile, keywords, modules, flows)
        acceptance = _string_list(story.get("acceptance_criteria")) or _acceptance_criteria(title, flows, modules)
        qa_action = _clean_text((options or {}).get("qa_action")).lower()
        existing_suite = (options or {}).get("existing_test_suite") if isinstance((options or {}).get("existing_test_suite"), dict) else {}
        memory_context = self._memory_context(
            "qa",
            active_profile,
            "Test Suite",
            story,
            modules=modules,
            flows=flows,
            acceptance_criteria=acceptance,
            capability=title,
        )
        suite = _qa_test_suite(title, description, acceptance, modules, flows, dependencies, active_profile, keywords)
        suite["memory_context"] = memory_context
        suite["memory_diagnostics"] = memory_context.get("diagnostics", {})
        suite["qa_memory"] = {
            "prior_tests": memory_context.get("reusableTests", []),
            "regression_patterns": [
                memory for memory in memory_context.get("relevantMemories", [])
                if "regression" in " ".join(_string_list(memory.get("tags"))).lower()
                or "regression" in _clean_text(memory.get("summary")).lower()
            ],
            "known_risks": memory_context.get("knownRisks", []),
            "previous_successful_artifacts": memory_context.get("previousSuccessfulArtifacts", []),
        }
        suite["generation_review"] = _generation_review(active_profile, suite["test_suite"]["test_cases"], modules, keywords)
        if qa_action == "generate_missing_tests" and existing_suite:
            suite = _append_missing_qa_tests(existing_suite, acceptance, title, modules, flows, dependencies, keywords)
            suite["memory_context"] = memory_context
            suite["memory_diagnostics"] = memory_context.get("diagnostics", {})
            suite["qa_memory"] = {
                "prior_tests": memory_context.get("reusableTests", []),
                "regression_patterns": [
                    memory for memory in memory_context.get("relevantMemories", [])
                    if "regression" in " ".join(_string_list(memory.get("tags"))).lower()
                    or "regression" in _clean_text(memory.get("summary")).lower()
                ],
                "known_risks": memory_context.get("knownRisks", []),
                "previous_successful_artifacts": memory_context.get("previousSuccessfulArtifacts", []),
            }
            suite["generation_review"] = _generation_review(active_profile, suite["test_suite"]["test_cases"], modules, keywords)
        phi_item = {
            **story,
            "title": title,
            "description": description,
            "acceptance_criteria": acceptance,
            "affected_modules": modules,
            "affected_flows": flows,
            "dependencies": dependencies,
            "domain": _clean_text(active_profile.get("domain")) or active_profile["knowledge_profile_preview"].get("domain") or "",
        }
        active_profile = self._profile_with_capsule("qa", active_profile, phi_item)
        phi = _project_phi_json(
            "generate_qa_test_cases",
            active_profile,
            phi_item,
            suite,
            options,
            ["test_suite", "coverage_summary", "coverage_score", "coverage_breakdown", "generated_test_count", "coverage_gaps", "generation_review"],
        )
        if phi["used"]:
            merged = _merge_known_fields(
                suite,
                _normalize_phi_qa_suite(phi["parsed"], suite),
                ["test_suite", "coverage_summary", "coverage_score", "coverage_breakdown", "generated_test_count", "coverage_gaps", "generation_review"],
            )
            merged["generation_review"] = suite["generation_review"]
            merged["memory_context"] = memory_context
            merged["memory_diagnostics"] = memory_context.get("diagnostics", {})
            merged["qa_memory"] = suite["qa_memory"]
            qa_payload = _attach_qa_intelligence(merged, story, active_profile, execution_package, execution_plan, implementation_validation)
            qa_payload["intelligence_trace"] = self._trace_decision(
                profile=active_profile,
                artifact_type="Story",
                artifact=story,
                stage="QA",
                source="QA Intelligence",
                decision="Generate QA Test Suite",
                reason="Story acceptance criteria, execution context, repository knowledge, Engineering Memory, and QA readiness rules produced the test suite.",
                confidence=float((qa_payload.get("qa_readiness") or {}).get("overallReadiness") or qa_payload.get("coverage_score") or 0) / 100,
                evidence=[{"type": "acceptance_criteria", "count": len(acceptance)}, {"type": "tests", "count": qa_payload.get("generated_test_count", 0)}],
                memory_context=memory_context,
                repository_evidence=modules + flows,
                validation_result=qa_payload.get("qa_readiness") or {},
                metadata=phi["metadata"],
            )
            return _with_provider_metadata(qa_payload, phi["metadata"])
        if phi["blocked"]:
            return _phi_error_response(phi)
        qa_payload = _attach_qa_intelligence(suite, story, active_profile, execution_package, execution_plan, implementation_validation)
        qa_payload["intelligence_trace"] = self._trace_decision(
            profile=active_profile,
            artifact_type="Story",
            artifact=story,
            stage="QA",
            source="QA Intelligence",
            decision="Generate QA Test Suite",
            reason="Story acceptance criteria, execution context, repository knowledge, Engineering Memory, and QA readiness rules produced the test suite.",
            confidence=float((qa_payload.get("qa_readiness") or {}).get("overallReadiness") or qa_payload.get("coverage_score") or 0) / 100,
            evidence=[{"type": "acceptance_criteria", "count": len(acceptance)}, {"type": "tests", "count": qa_payload.get("generated_test_count", 0)}],
            memory_context=memory_context,
            repository_evidence=modules + flows,
            validation_result=qa_payload.get("qa_readiness") or {},
            metadata=phi["metadata"],
        )
        return _with_provider_metadata(qa_payload, phi["metadata"])

    def analyze_story_impact(
        self,
        story: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        active_profile = _merge_external_knowledge(_normalize_profile(profile or self.get_profile()), knowledge_profile or {})
        title = _clean_text(story.get("title")) or "Untitled story"
        description = _clean_text(story.get("description"))
        selection = _select_knowledge_context(active_profile, story, "Story")
        keywords = _string_list(selection.get("intent", {}).get("keywords")) or _context_keywords(title, description, active_profile)
        modules = _selection_names(selection, "relevant_modules")
        flows = _selection_names(selection, "relevant_flows")
        return {
            "affected_applications": _impact_applications(active_profile, keywords),
            "affected_modules": modules,
            "affected_flows": flows,
            "affected_components": _impact_components(active_profile, modules, flows),
            "dependencies": _selection_names(selection, "relevant_dependencies") or _impact_dependencies(active_profile, keywords, modules, flows),
            "risks": _impact_risks(active_profile, keywords, modules, flows),
            "integration_points": _integration_points(active_profile, modules, flows),
            "recommended_reviewers": _recommended_reviewers(active_profile, modules, flows),
            **_relevance_metadata(selection),
            **_knowledge_registry_metadata("Impact analysis uses the Knowledge Registry and relationship graph."),
        }

    def analyze_feature_impact(
        self,
        feature: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        active_profile = _merge_external_knowledge(_normalize_profile(profile or self.get_profile()), knowledge_profile or {})
        title = _clean_text(feature.get("title")) or "Untitled feature"
        description = _clean_text(feature.get("description"))
        selection = _select_knowledge_context(active_profile, feature, "Feature")
        keywords = _string_list(selection.get("intent", {}).get("keywords")) or _context_keywords(title, description, active_profile)
        modules = _selection_names(selection, "relevant_modules")
        flows = _selection_names(selection, "relevant_flows")
        return {
            "affected_applications": _impact_applications(active_profile, keywords),
            "affected_modules": modules,
            "affected_flows": flows,
            "cross_team_dependencies": _cross_team_dependencies(active_profile, modules),
            "integration_points": _integration_points(active_profile, modules, flows),
            "risks": _impact_risks(active_profile, keywords, modules, flows),
            **_relevance_metadata(selection),
            **_knowledge_registry_metadata("Impact analysis uses the Knowledge Registry and relationship graph."),
        }

    def analyze_epic_impact(
        self,
        epic: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        active_profile = _merge_external_knowledge(_normalize_profile(profile or self.get_profile()), knowledge_profile or {})
        title = _clean_text(epic.get("title")) or "Untitled epic"
        description = _clean_text(epic.get("description"))
        selection = _select_knowledge_context(active_profile, epic, "Epic")
        keywords = _string_list(selection.get("intent", {}).get("keywords")) or _context_keywords(title, description, active_profile)
        modules = _selection_names(selection, "relevant_modules")
        flows = _selection_names(selection, "relevant_flows")
        return {
            "affected_applications": _impact_applications(active_profile, keywords),
            "affected_modules": modules,
            "affected_flows": flows,
            "program_dependencies": _program_dependencies(active_profile, modules, flows),
            "risks": _impact_risks(active_profile, keywords, modules, flows),
            "recommended_rollout_strategy": _rollout_strategy(active_profile, keywords),
            **_relevance_metadata(selection),
            **_knowledge_registry_metadata("Impact analysis uses the Knowledge Registry and relationship graph."),
        }

    def build_execution_context(
        self,
        story: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
        impact_analysis: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        active_profile = _merge_external_knowledge(_normalize_profile(profile or self.get_profile()), knowledge_profile or {})
        story = story or {}
        executable = _execution_executable_artifact(story, options)
        parent_story = _execution_parent_story(story, executable)
        title = _clean_text(story.get("title")) or "Untitled story"
        description = _clean_text(story.get("description"))
        selection = _select_knowledge_context(active_profile, story, "Story")
        relevant_profile = _profile_with_relevance(active_profile, selection)
        refined_story = self.refine_story(parent_story, relevant_profile, relevant_profile["knowledge_registry"], {"force_provider": "deterministic_fallback"})
        impact = _normalize_story_impact(
            impact_analysis or self.analyze_story_impact(parent_story, relevant_profile, relevant_profile["knowledge_registry"])
        )
        acceptance = _string_list(executable.get("acceptance_criteria")) or _string_list(parent_story.get("acceptance_criteria")) or refined_story["acceptance_criteria"]
        has_impact = any(impact[key] for key in ["affected_applications", "affected_modules", "affected_flows", "dependencies", "risks"])
        readiness = _execution_readiness_score(relevant_profile, has_impact)
        recommended_files = _recommended_files(relevant_profile, impact, title)
        file_ranking_status = "Repository file ranking available" if recommended_files else "Repository file ranking not available"
        memory_context = self._memory_context(
            "execution",
            relevant_profile,
            "Execution Package",
            executable,
            modules=impact["affected_modules"],
            flows=impact["affected_flows"],
            acceptance_criteria=acceptance,
            repository_files=recommended_files,
            capability=title,
        )
        task_plan = _task_intelligence(title, description, acceptance, impact, relevant_profile, recommended_files)
        generated_tasks = [
            {
                **task,
                **_lineage_metadata(story, "Story", "story_acceptance_criteria + context_capsule", selection, float(task.get("confidence") or 0.8)),
            }
            for task in task_plan["tasks"]
        ]
        selected_task = executable if _execution_artifact_type(executable) == "Task" else _selected_execution_task(story, generated_tasks, require_explicit=True)
        implementation_tasks = _tasks_for_areas(generated_tasks, ["UI Work", "Backend Work", "Data Work", "Analytics Work"])
        pipeline = _run_intelligence_pipeline(
            {**executable, "selected_task": selected_task or {}, "acceptance_criteria": acceptance},
            parent_story,
            relevant_profile,
            "Task",
            _existing_children_from_options(options),
            {**(options or {}), "deterministic_only": True},
        )
        story_dna_source = {
            **parent_story,
            "affected_modules": impact["affected_modules"],
            "affected_flows": impact["affected_flows"],
            "affected_applications": impact["affected_applications"],
            "dependencies": impact["dependencies"] or refined_story["dependencies"],
            "risks": impact["risks"] or refined_story["risks"],
        }
        story_dna = _option_parent_dna(options) or (parent_story.get("work_item_dna") if isinstance(parent_story.get("work_item_dna"), dict) else None) or generateDNA(
            story_dna_source,
            "Story",
            profile=relevant_profile,
            validation_report={"score": _basic_validation_score(impact["affected_modules"], impact["affected_flows"]), "issues": []},
        )
        task_dna_source = {
            **(selected_task or story),
            "affected_modules": impact["affected_modules"],
            "affected_flows": impact["affected_flows"],
            "affected_applications": impact["affected_applications"],
            "dependencies": impact["dependencies"] or refined_story["dependencies"],
            "risks": impact["risks"] or refined_story["risks"],
        }
        task_dna = (
            generateDNA(
                task_dna_source,
                "Task",
                profile=relevant_profile,
                parent_dna=story_dna,
                validation_report=pipeline["validationReports"][0] if pipeline.get("validationReports") else None,
            )
            if selected_task
            else story_dna
        )
        dna_validation = validateDNA(story_dna if selected_task else None, task_dna)
        cache = self._read_knowledge_cache()
        capsules = self._read_context_capsules()
        context_capsule = _pipeline_context_capsule(
            capsule_type="execution",
            source_work_item={
                **executable,
                "dependencies": impact["dependencies"] or refined_story["dependencies"],
                "risks": impact["risks"] or refined_story["risks"],
            },
            parent_story=parent_story,
            acceptance_criteria=acceptance,
            pipeline=pipeline,
            profile=relevant_profile,
            cache=cache,
            selected_task=selected_task,
            work_item_dna=task_dna,
            previous=capsules.get("execution") if isinstance(capsules.get("execution"), dict) else None,
        )
        capsules["execution"] = context_capsule
        self._write_context_capsules(capsules)
        validation_report = pipeline["validationReports"][0] if pipeline.get("validationReports") else None
        deterministic = _execution_package_from_capsule(
            story=parent_story,
            selected_task=selected_task,
            acceptance_criteria=acceptance,
            context_capsule=context_capsule,
            generated_tasks=generated_tasks,
            task_plan=task_plan,
            readiness=readiness,
            profile=relevant_profile,
            validation_report=validation_report,
        )
        deterministic.update(
            {
                **_lineage_metadata(executable, _execution_artifact_type(executable), "executable_artifact + context_capsule", selection, float((selected_task or {}).get("confidence") or executable.get("confidence") or 0.8)),
                **_relevance_metadata(selection),
            }
        )
        deterministic["executable_artifact"] = executable
        deterministic["artifact_id"] = _item_id(executable)
        deterministic["artifact_type"] = _execution_artifact_type(executable)
        deterministic["execution_source"] = {
            "artifactId": deterministic["artifact_id"],
            "artifactType": deterministic["artifact_type"],
            "title": _clean_text(executable.get("title")),
            "description": _clean_text(executable.get("description")),
        }
        deterministic["rejected_context"] = deterministic["context_capsule"]["rejectedContext"]
        deterministic["work_item_dna"] = task_dna
        deterministic["parent_work_item_dna"] = story_dna
        deterministic["dna_validation"] = dna_validation
        deterministic["memory_context"] = memory_context
        deterministic["memory_diagnostics"] = memory_context.get("diagnostics", {})
        deterministic["relevant_prior_implementation"] = memory_context.get("previousSuccessfulArtifacts", [])
        deterministic["prior_implementation_patterns"] = [
            memory for memory in memory_context.get("relevantMemories", [])
            if memory.get("category") in {"Execution Memory", "Pattern Memory"}
        ]
        deterministic["known_implementation_risks"] = memory_context.get("knownRisks", [])
        deterministic["reusable_testing_expectations"] = memory_context.get("reusableTests", [])
        deterministic.update(_pipeline_payload(pipeline))
        deterministic.update(_context_capsule_metadata(context_capsule))
        active_profile = {**relevant_profile, "_active_context_capsule": context_capsule}
        metadata = _execution_primary_metadata(time.monotonic(), "build_execution_context")
        deterministic["intelligence_trace"] = self._trace_decision(
            profile=relevant_profile,
            artifact_type=_execution_artifact_type(executable),
            artifact=executable,
            stage="Execution",
            source="Execution Intelligence",
            decision="Build Execution Package",
            reason="Task or Story DNA, Context Capsule, Repository Intelligence, Engineering Graph evidence, Engineering Memory, and validation report produced the execution package.",
            confidence=float(context_capsule.get("confidence") or 0.8),
            evidence=[
                {"type": "context_capsule", "id": context_capsule.get("capsuleId"), "tokenEstimate": context_capsule.get("tokenEstimate")},
                {"type": "acceptance_criteria", "count": len(acceptance)},
            ],
            memory_context=memory_context,
            repository_evidence=(context_capsule.get("selectedModules") or []) + (context_capsule.get("selectedFlows") or []) + (context_capsule.get("relevantFiles") or []),
            graph_evidence=context_capsule.get("graphReferences") or [],
            validation_result=validation_report or {},
            metadata=metadata,
        )
        if not _execution_ai_enrichment_enabled(options):
            return _with_implementation_package_aliases(_with_provider_metadata(deterministic, metadata))
        phi = _project_phi_json("build_execution_context", active_profile, executable, deterministic, _execution_ai_options(options), _execution_enrichment_keys("build_execution_context", deterministic))
        if phi["used"]:
            merged = _merge_known_fields(deterministic, phi["parsed"], _execution_enrichment_keys("build_execution_context", deterministic))
            merged["proposed_tasks"] = generated_tasks
            merged["task_intelligence_diagnostics"] = task_plan["diagnostics"]
            merged["implementation_tasks"] = implementation_tasks
            merged["ai_enrichment_status"] = "enriched"
            return _with_implementation_package_aliases(_with_provider_metadata(merged, phi["metadata"]))
        return _with_implementation_package_aliases(_with_provider_metadata(deterministic, _execution_timeout_metadata(metadata, phi["metadata"])))

    def build_dev_prompt(
        self,
        story: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
        impact_analysis: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        context = self.build_execution_context(story, profile, knowledge_profile, impact_analysis, {**(options or {}), "force_provider": "deterministic_fallback"})
        active_profile = _active_capsule_profile_from_execution_package(context)
        phi_item = _execution_package_phi_item(context)
        provider_name = _clean_text((options or {}).get("provider") or "azure_phi")
        provider_model = _clean_text((options or {}).get("model"))
        deterministic = build_developer_prompt_v2(
            context.get("execution_package_v2") if isinstance(context.get("execution_package_v2"), dict) else {},
            provider=provider_name,
            model=provider_model,
        )
        deterministic["developer_prompt_v2"] = {
            key: value
            for key, value in deterministic.items()
            if key not in {"developer_prompt_v2"}
        }
        deterministic["execution_package_v2"] = context.get("execution_package_v2", {})
        deterministic.update(_prompt_validation_payload(context, "Dev Prompt", deterministic["prompt"]))
        metadata = _execution_primary_metadata(time.monotonic(), "build_dev_prompt")
        if not _execution_ai_enrichment_enabled(options):
            return _with_ai_prompt_aliases(_with_provider_metadata(deterministic, metadata))
        phi = _project_phi_json("build_dev_prompt", active_profile, phi_item, deterministic, _execution_ai_options(options), ["prompt"])
        if phi["used"]:
            return _with_ai_prompt_aliases(_with_provider_metadata({**deterministic, **_pick_string_fields(phi["parsed"], ["prompt"])}, phi["metadata"]))
        return _with_ai_prompt_aliases(_with_provider_metadata(deterministic, _execution_timeout_metadata(metadata, phi["metadata"])))

    def build_execution_plan(
        self,
        story: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
        impact_analysis: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = self.build_execution_context(story, profile, knowledge_profile, impact_analysis, {**(options or {}), "force_provider": "deterministic_fallback"})
        provider_name = _clean_text((options or {}).get("provider") or "azure_phi")
        provider_model = _clean_text((options or {}).get("model"))
        execution_mode = _clean_text((options or {}).get("execution_mode") or (options or {}).get("executionMode") or "implement")
        deterministic = build_execution_plan(
            context.get("execution_package_v2") if isinstance(context.get("execution_package_v2"), dict) else {},
            execution_mode=execution_mode,
            provider=provider_name,
            model=provider_model,
        )
        execution_package_v2 = context.get("execution_package_v2") if isinstance(context.get("execution_package_v2"), dict) else {}
        skill_payload = self._skill_engine.compose(
            execution_package_v2,
            {
                "memoryContext": context.get("memory_context", {}),
                "executionMode": execution_mode,
            },
        )
        skill_section = _execution_plan_skill_section(skill_payload)
        if skill_section:
            plan_text = str(deterministic.get("plan") or deterministic.get("finalPlan") or "").strip()
            enriched_plan = f"{plan_text}\n\n{skill_section}".strip()
            deterministic["plan"] = enriched_plan
            deterministic["finalPlan"] = enriched_plan
        deterministic["execution_plan"] = {
            key: value
            for key, value in deterministic.items()
            if key not in {"execution_plan"}
        }
        if isinstance(deterministic.get("execution_plan"), dict):
            deterministic["execution_plan"]["engineeringSkills"] = skill_payload.get("skills", [])
            deterministic["execution_plan"]["skillComposition"] = skill_payload.get("composition", {})
            deterministic["execution_plan"]["skillDiagnostics"] = skill_payload.get("diagnostics", {})
        deterministic["execution_package_v2"] = execution_package_v2
        deterministic["engineering_skills"] = skill_payload.get("skills", [])
        deterministic["skill_composition"] = skill_payload.get("composition", {})
        deterministic["skill_diagnostics"] = skill_payload.get("diagnostics", {})
        deterministic["execution_context"] = {
            "packageId": context.get("execution_package_v2", {}).get("packageId") if isinstance(context.get("execution_package_v2"), dict) else context.get("package_id"),
            "artifactId": context.get("artifact_id"),
            "artifactType": context.get("artifact_type"),
            "executionSource": context.get("execution_source"),
        }
        deterministic.update(_prompt_validation_payload(context, "Execution Plan", deterministic["plan"]))
        metadata = _execution_primary_metadata(time.monotonic(), "build_execution_plan")
        return _with_implementation_plan_aliases(_with_provider_metadata(deterministic, metadata))

    def build_ui_prompt(
        self,
        story: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
        impact_analysis: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        context = self.build_execution_context(story, profile, knowledge_profile, impact_analysis, {**(options or {}), "force_provider": "deterministic_fallback"})
        active_profile = _active_capsule_profile_from_execution_package(context)
        phi_item = _execution_package_phi_item(context)
        ui = context["ui_guidelines"]
        deterministic = {
            "prompt": _execution_prompt(
                "UI Prompt",
                context,
                [
                    "Design the affected user experience and states for the approved story.",
                    f"Colors: primary={ui['primary_color'] or 'use project default'}, secondary={ui['secondary_color'] or 'use project default'}",
                    f"Typography: {ui['typography'] or 'use project default'}",
                    f"Component Library: {ui['component_library'] or 'reuse existing components'}",
                    f"Accessibility Rules: {', '.join(ui['accessibility_rules']) or 'Validate accessibility expectations.'}",
                    f"Affected User Flows: {', '.join(context['affected_flows']) or 'Confirm affected flows.'}",
                ],
            )
        }
        deterministic.update(_prompt_validation_payload(context, "UI Prompt", deterministic["prompt"]))
        metadata = _execution_primary_metadata(time.monotonic(), "build_ui_prompt")
        if not _execution_ai_enrichment_enabled(options):
            return _with_ai_prompt_aliases(_with_provider_metadata(deterministic, metadata), "ui")
        phi = _project_phi_json("build_ui_prompt", active_profile, phi_item, deterministic, _execution_ai_options(options), ["prompt"])
        if phi["used"]:
            return _with_ai_prompt_aliases(_with_provider_metadata({**deterministic, **_pick_string_fields(phi["parsed"], ["prompt"])}, phi["metadata"]), "ui")
        return _with_ai_prompt_aliases(_with_provider_metadata(deterministic, _execution_timeout_metadata(metadata, phi["metadata"])), "ui")

    def build_qa_prompt(
        self,
        story: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
        impact_analysis: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        context = self.build_execution_context(story, profile, knowledge_profile, impact_analysis, {**(options or {}), "force_provider": "deterministic_fallback"})
        active_profile = _active_capsule_profile_from_execution_package(context)
        phi_item = _execution_package_phi_item(context)
        deterministic = {
            "prompt": _execution_prompt(
                "QA Prompt",
                context,
                [
                    "Create manual and automation-ready coverage for the approved story.",
                    f"Risks: {', '.join(context['risks']) or 'Confirm risks before testing.'}",
                    f"Dependencies: {', '.join(context['dependencies']) or 'Confirm dependencies before testing.'}",
                    f"Integration Points: {', '.join(_unique(context['affected_modules'] + context['affected_flows'])) or 'Confirm integration points.'}",
                    f"Regression Areas: {', '.join(_unique(context['affected_flows'] + context['affected_modules'])) or 'Confirm regression scope.'}",
                    f"Testing Tasks: {', '.join(context['testing_tasks']) or 'Define test cases before validation.'}",
                ],
            )
        }
        deterministic.update(_prompt_validation_payload(context, "QA Prompt", deterministic["prompt"]))
        metadata = _execution_primary_metadata(time.monotonic(), "build_qa_prompt")
        if not _execution_ai_enrichment_enabled(options):
            return _with_ai_prompt_aliases(_with_provider_metadata(deterministic, metadata), "qa")
        phi = _project_phi_json("build_qa_prompt", active_profile, phi_item, deterministic, _execution_ai_options(options), ["prompt"])
        if phi["used"]:
            return _with_ai_prompt_aliases(_with_provider_metadata({**deterministic, **_pick_string_fields(phi["parsed"], ["prompt"])}, phi["metadata"]), "qa")
        return _with_ai_prompt_aliases(_with_provider_metadata(deterministic, _execution_timeout_metadata(metadata, phi["metadata"])), "qa")

    def build_copilot_context(
        self,
        story: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
        impact_analysis: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        context = self.build_execution_context(story, profile, knowledge_profile, impact_analysis, {**(options or {}), "force_provider": "deterministic_fallback"})
        active_profile = _active_capsule_profile_from_execution_package(context)
        phi_item = _execution_package_phi_item(context)
        capsule = context.get("context_capsule") if isinstance(context.get("context_capsule"), dict) else {}
        lines = [
            "Project Awareness Context",
            "",
            f"Project: {capsule.get('projectName') or 'Not specified'}",
            f"Domain: {capsule.get('domain') or 'Not specified'}",
            f"Project Type: {capsule.get('projectType') or 'Not specified'}",
            f"Capsule: {capsule.get('capsuleId') or 'Not available'}",
            f"Knowledge Version: {capsule.get('knowledgeVersion') or 'Not available'}",
            f"Repository Snapshot: {capsule.get('repositorySnapshotVersion') or 'Not available'}",
            "",
            f"Story: {_clean_text(context.get('parent_story', {}).get('title')) or 'Untitled story'}",
            context["story_summary"],
            "",
            "Affected Applications:",
            *_bullet_lines(context["affected_applications"]),
            "",
            "Affected Modules:",
            *_bullet_lines(context["affected_modules"]),
            "",
            "Affected Flows:",
            *_bullet_lines(context["affected_flows"]),
            "",
            "Dependencies:",
            *_bullet_lines(context["dependencies"]),
            "",
            "Standards:",
            *_bullet_lines(_flatten_standards(context["development_standards"])),
        ]
        deterministic = {"context": "\n".join(lines).strip()}
        deterministic.update(_prompt_validation_payload(context, "Copilot Context", deterministic["context"]))
        metadata = _execution_primary_metadata(time.monotonic(), "build_copilot_context")
        if not _execution_ai_enrichment_enabled(options):
            return _with_provider_metadata(deterministic, metadata)
        phi = _project_phi_json("build_copilot_context", active_profile, phi_item, deterministic, _execution_ai_options(options), ["context"])
        if phi["used"]:
            return _with_provider_metadata({**deterministic, **_pick_string_fields(phi["parsed"], ["context"])}, phi["metadata"])
        return _with_provider_metadata(deterministic, _execution_timeout_metadata(metadata, phi["metadata"]))

    def validate_implementation(
        self,
        execution_package: dict[str, Any],
        developer_prompt: dict[str, Any] | None = None,
        task_dna: dict[str, Any] | None = None,
        story_dna: dict[str, Any] | None = None,
        repository_diff: dict[str, Any] | None = None,
        changed_files: list[Any] | None = None,
        test_results: dict[str, Any] | None = None,
        build_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return validate_implementation(
            execution_package=execution_package or {},
            developer_prompt=developer_prompt or {},
            task_dna=task_dna or {},
            story_dna=story_dna or {},
            repository_diff=repository_diff or {},
            changed_files=changed_files or [],
            test_results=test_results or {},
            build_result=build_result or {},
        )

    def review_pr(
        self,
        pull_request: dict[str, Any] | None = None,
        linked_work_items: list[Any] | None = None,
        execution_package: dict[str, Any] | None = None,
        developer_prompt: dict[str, Any] | None = None,
        task_dna: dict[str, Any] | None = None,
        story_dna: dict[str, Any] | None = None,
        repository_diff: dict[str, Any] | None = None,
        changed_files: list[Any] | None = None,
        test_results: dict[str, Any] | None = None,
        build_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return review_pr(
            pull_request=pull_request or {},
            linked_work_items=linked_work_items or [],
            execution_package=execution_package or {},
            developer_prompt=developer_prompt or {},
            task_dna=task_dna or {},
            story_dna=story_dna or {},
            repository_diff=repository_diff or {},
            changed_files=changed_files or [],
            test_results=test_results or {},
            build_result=build_result or {},
        )

    def post_pr_review_comment(self, report: dict[str, Any]) -> dict[str, Any]:
        return PRReviewEngine().post_comment(report or {})

    def provider_probe(self, prompt: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = options or {}
        phi = _project_phi_probe(prompt, options)
        return {
            "provider_used": phi["metadata"]["provider_used"],
            "phi_status": phi["metadata"]["phi_status"],
            "raw_response_preview": phi["metadata"]["phi_raw_response_preview"],
            "parsed_response": phi.get("parsed", {}),
            "latency_ms": phi["metadata"]["phi_latency_ms"],
            **phi["metadata"],
        }


def _normalize_profile(profile: dict[str, Any]) -> dict[str, Any]:
    ui = profile.get("ui_guidelines") if isinstance(profile.get("ui_guidelines"), dict) else {}
    standards = profile.get("development_standards") if isinstance(profile.get("development_standards"), dict) else {}
    preview = profile.get("knowledge_profile_preview") if isinstance(profile.get("knowledge_profile_preview"), dict) else {}
    repository_connection = _normalize_repository_connection(profile.get("repository_connection"))
    connectors = _normalize_connectors(profile.get("connectors"), repository_connection)
    normalized = {
        "onboarding_completed": bool(profile.get("onboarding_completed")),
        "project_id": _clean_text(profile.get("project_id")),
        "project_name": _clean_text(profile.get("project_name")),
        "domain": _clean_text(profile.get("domain")),
        "project_type": _clean_text(profile.get("project_type")),
        "project_description": _clean_text(profile.get("project_description")),
        "connectors": connectors,
        "repository_connection": _repository_connection_from_connector(connectors["azure_devops"], repository_connection),
        "readme_analysis": _normalize_readme_analysis(profile.get("readme_analysis")),
        "knowledge_registry": _normalize_knowledge_registry(profile.get("knowledge_registry")),
        "applications": _normalize_applications(profile.get("applications")),
        "technology_stack": _normalize_stack(profile.get("technology_stack")),
        "development_standards": {
            "architecture_patterns": _string_list(standards.get("architecture_patterns")),
            "coding_guidelines": _string_list(standards.get("coding_guidelines")),
            "security_requirements": _string_list(standards.get("security_requirements")),
            "testing_requirements": _string_list(standards.get("testing_requirements")),
        },
        "ui_guidelines": {
            "primary_color": _clean_text(ui.get("primary_color")),
            "secondary_color": _clean_text(ui.get("secondary_color")),
            "typography": _clean_text(ui.get("typography")),
            "component_library": _clean_text(ui.get("component_library")),
            "accessibility_rules": _string_list(ui.get("accessibility_rules")),
        },
        "repository_sources": _string_list(profile.get("repository_sources")),
        "knowledge_profile_preview": {
            "domain": _clean_text(preview.get("domain")) or _clean_text(profile.get("domain")),
            "systems": _string_list(preview.get("systems")),
            "standards": _string_list(preview.get("standards")),
            "repository_status": _clean_text(preview.get("repository_status")) or "Repository README scan coming next.",
            "readiness": _clean_text(preview.get("readiness")),
        },
    }
    if not normalized["knowledge_profile_preview"]["systems"]:
        normalized["knowledge_profile_preview"]["systems"] = [app["name"] for app in normalized["applications"]]
    if not normalized["knowledge_profile_preview"]["standards"]:
        normalized["knowledge_profile_preview"]["standards"] = _flatten_standards(normalized["development_standards"])
    normalized["knowledge_profile_preview"]["readiness"] = normalized["knowledge_profile_preview"]["readiness"] or _readiness(normalized)
    return normalized


def _run_intelligence_pipeline(
    work_item: dict[str, Any],
    parent_work_item: dict[str, Any] | None,
    profile: dict[str, Any],
    output_type: str,
    existing_children: list[dict[str, Any]] | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    options = options or {}
    parent_work_item = parent_work_item or work_item
    repository_snapshot = _repository_snapshot_from_profile(profile)
    knowledge_registry = profile.get("knowledge_registry") if isinstance(profile.get("knowledge_registry"), dict) else {}
    intent = build_intent(work_item)
    capability_context = buildCapabilityContext(
        intent,
        {
            "parent_work_item": parent_work_item,
            "project_profile": profile,
            "repository_snapshot": repository_snapshot,
            "knowledge_registry": knowledge_registry,
        },
    )
    planning_context = buildPlanningContext(
        work_item,
        parent_work_item,
        {
            "intentModel": intent,
            "capabilityContext": capability_context,
            "projectProfile": profile,
            "repositorySnapshot": repository_snapshot,
            "knowledgeRegistry": knowledge_registry,
            "existingChildren": existing_children or [],
        },
    )
    planning_provider = _planning_llm_provider(options)
    reasoning = generatePlanningArtifact(
        planning_context,
        output_type,
        {
            "provider": planning_provider,
            "deterministic_only": bool(options.get("deterministic_only")),
        },
    )
    provider_metadata = getattr(planning_provider, "metadata", {}) if planning_provider is not None else {}
    provider_parsed = getattr(planning_provider, "parsed", {}) if planning_provider is not None else {}
    artifacts = []
    for artifact in reasoning.get("artifacts", []):
        if not isinstance(artifact, dict):
            continue
        report = validateArtifact(
            planning_context,
            artifact,
            {
                "repositorySnapshot": repository_snapshot,
                "knowledgeRegistry": knowledge_registry,
                "existingSiblings": existing_children or planning_context.get("existingChildren") or [],
            },
        )
        artifacts.append(
            {
                **artifact,
                "validationReport": report,
                "validationStatus": report["validationStatus"],
                "creationAllowed": report["validationStatus"] == "Approved",
                "manualEditAllowed": report["validationStatus"] == "NeedsReview",
                "creationBlocked": report["validationStatus"] == "Rejected",
            }
        )
    generic_artifacts = _generic_artifacts_from_pipeline(artifacts, work_item, output_type)
    return {
        "intent": intent,
        "capabilityContext": capability_context,
        "planningContext": planning_context,
        "reasoning": {**reasoning, "artifacts": artifacts},
        "artifacts": artifacts,
        "genericArtifacts": generic_artifacts,
        "validationReports": [artifact["validationReport"] for artifact in artifacts],
        "previewPolicy": _preview_policy([artifact["validationReport"] for artifact in artifacts]),
        "providerMetadata": provider_metadata,
        "providerParsed": provider_parsed,
    }


def _feature_analysis_ai_requested(options: dict[str, Any] | None) -> bool:
    options = options or {}
    mode = _clean_text(options.get("mode")).lower()
    force_provider = _clean_text(options.get("force_provider")).lower()
    if bool(options.get("deterministic_only")) or force_provider in {"deterministic_fallback", "domain_fallback"}:
        return False
    return (
        mode in {"ai_enrichment", "retry_ai_enrichment", "enhance_with_ai"}
        or bool(options.get("retry_ai_enrichment"))
        or os.getenv("AI_GEN_PROJECT_INTELLIGENCE_USE_PHI", "0").strip().lower() in {"1", "true", "yes", "on"}
    )


def _feature_analysis_options(options: dict[str, Any] | None) -> dict[str, Any]:
    next_options = dict(options or {})
    if not _feature_analysis_ai_requested(next_options):
        next_options["deterministic_only"] = True
        next_options.setdefault("allow_fallback", True)
    else:
        next_options.setdefault("allow_fallback", True)
        next_options.setdefault(
            "timeout_seconds",
            int(os.getenv("AI_GEN_FEATURE_ANALYSIS_PROVIDER_TIMEOUT_SECONDS", os.getenv("AI_GEN_REFINER_TIMEOUT_SECONDS", "60"))),
        )
        next_options.setdefault("max_tokens", int(os.getenv("AI_GEN_FEATURE_ANALYSIS_MAX_TOKENS", "700")))
    return next_options


def _story_analysis_ai_requested(options: dict[str, Any] | None) -> bool:
    options = options or {}
    mode = _clean_text(options.get("mode")).lower()
    force_provider = _clean_text(options.get("force_provider")).lower()
    if bool(options.get("deterministic_only")) or force_provider in {"deterministic_fallback", "domain_fallback"}:
        return False
    return (
        mode in {"ai_enrichment", "retry_ai_enrichment", "enhance_with_ai"}
        or bool(options.get("retry_ai_enrichment"))
        or os.getenv("AI_GEN_PROJECT_INTELLIGENCE_USE_PHI", "0").strip().lower() in {"1", "true", "yes", "on"}
    )


def _story_analysis_options(options: dict[str, Any] | None) -> dict[str, Any]:
    next_options = dict(options or {})
    ai_requested = _story_analysis_ai_requested(next_options)
    # Story Analysis must never depend on JSON-producing LLM planning. Build the
    # deterministic draft first, then optionally enrich it with plain text.
    next_options["deterministic_only"] = True
    next_options.setdefault("allow_fallback", True)
    if ai_requested:
        next_options["story_ai_requested"] = True
        next_options.setdefault(
            "timeout_seconds",
            int(os.getenv("AI_GEN_STORY_ANALYSIS_PROVIDER_TIMEOUT_SECONDS", os.getenv("AI_GEN_REFINER_TIMEOUT_SECONDS", "60"))),
        )
        next_options.setdefault("max_tokens", int(os.getenv("AI_GEN_STORY_ANALYSIS_MAX_TOKENS", "650")))
    return next_options


def _run_story_analysis_pipeline(
    story: dict[str, Any],
    profile: dict[str, Any],
    existing_children: list[dict[str, Any]] | None,
    options: dict[str, Any],
) -> dict[str, Any]:
    deterministic_options = dict(options or {})
    deterministic_options["deterministic_only"] = True
    deterministic_options.setdefault("allow_fallback", True)
    try:
        return _run_intelligence_pipeline(story, story, profile, "Task", existing_children, deterministic_options)
    except TimeoutError as exc:
        return _story_analysis_pipeline_error(story, profile, existing_children, "timeout", exc)
    except Exception as exc:
        message = str(exc).lower()
        status = "parse_error" if "parse" in message or "json" in message or "normalized" in message else "provider_unavailable"
        return _story_analysis_pipeline_error(story, profile, existing_children, status, exc)


def _run_feature_analysis_pipeline(
    feature: dict[str, Any],
    profile: dict[str, Any],
    existing_children: list[dict[str, Any]] | None,
    options: dict[str, Any],
) -> dict[str, Any]:
    try:
        return _run_intelligence_pipeline(feature, feature, profile, "Story", existing_children, options)
    except TimeoutError as exc:
        return _feature_analysis_pipeline_error(feature, profile, existing_children, "timeout", exc)
    except Exception as exc:
        message = str(exc).lower()
        status = "parse_error" if "parse" in message or "json" in message or "normalized" in message else "provider_unavailable"
        return _feature_analysis_pipeline_error(feature, profile, existing_children, status, exc)


def _run_feature_analysis_ai_enrichment(
    feature: dict[str, Any],
    deterministic: dict[str, Any],
    profile: dict[str, Any],
    options: dict[str, Any],
) -> dict[str, Any]:
    provider = options.get("llm_provider") or options.get("provider")
    if not hasattr(provider, "probe_json"):
        provider = get_refinement_provider()
    context_diagnostics = {
        "operation": "refine_feature",
        "feature_analysis_enrichment": True,
        "provider_prompt_mode": "plain_text_reasoning",
    }
    if provider is None or not provider.is_enabled():
        metadata = _fallback_metadata("deterministic_feature_analysis", "Azure Phi provider is not configured for optional Feature Analysis enrichment.")
        metadata.update({"phi_status": "provider_unavailable", "fallback_used": False})
        return _with_context_diagnostics(metadata, context_diagnostics)
    health = provider.health_snapshot() if hasattr(provider, "health_snapshot") else {}
    prompt = _feature_analysis_plain_text_prompt(feature, deterministic, profile)
    timeout_seconds = int(options.get("timeout_seconds") or os.getenv("AI_GEN_FEATURE_ANALYSIS_PROVIDER_TIMEOUT_SECONDS", os.getenv("AI_GEN_REFINER_TIMEOUT_SECONDS", "60")))
    max_tokens = int(options.get("max_tokens") or os.getenv("AI_GEN_FEATURE_ANALYSIS_MAX_TOKENS", "700"))
    try:
        probe = probe_json_with_budget(
            provider,
            _feature_analysis_enrichment_sections(prompt),
            operation="refine_feature",
            system_prompt=FEATURE_ANALYSIS_ENRICHMENT_SYSTEM_PROMPT,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
            response_format_enabled=False,
            allow_retry_without_response_format=False,
        )
    except TimeoutError as exc:
        probe = {
            "status": "timeout",
            "failure_reason": "provider_timeout",
            "failure_message": str(exc),
            "raw_content": "",
            "parsed_json": {},
            "elapsed_ms": timeout_seconds * 1000,
            "http_status": None,
            "parse_error": "TimeoutError",
        }
    except Exception as exc:
        probe = {
            "status": "provider_unavailable",
            "failure_reason": type(exc).__name__,
            "failure_message": str(exc),
            "raw_content": "",
            "parsed_json": {},
            "elapsed_ms": 0,
            "http_status": None,
            "parse_error": type(exc).__name__,
        }
    metadata = _with_context_diagnostics(_provider_status_metadata(provider, probe, health), context_diagnostics)
    raw_probe_text = str(probe.get("raw_content") or probe.get("raw_response_preview") or "")
    raw_text = _clean_text(raw_probe_text)
    finish_reason = _clean_text(probe.get("finish_reason")).lower()
    status = _clean_text(probe.get("failure_reason") or probe.get("status")).lower()
    if finish_reason == "length":
        metadata.update(
            {
                "phi_status": "truncated_response",
                "fallback_used": False,
                "fallback_reason": "Optional AI enrichment response was truncated before completion.",
            }
        )
    elif status == "success":
        metadata.update({"phi_status": "success", "fallback_used": False, "fallback_reason": ""})
    elif raw_probe_text and _feature_ai_reasoning_looks_useful(raw_probe_text):
        metadata.update(
            {
                "phi_status": "success",
                "fallback_used": False,
                "fallback_reason": "",
                "feature_analysis_enrichment_format": "plain_text_sections",
            }
        )
    else:
        metadata.update(
            {
                "phi_status": status or "unusable_response",
                "fallback_used": False,
                "fallback_reason": probe.get("failure_message") or "Optional AI enrichment did not return usable reasoning.",
            }
        )
    if _should_persist_feature_generation_failure(context_diagnostics, probe) and not _feature_ai_reasoning_looks_useful(raw_probe_text):
        metadata.update(
            _persist_feature_generation_failure(
                prompt=prompt,
                probe=probe,
                context_diagnostics=context_diagnostics,
                provider=provider,
                expected_keys=["plain_text_feature_analysis_enrichment"],
            )
        )
    return metadata


def _run_story_analysis_ai_enrichment(
    story: dict[str, Any],
    deterministic: dict[str, Any],
    profile: dict[str, Any],
    options: dict[str, Any],
) -> dict[str, Any]:
    provider = options.get("llm_provider") or options.get("provider")
    if not hasattr(provider, "probe_json"):
        provider = get_refinement_provider()
    context_diagnostics = {
        "operation": "refine_story",
        "story_analysis_enrichment": True,
        "provider_prompt_mode": "plain_text_reasoning",
    }
    if provider is None or not provider.is_enabled():
        metadata = _fallback_metadata("deterministic_story_analysis", "Azure Phi provider is not configured for optional Story Analysis enrichment.")
        metadata.update({"phi_status": "provider_unavailable", "fallback_used": False})
        return _with_context_diagnostics(metadata, context_diagnostics)
    health = provider.health_snapshot() if hasattr(provider, "health_snapshot") else {}
    prompt = _story_analysis_plain_text_prompt(story, deterministic, profile)
    prompt_tokens = _estimate_tokens(prompt)
    context_diagnostics.update(
        {
            "context_size": prompt_tokens,
            "context_after_compression": prompt_tokens,
            "tokens_sent": prompt_tokens,
            "final_prompt_tokens": prompt_tokens,
            "largest_context_sections": [{"section": "story_analysis_context", "tokens": prompt_tokens}],
            "compression_ratio": 1,
            "retry_attempt": 1,
        }
    )
    timeout_seconds = int(options.get("timeout_seconds") or os.getenv("AI_GEN_STORY_ANALYSIS_PROVIDER_TIMEOUT_SECONDS", os.getenv("AI_GEN_REFINER_TIMEOUT_SECONDS", "60")))
    max_tokens = int(options.get("max_tokens") or os.getenv("AI_GEN_STORY_ANALYSIS_MAX_TOKENS", "650"))
    try:
        probe = probe_json_with_budget(
            provider,
            _story_analysis_enrichment_sections(prompt),
            operation="refine_story",
            system_prompt=STORY_ANALYSIS_ENRICHMENT_SYSTEM_PROMPT,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
            response_format_enabled=False,
            allow_retry_without_response_format=False,
        )
        probe_status = _clean_text(probe.get("failure_reason") or probe.get("status")).lower()
        if probe_status == "prompt_too_long":
            context_diagnostics["retry_attempt"] = 2
            probe = probe_json_with_budget(
                provider,
                _story_analysis_enrichment_sections(prompt),
                operation="refine_story",
                system_prompt=STORY_ANALYSIS_ENRICHMENT_SYSTEM_PROMPT,
                max_tokens=max(250, int(max_tokens * 0.75)),
                timeout_seconds=timeout_seconds,
                response_format_enabled=False,
                allow_retry_without_response_format=False,
            )
    except TimeoutError as exc:
        probe = {
            "status": "timeout",
            "failure_reason": "provider_timeout",
            "failure_message": str(exc),
            "raw_content": "",
            "parsed_json": {},
            "elapsed_ms": timeout_seconds * 1000,
            "http_status": None,
            "parse_error": "TimeoutError",
        }
    except Exception as exc:
        probe = {
            "status": "provider_unavailable",
            "failure_reason": type(exc).__name__,
            "failure_message": str(exc),
            "raw_content": "",
            "parsed_json": {},
            "elapsed_ms": 0,
            "http_status": None,
            "parse_error": type(exc).__name__,
        }
    metadata = _with_context_diagnostics(_provider_status_metadata(provider, probe, health), context_diagnostics)
    raw_probe_text = str(probe.get("raw_content") or probe.get("raw_response_preview") or "")
    raw_text = _clean_text(raw_probe_text)
    finish_reason = _clean_text(probe.get("finish_reason")).lower()
    status = _clean_text(probe.get("failure_reason") or probe.get("status")).lower()
    if finish_reason == "length":
        metadata.update(
            {
                "phi_status": "truncated_response",
                "fallback_used": False,
                "fallback_reason": "Optional AI enrichment response was truncated before completion.",
            }
        )
    elif status == "success":
        metadata.update({"phi_status": "success", "fallback_used": False, "fallback_reason": ""})
    elif raw_probe_text and _story_ai_reasoning_looks_useful(raw_probe_text):
        metadata.update(
            {
                "phi_status": "success",
                "fallback_used": False,
                "fallback_reason": "",
                "story_analysis_enrichment_format": "plain_text_sections",
            }
        )
    elif raw_text:
        metadata.update(
            {
                "phi_status": "parse_error" if "parse" in status or "json" in status else status or "unusable_response",
                "fallback_used": False,
                "fallback_reason": probe.get("failure_message") or "Optional AI enrichment did not return usable reasoning.",
            }
        )
    else:
        metadata.update(
            {
                "phi_status": status or "unusable_response",
                "fallback_used": False,
                "fallback_reason": probe.get("failure_message") or "Optional AI enrichment did not return usable reasoning.",
            }
        )
    if _should_persist_feature_generation_failure(context_diagnostics, probe) and not _story_ai_reasoning_looks_useful(raw_probe_text):
        metadata.update(
            _persist_feature_generation_failure(
                prompt=prompt,
                probe=probe,
                context_diagnostics=context_diagnostics,
                provider=provider,
                expected_keys=["plain_text_story_analysis_enrichment"],
            )
        )
    return metadata


FEATURE_ANALYSIS_ENRICHMENT_SYSTEM_PROMPT = (
    "You are an engineering planning reviewer. Return concise plain text only. "
    "Do not return JSON. Do not explain the input format. Do not mention missing template fields. "
    "Write user-facing planning language, not backend implementation channels."
)


STORY_ANALYSIS_ENRICHMENT_SYSTEM_PROMPT = (
    "You are a Scrum Master and engineering planning reviewer. Return concise plain text only. "
    "Do not return JSON. Do not explain the input format. Do not mention missing template fields. "
    "Write story planning language, not backend implementation channels."
)


def _feature_analysis_enrichment_sections(prompt: str) -> list[PromptSection]:
    return [
        _prompt_budget_section("role", "Role", 100, True, False, "role", "Engineering planning reviewer"),
        _prompt_budget_section("objective", "Objective", 100, True, False, "objective", "Enrich a deterministic Feature Analysis draft with concise planning observations."),
        _prompt_budget_section("feature_analysis_context", "Feature Analysis Context", 100, True, True, "feature_analysis", prompt),
        _prompt_budget_section(
            "instructions",
            "Instructions",
            100,
            True,
            False,
            "instructions",
            "Return concise plain text bullets only. Use persona and capability language. Do not explain the input format. Do not invent modules, flows, dependencies, repository files, or backend channels.",
        ),
    ]


def _story_analysis_enrichment_sections(prompt: str) -> list[PromptSection]:
    return [
        _prompt_budget_section("role", "Role", 100, True, False, "role", "Scrum Master and engineering planning reviewer"),
        _prompt_budget_section("objective", "Objective", 100, True, False, "objective", "Enrich a deterministic Story Analysis draft with concise implementation planning observations."),
        _prompt_budget_section("story_analysis_context", "Story Analysis Context", 100, True, True, "story_analysis", prompt),
        _prompt_budget_section(
            "instructions",
            "Instructions",
            100,
            True,
            False,
            "instructions",
            "Return concise plain text bullets only. Use story, acceptance, task, and validation language. Do not explain the input format. Do not invent modules, flows, dependencies, repository files, or backend channels.",
        ),
    ]


def _feature_analysis_plain_text_prompt(feature: dict[str, Any], deterministic: dict[str, Any], profile: dict[str, Any]) -> str:
    dna = deterministic.get("work_item_dna") if isinstance(deterministic.get("work_item_dna"), dict) else {}
    registry = profile.get("knowledge_registry") if isinstance(profile.get("knowledge_registry"), dict) else {}
    relevance_text = _feature_analysis_relevance_text(feature, deterministic)
    modules = _feature_analysis_relevant_names(
        _string_list(deterministic.get("affected_modules")) or _string_list(registry.get("modules"))[:4],
        relevance_text,
    )
    flows = _feature_analysis_relevant_names(
        _string_list(deterministic.get("affected_flows")) or _string_list(registry.get("flows"))[:4],
        relevance_text,
    )
    stories = [
        _clean_text(story.get("title"))
        for story in deterministic.get("recommended_stories", [])
        if isinstance(story, dict) and _clean_text(story.get("title"))
    ][:8]
    lines = [
        "Feature Analysis AI Enrichment",
        "",
        f"Feature: {_clean_text(feature.get('title')) or 'Untitled feature'}",
        f"Description: {_truncate_text(_clean_text(feature.get('description') or deterministic.get('feature_summary')), 500)}",
        f"Capability: {_clean_text(dna.get('capability') or feature.get('capability') or feature.get('title'))}",
        f"Responsibilities: {', '.join(_string_list(dna.get('responsibilities'))[:6]) or 'Not specified'}",
        f"In scope: {', '.join(_string_list(deterministic.get('in_scope')) or _string_list(dna.get('inScope'))[:6]) or 'Use the feature boundary only'}",
        f"Modules: {', '.join(modules[:6])}",
        f"Flows: {', '.join(flows[:6])}",
        f"Dependencies: {', '.join(_string_list(deterministic.get('dependencies'))[:6]) or 'No dependencies identified'}",
        f"Current story candidates: {', '.join(stories) or 'No stories generated yet'}",
        "",
        "Enrich these sections in concise bullets:",
        "1. User journeys",
        "2. Acceptance themes",
        "3. Story candidates",
        "4. Risks and edge cases",
        "",
        "Rules:",
        "- Return exactly the four numbered sections above.",
        "- Use only the feature, modules, flows, and dependencies listed above.",
        "- Do not introduce unrelated modules or flows.",
        "- Write user journeys as user actions, not APIs, services, dashboards, or implementation channels.",
        "- Do not start story candidates with vague verbs such as Use.",
        "- Do not explain that fields are missing.",
        "- Keep the answer under 250 words.",
    ]
    return "\n".join(lines)


def _story_analysis_plain_text_prompt(story: dict[str, Any], deterministic: dict[str, Any], profile: dict[str, Any]) -> str:
    registry = profile.get("knowledge_registry") if isinstance(profile.get("knowledge_registry"), dict) else {}
    modules = _string_list(deterministic.get("affected_modules")) or _string_list(registry.get("modules"))[:3]
    flows = _string_list(deterministic.get("affected_flows")) or _string_list(registry.get("flows"))[:3]
    tasks = [
        _clean_text(task.get("title"))
        for task in deterministic.get("proposed_tasks", [])
        if isinstance(task, dict) and _clean_text(task.get("title"))
    ][:8]
    acceptance = _string_list(deterministic.get("acceptance_criteria"))[:8]
    lines = [
        "Story Analysis AI Enrichment",
        "",
        f"Story: {_clean_text(story.get('title')) or 'Untitled story'}",
        f"Description: {_truncate_text(_clean_text(story.get('description') or deterministic.get('story_summary')), 450)}",
        f"Acceptance criteria: {'; '.join(acceptance) or 'Not specified'}",
        f"Modules: {', '.join(modules[:5])}",
        f"Flows: {', '.join(flows[:5])}",
        f"Dependencies: {', '.join(_string_list(deterministic.get('dependencies'))[:5]) or 'No dependencies identified'}",
        f"Current task candidates: {', '.join(tasks) or 'No tasks generated yet'}",
        "",
        "Enrich these sections in concise bullets:",
        "1. Implementation areas",
        "2. Acceptance mapping",
        "3. Task candidates",
        "4. Risks and edge cases",
        "",
        "Rules:",
        "- Return exactly the four numbered sections above.",
        "- Use only the story, modules, flows, dependencies, and acceptance criteria listed above.",
        "- Do not introduce unrelated modules or flows.",
        "- Do not invent repository files.",
        "- Write task candidates as engineering work areas, not generic Design/Implement/Test placeholders.",
        "- Do not explain that fields are missing.",
        "- Keep the answer under 220 words.",
    ]
    return "\n".join(lines)


def _feature_analysis_relevance_text(feature: dict[str, Any], deterministic: dict[str, Any]) -> str:
    parts = [
        feature.get("title"),
        feature.get("description"),
        deterministic.get("feature_summary"),
    ]
    dna = deterministic.get("work_item_dna") if isinstance(deterministic.get("work_item_dna"), dict) else {}
    parts.extend(_string_list(dna.get("businessGoals")))
    parts.extend(_string_list(dna.get("responsibilities")))
    for story in deterministic.get("recommended_stories", []):
        if isinstance(story, dict):
            parts.extend([story.get("title"), story.get("description")])
            parts.extend(_string_list(story.get("acceptance_criteria")))
    return " ".join(_clean_text(part).lower() for part in parts if _clean_text(part))


def _feature_analysis_relevant_names(names: list[str], relevance_text: str) -> list[str]:
    selected: list[str] = []
    for name in names:
        text = _clean_text(name)
        if not text or _feature_analysis_blocked_context_reason(text, relevance_text):
            continue
        if _feature_analysis_name_matches(text, relevance_text):
            selected.append(text)
    return selected or [_clean_text(name) for name in names[:2] if _clean_text(name) and not _feature_analysis_blocked_context_reason(name, relevance_text)]


def _feature_analysis_name_matches(name: str, relevance_text: str) -> bool:
    tokens = [
        token
        for token in _feature_analysis_token_set(name)
        if token not in {"flow", "review", "platform", "application", "app", "api", "service", "management"}
    ]
    if any(token in relevance_text for token in tokens):
        return True
    normalized = name.lower()
    if "device health" in normalized and any(token in relevance_text for token in ["fault", "event", "device", "outage"]):
        return True
    if "telemetry" in normalized and any(token in relevance_text for token in ["fault", "event", "device", "health", "outage"]):
        return True
    return False


def _feature_analysis_token_set(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z][a-z0-9]{2,}", value.lower())}


def _feature_analysis_blocked_context_reason(name: str, relevance_text: str) -> str:
    normalized = name.lower()
    if any(token in normalized for token in ["login", "token", "auth", "session"]) and not any(
        token in relevance_text for token in ["login", "token", "auth", "session", "credential", "password"]
    ):
        return "authentication context is not relevant to this feature intent"
    if "firmware" in normalized and not any(
        token in relevance_text for token in ["firmware", "rollout", "upgrade", "version", "rollback", "compliance"]
    ):
        return "firmware context is not relevant to this feature intent"
    if any(token in normalized for token in ["analytics", "reporting", "dashboard", "metrics", "kpi"]) and not any(
        token in relevance_text for token in ["analytics", "report", "reporting", "dashboard", "trend", "metric", "kpi"]
    ):
        return "analytics/reporting context is not relevant to this feature intent"
    return ""


def _sanitize_feature_ai_reasoning(text: str, feature: dict[str, Any], deterministic: dict[str, Any]) -> str:
    relevance_text = _feature_analysis_relevance_text(feature, deterministic)
    sanitized: list[str] = []
    for line in text.splitlines():
        lowered = line.lower()
        leaked = False
        for candidate in ["Login Flow", "Token Refresh", "Authentication", "Analytics Platform", "Analytics", "Firmware Update", "Firmware Management"]:
            if candidate.lower() in lowered and _feature_analysis_blocked_context_reason(candidate, relevance_text):
                leaked = True
                break
        if not leaked:
            normalized = _normalize_feature_ai_reasoning_line(line)
            if normalized:
                sanitized.append(normalized)
    return "\n".join(sanitized).strip()


def _parse_feature_ai_enrichment_sections(text: str) -> dict[str, list[str]]:
    sections = {
        "userJourneys": [],
        "acceptanceThemes": [],
        "storyCandidates": [],
        "risksAndEdgeCases": [],
    }
    aliases = {
        "user journeys": "userJourneys",
        "acceptance themes": "acceptanceThemes",
        "story candidates": "storyCandidates",
        "story candidates to add or improve": "storyCandidates",
        "risks and edge cases": "risksAndEdgeCases",
    }
    current = ""
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading_match = re.match(r"^\s*(?:#{1,4}\s*)?(?:\d+[.)]\s*)?([A-Za-z][A-Za-z\s]+?)\s*:?\s*$", line)
        if heading_match:
            label = heading_match.group(1).strip().lower()
            if label in aliases:
                current = aliases[label]
                continue
        if not current:
            continue
        item = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
        item = item.strip("\"' ")
        if item:
            sections[current].append(item)
    return {key: _unique(values) for key, values in sections.items()}


def _parse_story_ai_enrichment_sections(text: str) -> dict[str, list[str]]:
    sections = {
        "implementationAreas": [],
        "acceptanceMapping": [],
        "taskCandidates": [],
        "risksAndEdgeCases": [],
    }
    aliases = {
        "implementation areas": "implementationAreas",
        "acceptance mapping": "acceptanceMapping",
        "task candidates": "taskCandidates",
        "task candidates to add or improve": "taskCandidates",
        "risks and edge cases": "risksAndEdgeCases",
    }
    current = ""
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading_match = re.match(r"^\s*(?:#{1,4}\s*)?(?:\d+[.)]\s*)?([A-Za-z][A-Za-z\s]+?)\s*:?\s*$", line)
        if heading_match:
            label = heading_match.group(1).strip().lower()
            if label in aliases:
                current = aliases[label]
                continue
        if not current:
            continue
        item = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip().strip("\"' ")
        if item:
            sections[current].append(_normalize_feature_ai_reasoning_line(item))
    return {key: _unique([item for item in values if item]) for key, values in sections.items()}


def _normalize_feature_ai_reasoning_line(line: str) -> str:
    text = str(line or "").strip()
    if not text:
        return ""
    bullet = ""
    if text.startswith(("-", "*")):
        bullet = text[:1]
        text = text[1:].strip()
    text = re.sub(r"\bvia Backend API\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bthrough Backend API\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\band Backend API\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bBackend API\b", "service behavior", text, flags=re.IGNORECASE)
    text = re.sub(r"\bOperations Dashboard\s*\(API\)\b", "operations view", text, flags=re.IGNORECASE)
    text = re.sub(r"\bOperations Dashboard\b", "operations view", text, flags=re.IGNORECASE)
    text = re.sub(r"\bMobile\b", "mobile experience", text)
    text = re.sub(r"\bUse see newly arrived events\b", "Review newly arrived fault events", text, flags=re.IGNORECASE)
    text = re.sub(r"\busing see newly arrived events\b", "reviewing newly arrived fault events", text, flags=re.IGNORECASE)
    text = re.sub(r"\breviewing view event details\b", "reviewing event details", text, flags=re.IGNORECASE)
    text = re.sub(r"\bUse review\b", "Review", text, flags=re.IGNORECASE)
    text = re.sub(r"\bUse classify\b", "Classify", text, flags=re.IGNORECASE)
    text = re.sub(r"\bView detect fault\b", "Detect and view faults", text, flags=re.IGNORECASE)
    text = re.sub(r"\bUser searches\b", "Operations user searches", text)
    text = re.sub(r"\bUser reviews\b", "Operations user reviews", text)
    text = re.sub(r"\bUser accesses\b", "Operations user accesses", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" ,")
    text = re.sub(r"\s+([.!?:;])", r"\1", text)
    if bullet and text:
        return f"{bullet} {text}"
    return text


def _feature_ai_reasoning_looks_useful(text: str) -> bool:
    normalized = text.lower()
    if not normalized.strip():
        return False
    template_markers = [
        "json-like structure",
        "empty or null values",
        "placeholder for future data",
        "please provide the relevant details",
        "if you need assistance",
    ]
    if any(marker in normalized for marker in template_markers):
        return False
    parsed = _parse_feature_ai_enrichment_sections(text)
    return any(parsed.values())


def _story_ai_reasoning_looks_useful(text: str) -> bool:
    normalized = text.lower()
    if not normalized.strip():
        return False
    template_markers = [
        "json-like structure",
        "empty or null values",
        "placeholder for future data",
        "please provide the relevant details",
        "if you need assistance",
    ]
    if any(marker in normalized for marker in template_markers):
        return False
    parsed = _parse_story_ai_enrichment_sections(text)
    return any(parsed.values())


def _story_analysis_pipeline_error(
    story: dict[str, Any],
    profile: dict[str, Any],
    existing_children: list[dict[str, Any]] | None,
    status: str,
    exc: Exception,
) -> dict[str, Any]:
    repository_snapshot = _repository_snapshot_from_profile(profile)
    knowledge_registry = profile.get("knowledge_registry") if isinstance(profile.get("knowledge_registry"), dict) else {}
    intent = build_intent(story)
    capability_context = buildCapabilityContext(
        intent,
        {
            "parent_work_item": story,
            "project_profile": profile,
            "repository_snapshot": repository_snapshot,
            "knowledge_registry": knowledge_registry,
        },
    )
    planning_context = buildPlanningContext(
        story,
        story,
        {
            "intentModel": intent,
            "capabilityContext": capability_context,
            "projectProfile": profile,
            "repositorySnapshot": repository_snapshot,
            "knowledgeRegistry": knowledge_registry,
            "existingChildren": existing_children or [],
        },
    )
    metadata = _fallback_metadata("deterministic_story_analysis", "Story analysis returned a deterministic draft because AI enrichment failed.")
    metadata.update(
        {
            "provider_used": "deterministic_story_analysis",
            "source": "deterministic_story_analysis",
            "phi_status": status,
            "fallback_used": False,
            "fallback_reason": f"Optional AI enrichment failed: {exc}",
            "story_analysis_ai_status": status,
            "raw_response_preview": str(exc)[:1200],
        }
    )
    return {
        "intent": intent,
        "capabilityContext": capability_context,
        "planningContext": planning_context,
        "reasoning": {"diagnostics": {"providerUsed": "deterministic_story_analysis"}, "artifacts": []},
        "artifacts": [],
        "genericArtifacts": [],
        "validationReports": [],
        "previewPolicy": {"status": "NeedsReview", "allow_create": False, "allow_save": True, "allow_manual_edit": True, "block_creation": False},
        "providerMetadata": metadata,
        "providerParsed": {},
    }


def _feature_analysis_pipeline_error(
    feature: dict[str, Any],
    profile: dict[str, Any],
    existing_children: list[dict[str, Any]] | None,
    status: str,
    exc: Exception,
) -> dict[str, Any]:
    repository_snapshot = _repository_snapshot_from_profile(profile)
    knowledge_registry = profile.get("knowledge_registry") if isinstance(profile.get("knowledge_registry"), dict) else {}
    intent = build_intent(feature)
    capability_context = buildCapabilityContext(
        intent,
        {
            "parent_work_item": feature,
            "project_profile": profile,
            "repository_snapshot": repository_snapshot,
            "knowledge_registry": knowledge_registry,
        },
    )
    planning_context = buildPlanningContext(
        feature,
        feature,
        {
            "intentModel": intent,
            "capabilityContext": capability_context,
            "projectProfile": profile,
            "repositorySnapshot": repository_snapshot,
            "knowledgeRegistry": knowledge_registry,
            "existingChildren": existing_children or [],
        },
    )
    metadata = _fallback_metadata("deterministic_feature_analysis", "Feature analysis returned a deterministic draft because AI enrichment failed.")
    metadata.update(
        {
            "provider_used": "deterministic_feature_analysis",
            "source": "deterministic_feature_analysis",
            "phi_status": status,
            "fallback_used": False,
            "fallback_reason": f"Optional AI enrichment failed: {exc}",
            "feature_analysis_ai_status": status,
            "raw_response_preview": str(exc)[:1200],
        }
    )
    return {
        "intent": intent,
        "capabilityContext": capability_context,
        "planningContext": planning_context,
        "reasoning": {"diagnostics": {"providerUsed": "deterministic_feature_analysis"}, "artifacts": []},
        "artifacts": [],
        "genericArtifacts": [],
        "validationReports": [],
        "previewPolicy": {"status": "NeedsReview", "allow_create": False, "allow_save": True, "allow_manual_edit": True, "block_creation": False},
        "providerMetadata": metadata,
        "providerParsed": {},
    }


def _feature_analysis_provider_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(metadata or {})
    sanitized.pop("error", None)
    sanitized.pop("message", None)
    phi_status = _clean_text(sanitized.get("phi_status")).lower()
    if phi_status and phi_status not in {"success", "not_required", "skipped"}:
        sanitized["fallback_used"] = False
        sanitized.setdefault("fallback_reason", "Optional AI enrichment did not return usable output.")
    return sanitized


def _story_analysis_provider_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(metadata or {})
    sanitized.pop("error", None)
    sanitized.pop("message", None)
    phi_status = _clean_text(sanitized.get("phi_status")).lower()
    if phi_status == "required_sections_exceed_budget":
        sanitized["phi_status"] = "blocked_by_budget_guard"
        sanitized.setdefault("prompt_too_long_stage", "before_provider_call")
        largest_section = (
            sanitized.get("largest_section")
            or sanitized.get("largestSection")
            or sanitized.get("largestRequiredSection")
            or sanitized.get("largest_required_section")
            or "required_sections"
        )
        fallback_reason = _clean_text(sanitized.get("fallback_reason"))
        if "largest section" not in fallback_reason.lower():
            sanitized["fallback_reason"] = f"{fallback_reason} Largest section: {largest_section}".strip()
        phi_status = "blocked_by_budget_guard"
    if phi_status and phi_status not in {"success", "not_required", "skipped"}:
        sanitized["fallback_used"] = False
        sanitized.setdefault("fallback_reason", "Optional AI enrichment did not return usable output.")
    return sanitized


def _feature_analysis_ai_status(metadata: dict[str, Any], ai_requested: bool) -> str:
    phi_status = _clean_text(metadata.get("phi_status")).lower()
    fallback_reason = _clean_text(metadata.get("fallback_reason")).lower()
    if not ai_requested:
        return "not_requested"
    if phi_status == "success":
        return "success"
    if phi_status == "plain_text_response":
        return "plain_text_response"
    if phi_status in {"truncated_response", "length"} or "truncated" in fallback_reason:
        return "truncated_response"
    if "timeout" in phi_status or "timeout" in fallback_reason or phi_status == "provider_timeout":
        return "timeout"
    if "parse" in phi_status or "json" in fallback_reason or "normalized" in fallback_reason or phi_status in {"unusable_response", "invalid_json"}:
        return "parse_error"
    if phi_status in {"missing_config", "provider_unavailable", "connection_error"}:
        return "provider_unavailable"
    return "provider_unavailable" if not phi_status else "parse_error"


def _story_analysis_ai_status(metadata: dict[str, Any], ai_requested: bool) -> str:
    return _feature_analysis_ai_status(metadata, ai_requested)


def _feature_analysis_validation_status(dna_validation: dict[str, Any], recommended_stories: list[dict[str, Any]], ai_status: str) -> str:
    if not bool(dna_validation.get("valid", True)):
        return "Blocked"
    if not recommended_stories:
        return "NeedsReview"
    if ai_status in {"timeout", "parse_error", "provider_unavailable", "truncated_response"}:
        return "NeedsReview"
    return "Ready"


def _story_analysis_validation_status(dna_validation: dict[str, Any], proposed_tasks: list[dict[str, Any]], ai_status: str) -> str:
    if not bool(dna_validation.get("valid", True)):
        return "Blocked"
    if not proposed_tasks:
        return "NeedsReview"
    if ai_status in {"timeout", "parse_error", "provider_unavailable", "truncated_response"}:
        return "NeedsReview"
    return "Ready"


def _feature_analysis_payload(
    feature: dict[str, Any],
    deterministic: dict[str, Any],
    provider_metadata: dict[str, Any],
    modules: list[str],
    flows: list[str],
    selection: dict[str, Any],
    dna_validation: dict[str, Any],
    *,
    ai_requested: bool,
) -> dict[str, Any]:
    recommended_stories = [story for story in deterministic.get("recommended_stories", []) if isinstance(story, dict)]
    ai_status = _feature_analysis_ai_status(provider_metadata, ai_requested)
    validation_status = _feature_analysis_validation_status(dna_validation, recommended_stories, ai_status)
    dna = deterministic.get("work_item_dna") if isinstance(deterministic.get("work_item_dna"), dict) else {}
    scope = dna.get("scope") if isinstance(dna.get("scope"), dict) else {}
    draft = {
        "featureId": _item_id(feature, "feature"),
        "title": _clean_text(feature.get("title")) or _clean_text(dna.get("title")) or "Untitled feature",
        "summary": deterministic.get("feature_summary"),
        "capability": _clean_text(dna.get("capability") or dna.get("primaryCapability") or feature.get("capability") or feature.get("title")),
        "responsibilities": _string_list(dna.get("responsibilities")) or _string_list(feature.get("responsibilities")),
        "inScope": _string_list(scope.get("in_scope") if isinstance(scope, dict) else None) or _string_list(dna.get("inScope")) or _string_list(feature.get("in_scope")),
        "outOfScope": _string_list(scope.get("out_of_scope") if isinstance(scope, dict) else None) or _string_list(dna.get("outOfScope")) or _string_list(feature.get("out_of_scope")),
        "dependencies": _string_list(deterministic.get("dependencies")),
        "repositoryEvidence": {
            "modules": modules,
            "flows": flows,
            "dependencies": _selection_names(selection, "relevant_dependencies"),
            "rejectedContext": deterministic.get("rejected_context") or deterministic.get("rejected_irrelevant_context") or [],
        },
        "knowledgeReferences": {
            "modules": modules,
            "flows": flows,
            "applications": _selection_names(selection, "relevant_applications"),
        },
        "validationSummary": {
            "dnaValid": bool(dna_validation.get("valid", True)),
            "dnaStatus": dna_validation.get("status") or ("Ready" if dna_validation.get("valid", True) else "Blocked"),
            "issues": _string_list(dna_validation.get("issues")),
        },
        "storyCandidates": [
            {
                "title": story.get("title"),
                "description": story.get("description"),
                "acceptanceCriteria": _string_list(story.get("acceptance_criteria")),
                "confidence": story.get("confidence"),
            }
            for story in recommended_stories
        ],
        "risks": _string_list(deterministic.get("risks")),
    }
    ai_enrichment = None
    raw_reasoning = _sanitize_feature_ai_reasoning(
        str(provider_metadata.get("raw_response_preview") or provider_metadata.get("phi_raw_response_preview") or ""),
        feature,
        deterministic,
    )
    warnings: list[str] = []
    if raw_reasoning and ai_status in {"success", "truncated_response"}:
        parsed_enrichment = _parse_feature_ai_enrichment_sections(raw_reasoning)
        deterministic_journeys = deterministic.get("story_analysis", {}).get("userJourneys", []) if isinstance(deterministic.get("story_analysis"), dict) else []
        deterministic_themes = deterministic.get("story_generation_diagnostics", {}).get("story_coverage_areas", []) if isinstance(deterministic.get("story_generation_diagnostics"), dict) else []
        ai_enrichment = {
            "userJourneys": parsed_enrichment.get("userJourneys") or deterministic_journeys,
            "acceptanceThemes": parsed_enrichment.get("acceptanceThemes") or deterministic_themes,
            "storyCandidates": parsed_enrichment.get("storyCandidates") or draft["storyCandidates"],
            "risksAndEdgeCases": parsed_enrichment.get("risksAndEdgeCases") or draft["risks"],
            "aiReasoningText": raw_reasoning,
            "source": "azure_phi",
            "format": "plain_text_sections",
        }
    if ai_status in {"timeout", "parse_error", "provider_unavailable", "truncated_response"}:
        warnings.append("Feature analysis is available. AI enrichment failed and can be retried.")
    result = {
        "featureId": draft["featureId"],
        "deterministicDraft": draft,
        "aiEnrichment": ai_enrichment,
        "aiStatus": ai_status,
        "validationStatus": validation_status,
        "diagnostics": {
            "providerTimeoutMs": int(os.getenv("AI_GEN_FEATURE_ANALYSIS_PROVIDER_TIMEOUT_SECONDS", os.getenv("AI_GEN_REFINER_TIMEOUT_SECONDS", "60"))) * 1000,
            "providerMetadata": provider_metadata,
            "rawResponsePreview": provider_metadata.get("raw_response_preview") or provider_metadata.get("phi_raw_response_preview") or "",
            "parseError": provider_metadata.get("parse_error") or (provider_metadata.get("fallback_reason") if ai_status == "parse_error" else ""),
            "deterministicDraftReady": True,
            "storyCandidateCount": len(recommended_stories),
            "selectedModules": modules,
            "selectedFlows": flows,
        },
        "warnings": warnings,
    }
    return {
        "feature_analysis_result": result,
        "featureAnalysisResult": result,
        "deterministic_draft": draft,
        "ai_status": ai_status,
        "validation_status": validation_status,
        "feature_analysis_diagnostics": result["diagnostics"],
        "warnings": warnings,
    }


def _story_analysis_payload(
    story: dict[str, Any],
    deterministic: dict[str, Any],
    provider_metadata: dict[str, Any],
    modules: list[str],
    flows: list[str],
    selection: dict[str, Any],
    dna_validation: dict[str, Any],
    *,
    ai_requested: bool,
) -> dict[str, Any]:
    proposed_tasks = [task for task in deterministic.get("proposed_tasks", []) if isinstance(task, dict)]
    ai_status = _story_analysis_ai_status(provider_metadata, ai_requested)
    validation_status = _story_analysis_validation_status(dna_validation, proposed_tasks, ai_status)
    dna = deterministic.get("work_item_dna") if isinstance(deterministic.get("work_item_dna"), dict) else {}
    draft = {
        "storyId": _item_id(story, "story"),
        "title": _clean_text(story.get("title")) or _clean_text(dna.get("title")) or "Untitled story",
        "summary": deterministic.get("story_summary"),
        "userStory": deterministic.get("story_summary"),
        "acceptanceCriteria": _string_list(deterministic.get("acceptance_criteria")),
        "affectedModules": modules,
        "affectedFlows": flows,
        "dependencies": _string_list(deterministic.get("dependencies")),
        "repositoryEvidence": {
            "modules": modules,
            "flows": flows,
            "dependencies": _selection_names(selection, "relevant_dependencies"),
            "rejectedContext": deterministic.get("rejected_context") or deterministic.get("rejected_irrelevant_context") or [],
        },
        "taskCandidates": [
            {
                "title": task.get("title"),
                "description": task.get("description"),
                "workArea": task.get("work_area"),
                "acceptanceCriteria": _string_list(task.get("acceptance_criteria")),
                "confidence": task.get("confidence"),
            }
            for task in proposed_tasks
        ],
        "implementationAreas": _unique([_clean_text(task.get("work_area")) for task in proposed_tasks if _clean_text(task.get("work_area"))]),
        "risks": _string_list(deterministic.get("risks")),
    }
    ai_enrichment = None
    raw_reasoning = str(provider_metadata.get("raw_response_preview") or provider_metadata.get("phi_raw_response_preview") or "").strip()
    warnings: list[str] = []
    if raw_reasoning and ai_status in {"success", "truncated_response"}:
        parsed_enrichment = _parse_story_ai_enrichment_sections(raw_reasoning)
        ai_enrichment = {
            "implementationAreas": parsed_enrichment.get("implementationAreas") or draft["implementationAreas"],
            "acceptanceMapping": parsed_enrichment.get("acceptanceMapping") or draft["acceptanceCriteria"],
            "taskCandidates": parsed_enrichment.get("taskCandidates") or [task["title"] for task in draft["taskCandidates"] if task.get("title")],
            "risksAndEdgeCases": parsed_enrichment.get("risksAndEdgeCases") or draft["risks"],
            "aiReasoningText": raw_reasoning,
            "source": "azure_phi",
            "format": "plain_text_sections",
        }
    if ai_status in {"timeout", "parse_error", "provider_unavailable", "truncated_response"}:
        warnings.append("Story analysis is available. AI enrichment failed and can be retried.")
    result = {
        "storyId": draft["storyId"],
        "deterministicDraft": draft,
        "aiEnrichment": ai_enrichment,
        "aiStatus": ai_status,
        "validationStatus": validation_status,
        "diagnostics": {
            "providerTimeoutMs": int(os.getenv("AI_GEN_STORY_ANALYSIS_PROVIDER_TIMEOUT_SECONDS", os.getenv("AI_GEN_REFINER_TIMEOUT_SECONDS", "60"))) * 1000,
            "providerMetadata": provider_metadata,
            "rawResponsePreview": provider_metadata.get("raw_response_preview") or provider_metadata.get("phi_raw_response_preview") or "",
            "parseError": provider_metadata.get("parse_error") or (provider_metadata.get("fallback_reason") if ai_status == "parse_error" else ""),
            "deterministicDraftReady": True,
            "taskCandidateCount": len(proposed_tasks),
            "selectedModules": modules,
            "selectedFlows": flows,
        },
        "warnings": warnings,
    }
    return {
        "story_analysis_result": result,
        "storyAnalysisResult": result,
        "deterministic_draft": draft,
        "ai_status": ai_status,
        "validation_status": validation_status,
        "story_analysis_diagnostics": result["diagnostics"],
        "warnings": warnings,
    }


def _run_epic_feature_pipeline(
    epic: dict[str, Any],
    features: list[dict[str, Any]],
    profile: dict[str, Any],
    existing_children: list[dict[str, Any]] | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    options = options or {}
    repository_snapshot = _repository_snapshot_from_profile(profile)
    knowledge_registry = profile.get("knowledge_registry") if isinstance(profile.get("knowledge_registry"), dict) else {}
    epic_analysis = options.get("epic_analysis") if isinstance(options.get("epic_analysis"), dict) else {}
    provider_metadata = options.get("provider_metadata") if isinstance(options.get("provider_metadata"), dict) else {}
    provider_parsed = options.get("provider_parsed") if isinstance(options.get("provider_parsed"), dict) else {}
    validation_reports: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    contexts_by_title: dict[str, dict[str, Any]] = {}
    first_context: dict[str, Any] | None = None
    for feature in features:
        capability = _clean_text(feature.get("capability_category") or feature.get("capability") or feature.get("title"))
        capability_work_item = {
            "id": f"{_item_id(epic, 'epic')}::{capability}",
            "type": "Feature",
            "title": _clean_text(feature.get("title")) or capability,
            "description": _clean_text(feature.get("description")),
            "acceptanceCriteria": _string_list(feature.get("acceptance_criteria")),
        }
        capability_context = buildCapabilityContext(
            {
                **build_intent(capability_work_item),
                "primaryCapability": capability,
                "secondaryCapabilities": [],
            },
            {
                "parent_work_item": epic,
                "project_profile": profile,
                "repository_snapshot": repository_snapshot,
                "knowledge_registry": knowledge_registry,
            },
        )
        planning_context = buildPlanningContext(
            capability_work_item,
            epic,
            {
                "intentModel": {
                    **build_intent(capability_work_item),
                    "primaryCapability": capability,
                    "secondaryCapabilities": [],
                },
                "capabilityContext": capability_context,
                "projectProfile": profile,
                "repositorySnapshot": repository_snapshot,
                "knowledgeRegistry": knowledge_registry,
                "existingChildren": existing_children or [],
                "objective": "Generate one feature from one approved Epic Analysis capability.",
            },
        )
        first_context = first_context or planning_context
        contexts_by_title[_clean_text(feature.get("title")).lower()] = planning_context
        artifact = _item_to_planning_artifact(feature, "Feature", planning_context)
        report = validateArtifact(
            planning_context,
            artifact,
            {
                "repositorySnapshot": repository_snapshot,
                "knowledgeRegistry": knowledge_registry,
                "existingSiblings": existing_children or [],
            },
        )
        validation_reports.append(report)
        artifacts.append(
            {
                **artifact,
                "validationReport": report,
                "validationStatus": report["validationStatus"],
                "creationAllowed": report["validationStatus"] == "Approved",
                "manualEditAllowed": report["validationStatus"] == "NeedsReview",
                "creationBlocked": report["validationStatus"] == "Rejected",
            }
        )
    fallback_context = first_context or buildPlanningContext(
        epic,
        epic,
        {
            "projectProfile": profile,
            "repositorySnapshot": repository_snapshot,
            "knowledgeRegistry": knowledge_registry,
            "existingChildren": existing_children or [],
            "objective": "Analyze epic before feature generation.",
        },
    )
    return {
        "intent": build_intent(epic),
        "capabilityContext": {"source": "epic_analysis", "requiredCapabilities": epic_analysis.get("requiredCapabilities", [])},
        "planningContext": fallback_context,
        "featurePlanningContexts": contexts_by_title,
        "reasoning": {
            "diagnostics": {
                "providerUsed": "epic_analysis_intelligence",
                "featureGenerationMode": "one_capability_at_a_time",
                "capabilityCount": len(features),
            },
            "artifacts": artifacts,
        },
        "artifacts": artifacts,
        "validationReports": validation_reports,
        "previewPolicy": _preview_policy(validation_reports),
        "providerMetadata": provider_metadata or {
            "provider_used": "epic_analysis_intelligence",
            "source": "epic_analysis_intelligence",
            "phi_status": "not_required",
            "fallback_used": False,
            "fallback_reason": "",
            "epic_analysis_confidence": epic_analysis.get("confidence"),
        },
        "providerParsed": provider_parsed,
    }


def _planning_llm_provider(options: dict[str, Any]) -> Any:
    provider = options.get("llm_provider") or options.get("provider")
    if hasattr(provider, "generate_json"):
        return provider
    force_provider = _clean_text(options.get("force_provider"))
    if bool(options.get("deterministic_only")) or force_provider in {"deterministic_fallback", "domain_fallback"}:
        return None
    return _ProjectPlanningPhiProvider(options)


class _ProjectPlanningPhiProvider:
    def __init__(self, options: dict[str, Any]) -> None:
        self.options = dict(options)
        self.metadata: dict[str, Any] = {}
        self.last_result: dict[str, Any] = {}
        self.parsed: dict[str, Any] = {}

    def generate_json(self, prompt: str, output_type: str) -> dict[str, Any]:
        probe_options = dict(self.options)
        probe_options.setdefault("allow_fallback", False)
        probe_options.setdefault("max_tokens", 900)
        probe_options.setdefault("operation", _planning_operation_for_output_type(output_type))
        expected_keys = [
            "artifacts",
            "planningArtifacts",
            "title",
            "description",
            "businessValue",
            "acceptanceCriteria",
            "business_goal",
            "recommended_features",
            "recommended_stories",
            "proposed_tasks",
        ]
        result: dict[str, Any] = {}
        for _attempt in range(2):
            result = _project_phi_probe(prompt, probe_options, expected_keys=expected_keys)
            metadata = result.get("metadata", {})
            if metadata.get("phi_status") != "prompt_too_long":
                break
        self.last_result = result
        self.metadata = result.get("metadata", {})
        self.parsed = result.get("parsed", {}) if result.get("used") else {}
        return _planning_provider_payload(self.parsed, output_type)


def _planning_provider_payload(parsed: dict[str, Any], output_type: str) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        return {}
    if isinstance(parsed.get("artifacts"), list) or isinstance(parsed.get("planningArtifacts"), list):
        return parsed
    normalized = _clean_text(output_type).lower()
    if normalized.startswith("feature") and isinstance(parsed.get("recommended_features"), list):
        return {"artifacts": parsed["recommended_features"]}
    if normalized.startswith("story") and isinstance(parsed.get("recommended_stories"), list):
        return {"artifacts": parsed["recommended_stories"]}
    if normalized.startswith("task") and isinstance(parsed.get("proposed_tasks"), list):
        return {"artifacts": parsed["proposed_tasks"]}
    return parsed


def _planning_operation_for_output_type(output_type: str) -> str:
    normalized = _clean_text(output_type).lower()
    if normalized.startswith("feature"):
        return "generate_features"
    if normalized.startswith("story"):
        return "refine_feature"
    if normalized.startswith("task"):
        return "generate_tasks"
    return "refine_epic"


def _append_rejected_phi_feature_diagnostics(payload: dict[str, Any], provider_parsed: dict[str, Any], epic_title: str) -> None:
    features = provider_parsed.get("recommended_features") if isinstance(provider_parsed, dict) else []
    if not isinstance(features, list):
        return
    diagnostics = payload.setdefault("capability_diagnostics", {})
    rejected = diagnostics.setdefault("rejected_similar_features", [])
    existing_titles = {_clean_text(item.get("title")).lower() for item in rejected if isinstance(item, dict)}
    epic_tokens = set(_simple_keywords(epic_title))
    for feature in features:
        if not isinstance(feature, dict):
            continue
        title = _clean_text(feature.get("title"))
        if not title or title.lower() in existing_titles:
            continue
        title_tokens = set(_simple_keywords(title))
        is_too_close = bool(title_tokens and epic_tokens and len(title_tokens & epic_tokens) / max(1, len(title_tokens)) >= 0.5)
        is_generic_dashboard = "dashboard" in title.lower() and "dashboard" in epic_title.lower()
        if is_too_close or is_generic_dashboard:
            rejected.append(
                {
                    "title": title,
                    "reason": "phi suggestion overlapped the epic title or generic UI framing",
                    "similarity": round(len(title_tokens & epic_tokens) / max(1, len(title_tokens)), 2) if title_tokens else 0,
                }
            )


def _simple_keywords(value: Any) -> list[str]:
    text = _clean_text(value).lower()
    token = ""
    output: list[str] = []
    for char in text:
        if char.isalnum():
            token += char
            continue
        if len(token) > 2 and token not in output:
            output.append(token)
        token = ""
    if len(token) > 2 and token not in output:
        output.append(token)
    return output


def _existing_children_from_options(options: dict[str, Any] | None) -> list[dict[str, Any]]:
    options = options or {}
    children = options.get("existing_children") or options.get("existingChildren") or options.get("existing_children_preview") or []
    return [item for item in children if isinstance(item, dict)] if isinstance(children, list) else []


def _preview_policy(validation_reports: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = [_clean_text(report.get("validationStatus")) for report in validation_reports if isinstance(report, dict)]
    if statuses and all(status == "Approved" for status in statuses):
        return {
            "status": "Approved",
            "allow_create": True,
            "allow_save": True,
            "allow_manual_edit": False,
            "block_creation": False,
            "message": "Validation approved. Create and save actions are available.",
        }
    if any(status == "Rejected" for status in statuses):
        return {
            "status": "Rejected",
            "allow_create": False,
            "allow_save": False,
            "allow_manual_edit": True,
            "block_creation": True,
            "message": "Validation rejected this output. Fix issues before creating or saving.",
        }
    return {
        "status": "NeedsReview",
        "allow_create": False,
        "allow_save": False,
        "allow_manual_edit": True,
        "block_creation": False,
        "message": "Validation needs review. Edit warnings before creating or saving.",
    }


def _repository_snapshot_from_profile(profile: dict[str, Any]) -> dict[str, Any]:
    registry = profile.get("knowledge_registry") if isinstance(profile.get("knowledge_registry"), dict) else {}
    readme = profile.get("readme_analysis") if isinstance(profile.get("readme_analysis"), dict) else {}
    return {
        "knowledge_registry": registry,
        "modules": [
            {"name": name, "keywords": _context_keywords(name, "", profile)}
            for name in _string_list(registry.get("modules")) or _string_list(readme.get("modules"))
        ],
        "flows": _string_list(registry.get("flows")) or _string_list(readme.get("flows")),
        "dependencies": _string_list(registry.get("dependencies")),
        "rankedFiles": _repository_ranked_files(profile),
        "source_files": _string_list(registry.get("source_files")) or _string_list(profile.get("repository_sources")),
    }


def _repository_ranked_files(profile: dict[str, Any]) -> list[dict[str, Any]]:
    registry = profile.get("knowledge_registry") if isinstance(profile.get("knowledge_registry"), dict) else {}
    files = _string_list(registry.get("ranked_files")) or _string_list(registry.get("source_files")) or _string_list(profile.get("repository_sources"))
    return [{"path": path, "score": 0.5} for path in files[:12]]


def _artifact_to_generated_item(artifact: dict[str, Any], item_type: str, parent: dict[str, Any], parent_type: str) -> dict[str, Any]:
    evidence = artifact.get("generatedUsing") if isinstance(artifact.get("generatedUsing"), dict) else {}
    return {
        "id": _draft_id(item_type, artifact.get("title")),
        "type": item_type,
        "title": _clean_text(artifact.get("title")) or item_type,
        "description": _clean_text(artifact.get("description")),
        "business_value": _clean_text(artifact.get("businessValue")),
        "acceptance_criteria": _string_list(artifact.get("acceptanceCriteria")),
        "personas": _string_list(artifact.get("personas")),
        "dependencies": _string_list(artifact.get("dependencies")),
        "risks": _string_list(artifact.get("risks")),
        "assumptions": _string_list(artifact.get("assumptions")),
        "parent_id": _item_id(parent),
        "parent_type": parent_type,
        "derived_from": "intelligence_pipeline",
        "source_intent": _string_list((artifact.get("generatedUsing") or {}).get("capabilities") if isinstance(artifact.get("generatedUsing"), dict) else []),
        "selected_modules": _string_list(evidence.get("modules")),
        "selected_flows": _string_list(evidence.get("flows")),
        "rejected_context": [],
        "confidence": float(artifact.get("confidence") or 0.0),
        "validation_report": artifact.get("validationReport"),
        "validation_status": _clean_text(artifact.get("validationStatus")),
        "creation_allowed": bool(artifact.get("creationAllowed")),
        "manual_edit_allowed": bool(artifact.get("manualEditAllowed")),
        "creation_blocked": bool(artifact.get("creationBlocked")),
        "status": "preview",
    }


def _generic_artifacts_from_pipeline(artifacts: list[dict[str, Any]], parent: dict[str, Any], output_type: str) -> list[dict[str, Any]]:
    engine = ArtifactEngine()
    artifact_type = _generic_artifact_type(output_type)
    output: list[dict[str, Any]] = []
    parent_id = _item_id(parent)
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        source = {
            "id": item.get("id"),
            "parentId": parent_id,
            "title": item.get("title"),
            "description": item.get("description"),
            "businessGoal": item.get("businessGoal"),
            "businessValue": item.get("businessValue"),
            "repositoryEvidence": (item.get("generatedUsing") or {}).get("modules") if isinstance(item.get("generatedUsing"), dict) else [],
            "knowledgeReferences": (item.get("generatedUsing") or {}).get("flows") if isinstance(item.get("generatedUsing"), dict) else [],
            "dependencies": item.get("dependencies"),
            "responsibilities": item.get("personas"),
            "acceptanceThemes": item.get("acceptanceCriteria"),
            "dna": item.get("work_item_dna") or item.get("dna"),
            "validation": item.get("validationReport"),
            "confidence": item.get("confidence"),
        }
        artifact = engine.create(artifact_type, source, {"parentId": parent_id})
        artifact = engine.analyze(artifact, {"parentId": parent_id})
        artifact = engine.generate(artifact, {"parentId": parent_id})
        artifact = engine.validate(artifact, {"parentId": parent_id})
        artifact = engine.build_dna(artifact, {"parentId": parent_id})
        artifact = engine.version(artifact)
        output.append(artifact)
    return output


def _generic_artifact_type(output_type: str) -> str:
    normalized = _clean_text(output_type).lower()
    if normalized.startswith("feature"):
        return "Feature"
    if normalized.startswith("story"):
        return "Story"
    if normalized.startswith("task"):
        return "Task"
    if normalized.startswith("execution"):
        return "Execution Package"
    return "Epic"


def _draft_id(item_type: str, title: Any) -> str:
    item_slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in (_clean_text(item_type) or "item")).strip("_") or "item"
    seed = f"{item_slug}|{_clean_text(title)}"
    return f"draft_{item_slug}_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:10]}"


def _pipeline_payload(pipeline: dict[str, Any]) -> dict[str, Any]:
    return {
        "intelligence_pipeline": {
            "intent": pipeline["intent"],
            "capability_context": pipeline["capabilityContext"],
            "planning_context": pipeline["planningContext"],
            "reasoning_diagnostics": pipeline["reasoning"].get("diagnostics", {}),
            "validation_reports": pipeline["validationReports"],
            "preview_policy": pipeline["previewPolicy"],
            "provider_metadata": pipeline.get("providerMetadata", {}),
            "provider_parsed": pipeline.get("providerParsed", {}),
            "generic_artifacts": pipeline.get("genericArtifacts", []),
        },
        "validation_reports": pipeline["validationReports"],
        "preview_policy": pipeline["previewPolicy"],
    }


def _pipeline_context_capsule(
    *,
    capsule_type: str,
    source_work_item: dict[str, Any],
    parent_story: dict[str, Any],
    acceptance_criteria: list[str],
    pipeline: dict[str, Any],
    profile: dict[str, Any],
    cache: dict[str, Any] | None,
    selected_task: dict[str, Any] | None = None,
    work_item_dna: dict[str, Any] | None = None,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    planning_context = pipeline.get("planningContext") if isinstance(pipeline.get("planningContext"), dict) else {}
    capability_context = pipeline.get("capabilityContext") if isinstance(pipeline.get("capabilityContext"), dict) else {}
    intent = pipeline.get("intent") if isinstance(pipeline.get("intent"), dict) else {}
    validation_reports = [report for report in pipeline.get("validationReports", []) if isinstance(report, dict)]
    dna_evidence = work_item_dna.get("repositoryEvidence") if isinstance(work_item_dna, dict) and isinstance(work_item_dna.get("repositoryEvidence"), dict) else {}
    dna_boundary = work_item_dna.get("planningBoundary") if isinstance(work_item_dna, dict) and isinstance(work_item_dna.get("planningBoundary"), dict) else {}
    repository_snapshot = _repository_snapshot_from_profile(profile)
    knowledge_version = _clean_text((cache or {}).get("knowledge_version")) or _knowledge_version(profile)
    repository_snapshot_version = _repository_snapshot_version(repository_snapshot, profile)
    selected_modules = _string_list(dna_evidence.get("modules")) or _names_from_context(planning_context.get("selectedModules"))
    selected_flows = _string_list(dna_evidence.get("flows")) or _names_from_context(planning_context.get("selectedFlows"))
    selected_applications = _string_list(dna_evidence.get("applications")) or _names_from_context(planning_context.get("selectedApplications")) or _application_names(profile)[:3]
    selected_dependencies = _unique(
        [
            *_string_list(work_item_dna.get("dependencies") if isinstance(work_item_dna, dict) else []),
            *_names_from_context(planning_context.get("selectedDependencies")),
            *_string_list(source_work_item.get("dependencies")),
            *_string_list(parent_story.get("dependencies")),
        ]
    )
    selected_standards = _string_list(work_item_dna.get("engineeringStandards") if isinstance(work_item_dna, dict) else []) or _names_from_context(planning_context.get("selectedStandards"))
    selected_capabilities = _string_list(work_item_dna.get("capability") if isinstance(work_item_dna, dict) else "") or _names_from_context(planning_context.get("selectedCapabilities")) or _names_from_context(capability_context.get("selectedCapabilities"))
    repository_capsule = RepositoryContextCapsuleBuilder().build_capsule(
        story={
            "id": _item_id(source_work_item),
            "title": _clean_text(source_work_item.get("title")) or _clean_text(parent_story.get("title")),
            "description": _clean_text(source_work_item.get("description")) or _clean_text(parent_story.get("description")),
            "acceptance_criteria": acceptance_criteria,
        },
        repository_snapshot={
            **repository_snapshot,
            "metadata": {
                **(repository_snapshot.get("metadata") if isinstance(repository_snapshot.get("metadata"), dict) else {}),
                "architectureNotes": _string_list(profile.get("knowledge_registry", {}).get("architecture_notes") if isinstance(profile.get("knowledge_registry"), dict) else []),
            },
        },
        engineering_graph=profile.get("engineering_graph") if isinstance(profile.get("engineering_graph"), dict) else {},
        repository_ranking=(profile.get("knowledge_registry", {}).get("ranked_files") if isinstance(profile.get("knowledge_registry"), dict) else [])
        or (profile.get("knowledge_registry", {}).get("repository_file_ranking") if isinstance(profile.get("knowledge_registry"), dict) else [])
        or profile.get("repository_file_ranking")
        or [],
        selected_modules=selected_modules,
        selected_flows=selected_flows,
    ).to_dict()
    relevant_files = repository_capsule.get("relevantFiles") if isinstance(repository_capsule.get("relevantFiles"), list) else _ranked_relevant_files(profile, selected_modules, selected_flows, source_work_item)
    file_ranking_status = "Repository file ranking available" if relevant_files else "Repository file ranking not available"
    repository_dependencies = [
        _clean_text(item.get("name") or item.get("path") or item.get("title"))
        for item in list(repository_capsule.get("dependencies") or [])
        if isinstance(item, dict)
    ]
    selected_dependencies = _unique([*selected_dependencies, *repository_dependencies])
    rejected_context = _capsule_rejected_context(planning_context)
    story_keywords = _context_keywords(_clean_text(parent_story.get("title")), _clean_text(parent_story.get("description")), profile)
    risks = _unique(
        [
            *_string_list(work_item_dna.get("risks") if isinstance(work_item_dna, dict) else []),
            *_string_list(planning_context.get("risks")),
            *_string_list(source_work_item.get("risks")),
            *_risks_for_profile(profile, story_keywords),
            *_string_list(repository_capsule.get("risks")),
            *[
                _clean_text(issue.get("message") or issue.get("reason") or issue.get("title"))
                for report in validation_reports
                for issue in (report.get("issues") if isinstance(report.get("issues"), list) else [])
                if isinstance(issue, dict)
            ],
        ]
    )[:10]
    constraints = _unique([*_string_list(work_item_dna.get("constraints") if isinstance(work_item_dna, dict) else []), *_string_list(planning_context.get("constraints"))])[:10]
    capsule_acceptance = acceptance_criteria or _string_list(work_item_dna.get("acceptanceThemes") if isinstance(work_item_dna, dict) else [])
    source_payload = {
        "capsule_type": capsule_type,
        "work_item_dna": work_item_dna or {},
        "source_work_item": _compact_work_item(source_work_item),
        "parent_story": _compact_work_item(parent_story),
        "selected_task": _compact_work_item(selected_task or {}),
        "acceptance_criteria": capsule_acceptance,
        "planning_context_version": planning_context.get("planningContextVersion") or planning_context.get("version"),
        "selected_modules": selected_modules,
        "selected_flows": selected_flows,
        "selected_dependencies": selected_dependencies,
        "knowledge_version": knowledge_version,
        "repository_snapshot_version": repository_snapshot_version,
        "knowledge_registry": profile.get("knowledge_registry", {}),
        "repository_snapshot": repository_snapshot,
    }
    source_hash = hashlib.sha256(json.dumps(source_payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    previous_version = int((previous or {}).get("version") or 0)
    generated_at = _now_iso()
    payload = {
        "capsuleId": f"{capsule_type}_{source_hash[:12]}",
        "capsuleType": capsule_type,
        "sourceWorkItemId": _item_id(source_work_item),
        "parentStoryId": _item_id(parent_story),
        "knowledgeVersion": knowledge_version,
        "repositorySnapshotVersion": repository_snapshot_version,
        "generatedAt": generated_at,
        "projectName": _clean_text(profile.get("project_name")),
        "domain": _clean_text(profile.get("domain") or profile.get("knowledge_profile_preview", {}).get("domain") if isinstance(profile.get("knowledge_profile_preview"), dict) else profile.get("domain")),
        "projectType": _clean_text(profile.get("project_type")),
        "intentSummary": _intent_summary(intent, planning_context),
        "selectedCapabilities": selected_capabilities,
        "selectedModules": selected_modules,
        "selectedFlows": selected_flows,
        "selectedApplications": selected_applications,
        "selectedDependencies": selected_dependencies,
        "selectedStandards": selected_standards,
        "acceptanceCriteria": capsule_acceptance[:8],
        "inScope": _string_list(dna_boundary.get("inScope")),
        "outOfScope": _string_list(dna_boundary.get("outOfScope")),
        "relevantFiles": relevant_files,
        "relevantAPIs": repository_capsule.get("relevantAPIs") if isinstance(repository_capsule.get("relevantAPIs"), list) else [],
        "architectureRules": _string_list(repository_capsule.get("architectureRules")),
        "suggestedTests": repository_capsule.get("suggestedTests") if isinstance(repository_capsule.get("suggestedTests"), list) else [],
        "moduleContext": repository_capsule.get("moduleContext") if isinstance(repository_capsule.get("moduleContext"), list) else [],
        "graphReferences": repository_capsule.get("graphReferences") if isinstance(repository_capsule.get("graphReferences"), list) else [],
        "fileRankingStatus": file_ranking_status,
        "rejectedContext": rejected_context,
        "risks": risks,
        "constraints": constraints,
        "confidence": round(float(planning_context.get("confidence") or 0.72), 2),
        "freshnessStatus": "fresh",
    }
    if work_item_dna:
        payload["workItemDNA"] = work_item_dna
        payload["dnaId"] = work_item_dna.get("dnaId")
        payload["dnaVersion"] = work_item_dna.get("version")
    payload["tokenEstimate"] = _estimate_tokens(json.dumps(payload, ensure_ascii=True, separators=(",", ":"), default=str))
    source_size = _estimate_tokens(json.dumps(source_payload, ensure_ascii=True, separators=(",", ":"), default=str))
    capsule = {
        "capsule_id": payload["capsuleId"],
        "capsule_type": capsule_type,
        "status": "ready",
        "version": previous_version + 1 if (previous or {}).get("source_hash") != source_hash else previous_version or 1,
        "created_at": generated_at,
        "last_refreshed": generated_at,
        "source_hash": source_hash,
        "source_version": knowledge_version,
        "knowledge_version": knowledge_version,
        "repository_snapshot_version": repository_snapshot_version,
        "freshness_status": payload["freshnessStatus"],
        "dependencies": ["work_item_dna", "work_item", "parent_story", "planning_context", "knowledge_registry", "repository_snapshot"],
        "parent_references": _capsule_parent_references(parent_story),
        "payload": {
            **payload,
            "modules": selected_modules,
            "flows": selected_flows,
            "applications": selected_applications,
            "standards": selected_standards,
            "dependencies": selected_dependencies,
            "architecture_summary": _truncate_text(_architecture_summary_text(profile, profile.get("knowledge_registry", {})), 260),
        },
        "diagnostics": {
            "capsule_size_tokens": payload["tokenEstimate"],
            "source_size_tokens": source_size,
            "compression_ratio": round(payload["tokenEstimate"] / max(source_size, 1), 3),
            "selected_modules": selected_modules,
            "selected_flows": selected_flows,
            "selected_files": [_clean_text(item.get("path")) for item in relevant_files if isinstance(item, dict)],
            "selected_apis": [_clean_text(item.get("name")) for item in payload["relevantAPIs"] if isinstance(item, dict)],
            "architecture_rules": payload["architectureRules"],
            "rejected_context": rejected_context,
            "confidence": payload["confidence"],
            "freshness_status": payload["freshnessStatus"],
            "dna_id": (work_item_dna or {}).get("dnaId"),
            "dna_version": (work_item_dna or {}).get("version"),
            "repository_capsule": repository_capsule.get("diagnostics") if isinstance(repository_capsule.get("diagnostics"), dict) else {},
        },
    }
    return capsule


def _capsule_public_payload(capsule: dict[str, Any]) -> dict[str, Any]:
    payload = capsule.get("payload") if isinstance(capsule.get("payload"), dict) else {}
    return {
        "capsuleId": payload.get("capsuleId") or capsule.get("capsule_id"),
        "capsuleType": payload.get("capsuleType") or capsule.get("capsule_type"),
        "sourceWorkItemId": payload.get("sourceWorkItemId"),
        "parentStoryId": payload.get("parentStoryId"),
        "knowledgeVersion": payload.get("knowledgeVersion") or capsule.get("knowledge_version"),
        "repositorySnapshotVersion": payload.get("repositorySnapshotVersion") or capsule.get("repository_snapshot_version"),
        "generatedAt": payload.get("generatedAt") or capsule.get("created_at"),
        "projectName": _clean_text(payload.get("projectName")),
        "domain": _clean_text(payload.get("domain")),
        "projectType": _clean_text(payload.get("projectType")),
        "intentSummary": payload.get("intentSummary"),
        "selectedCapabilities": _string_list(payload.get("selectedCapabilities")),
        "selectedModules": _string_list(payload.get("selectedModules") or payload.get("modules")),
        "selectedFlows": _string_list(payload.get("selectedFlows") or payload.get("flows")),
        "selectedApplications": _string_list(payload.get("selectedApplications") or payload.get("applications")),
        "selectedDependencies": _string_list(payload.get("selectedDependencies") or payload.get("dependencies")),
        "selectedStandards": _string_list(payload.get("selectedStandards") or payload.get("standards")),
        "acceptanceCriteria": _string_list(payload.get("acceptanceCriteria")),
        "inScope": _string_list(payload.get("inScope")),
        "outOfScope": _string_list(payload.get("outOfScope")),
        "relevantFiles": payload.get("relevantFiles") if isinstance(payload.get("relevantFiles"), list) else [],
        "relevantAPIs": payload.get("relevantAPIs") if isinstance(payload.get("relevantAPIs"), list) else [],
        "architectureRules": _string_list(payload.get("architectureRules")),
        "suggestedTests": payload.get("suggestedTests") if isinstance(payload.get("suggestedTests"), list) else [],
        "moduleContext": payload.get("moduleContext") if isinstance(payload.get("moduleContext"), list) else [],
        "graphReferences": payload.get("graphReferences") if isinstance(payload.get("graphReferences"), list) else [],
        "fileRankingStatus": _clean_text(payload.get("fileRankingStatus")) or "Repository file ranking not available",
        "rejectedContext": payload.get("rejectedContext") if isinstance(payload.get("rejectedContext"), list) else [],
        "risks": _string_list(payload.get("risks")),
        "constraints": _string_list(payload.get("constraints")),
        "confidence": float(payload.get("confidence") or 0),
        "tokenEstimate": int(payload.get("tokenEstimate") or 0),
        "freshnessStatus": _clean_text(payload.get("freshnessStatus") or capsule.get("freshness_status")) or "unknown",
        "workItemDNA": payload.get("workItemDNA") if isinstance(payload.get("workItemDNA"), dict) else {},
        "dnaId": payload.get("dnaId"),
        "dnaVersion": payload.get("dnaVersion"),
    }


def _context_capsule_metadata(capsule: dict[str, Any]) -> dict[str, Any]:
    public = _capsule_public_payload(capsule)
    diagnostics = capsule.get("diagnostics") if isinstance(capsule.get("diagnostics"), dict) else {}
    return {
        "context_capsule_used": True,
        "context_capsule_required": True,
        "capsuleId": public["capsuleId"],
        "capsuleGeneratedAt": public["generatedAt"],
        "knowledgeVersion": public["knowledgeVersion"],
        "repositorySnapshotVersion": public["repositorySnapshotVersion"],
        "selectedModules": public["selectedModules"],
        "selectedFlows": public["selectedFlows"],
        "selectedFiles": [_clean_text(item.get("path")) for item in public["relevantFiles"] if isinstance(item, dict)],
        "selectedAPIs": [_clean_text(item.get("name")) for item in public["relevantAPIs"] if isinstance(item, dict)],
        "rejectedContext": public["rejectedContext"],
        "tokenEstimate": public["tokenEstimate"],
        "confidence": public["confidence"],
        "freshnessStatus": public["freshnessStatus"],
        "dnaId": public.get("dnaId"),
        "dnaVersion": public.get("dnaVersion"),
        "context_capsule_type": capsule.get("capsule_type"),
        "context_capsule_version": capsule.get("version"),
        "context_capsule_size_tokens": diagnostics.get("capsule_size_tokens", public["tokenEstimate"]),
        "context_capsule_source_size_tokens": diagnostics.get("source_size_tokens", 0),
        "context_capsule_compression_ratio": diagnostics.get("compression_ratio", 0),
    }


def _execution_package_from_capsule(
    *,
    story: dict[str, Any],
    selected_task: dict[str, Any],
    acceptance_criteria: list[str],
    context_capsule: dict[str, Any],
    generated_tasks: list[dict[str, Any]],
    task_plan: dict[str, Any],
    readiness: dict[str, Any],
    profile: dict[str, Any],
    validation_report: dict[str, Any] | None,
) -> dict[str, Any]:
    capsule = _capsule_public_payload(context_capsule)
    relevant_files = [item for item in capsule["relevantFiles"] if isinstance(item, dict)]
    relevant_file_paths = [_clean_text(item.get("path")) for item in relevant_files if _clean_text(item.get("path"))]
    work_item_dna = capsule.get("workItemDNA") if isinstance(capsule.get("workItemDNA"), dict) else {}
    modules = capsule["selectedModules"]
    flows = capsule["selectedFlows"]
    dependencies = capsule["selectedDependencies"]
    risks = capsule["risks"]
    implementation_tasks = _tasks_for_areas(generated_tasks, ["UI Work", "Frontend Work", "Backend Work", "Data Work", "Analytics Work"])
    testing_tasks = _tasks_for_areas(generated_tasks, ["QA Work"])
    story_title = _clean_text(story.get("title")) or "Untitled story"
    story_description = _clean_text(story.get("description"))
    task_title = _clean_text(selected_task.get("title")) or "Selected execution task"
    artifact_type = "Task" if selected_task else "Story"
    artifact = selected_task if selected_task else story
    artifact_id = _item_id(artifact)
    package = {
        "execution_package_source": "context_capsule",
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "execution_source": {
            "artifactId": artifact_id,
            "artifactType": artifact_type,
            "title": _clean_text(artifact.get("title")),
            "description": _clean_text(artifact.get("description")),
        },
        "context_capsule": capsule,
        "context_capsule_diagnostics": _context_capsule_metadata(context_capsule),
        "work_item_dna": work_item_dna,
        "dna_summary": _dna_summary(work_item_dna),
        "story_summary": _sentence(story_title, story_description),
        "task_focus": task_title if selected_task else story_title,
        "selected_task": selected_task,
        "parent_story": {
            "id": _item_id(story),
            "title": story_title,
            "description": story_description,
            "acceptance_criteria": acceptance_criteria,
        },
        "implementation_boundary": _execution_boundary(task_title, modules, flows),
        "capsule_summary": _capsule_summary(capsule),
        "business_outcome": _clean_text(work_item_dna.get("businessOutcome")) if work_item_dna else "",
        "capability": _clean_text(work_item_dna.get("capability")) if work_item_dna else "",
        "responsibilities": _string_list(work_item_dna.get("responsibilities")) if work_item_dna else [],
        "in_scope": _string_list(capsule.get("inScope")),
        "out_of_scope": _string_list(capsule.get("outOfScope")),
        "acceptance_criteria": acceptance_criteria,
        "affected_applications": capsule["selectedApplications"],
        "affected_modules": modules,
        "affected_flows": flows,
        "dependencies": dependencies,
        "risks": risks,
        "technology_stack": _compact_stack(profile),
        "ui_guidelines": profile["ui_guidelines"],
        "development_standards": profile["development_standards"],
        "relevant_files": relevant_files,
        "recommended_files": relevant_file_paths,
        "file_ranking_status": capsule["fileRankingStatus"],
        "engineering_rules": _engineering_rules_from_capsule(capsule, profile),
        "validation_report": validation_report or {},
        "rejected_context": capsule["rejectedContext"],
        "acceptance_criteria_mapping": _acceptance_criteria_mapping(acceptance_criteria, implementation_tasks),
        "proposed_tasks": generated_tasks,
        "task_intelligence_diagnostics": task_plan.get("diagnostics", {}),
        "implementation_tasks": implementation_tasks,
        "testing_tasks": testing_tasks,
        "documentation_tasks": _documentation_tasks(story_title, profile, {"dependencies": dependencies, "affected_modules": modules, "affected_flows": flows}),
        "implementation_notes": _implementation_notes(profile, {"dependencies": dependencies, "risks": risks}),
        "execution_readiness": readiness["label"],
        "execution_readiness_score": readiness["score"],
        "execution_readiness_breakdown": readiness["breakdown"],
        "execution_readiness_result": readiness["result"],
        "ai_enrichment_status": "not_requested",
    }
    package["execution_package_v2"] = build_execution_package_v2(
        story=story,
        selected_task=selected_task,
        acceptance_criteria=acceptance_criteria,
        context_capsule=capsule,
        generated_tasks=generated_tasks,
        task_plan=task_plan,
        readiness=readiness,
        profile=profile,
        validation_report=validation_report,
    )
    package["executionPackageV2"] = package["execution_package_v2"]
    package["execution_package_version"] = "v2"
    return package


def _dna_summary(dna: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(dna, dict) or not dna:
        return {}
    evidence = dna.get("repositoryEvidence") if isinstance(dna.get("repositoryEvidence"), dict) else {}
    validation = dna.get("validationSummary") if isinstance(dna.get("validationSummary"), dict) else {}
    return {
        "dnaId": dna.get("dnaId"),
        "version": dna.get("version"),
        "workItemType": dna.get("workItemType"),
        "parentDNA": dna.get("parentDNA"),
        "businessGoals": _string_list(dna.get("businessGoals")),
        "businessOutcome": _clean_text(dna.get("businessOutcome")),
        "capability": _clean_text(dna.get("capability")),
        "responsibilities": _string_list(dna.get("responsibilities")),
        "inScope": _string_list((dna.get("planningBoundary") or {}).get("inScope") if isinstance(dna.get("planningBoundary"), dict) else []),
        "outOfScope": _string_list((dna.get("planningBoundary") or {}).get("outOfScope") if isinstance(dna.get("planningBoundary"), dict) else []),
        "modules": _string_list(evidence.get("modules")),
        "flows": _string_list(evidence.get("flows")),
        "files": _string_list(evidence.get("files")),
        "dependencies": _string_list(dna.get("dependencies")),
        "constraints": _string_list(dna.get("constraints")),
        "risks": _string_list(dna.get("risks")),
        "acceptanceThemes": _string_list(dna.get("acceptanceThemes")),
        "validationScore": int(validation.get("score") or 0),
        "validationIssues": _string_list(validation.get("issues")),
        "confidence": round(float(dna.get("confidence") or 0), 3),
        "approved": bool(dna.get("approved")),
    }


def _compact_work_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "id": _item_id(item),
            "type": _clean_text(item.get("type") or item.get("work_item_type")),
            "title": _clean_text(item.get("title")),
            "description": _truncate_text(item.get("description"), 500),
            "acceptance_criteria": _string_list(item.get("acceptance_criteria"))[:8],
            "work_area": _clean_text(item.get("work_area")),
        }.items()
        if value not in ("", [], {}, None)
    }


def _repository_snapshot_version(repository_snapshot: dict[str, Any], profile: dict[str, Any]) -> str:
    payload = {
        "repository": profile.get("repository_connection"),
        "source_files": repository_snapshot.get("source_files"),
        "rankedFiles": repository_snapshot.get("rankedFiles"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def _ranked_relevant_files(profile: dict[str, Any], modules: list[str], flows: list[str], item: dict[str, Any]) -> list[dict[str, Any]]:
    registry = profile.get("knowledge_registry") if isinstance(profile.get("knowledge_registry"), dict) else {}
    ranked = registry.get("ranked_files") or registry.get("repository_file_ranking") or profile.get("repository_file_ranking") or []
    if not isinstance(ranked, list):
        return []
    terms = set(_simple_keywords(" ".join([_clean_text(item.get("title")), _clean_text(item.get("description")), " ".join(modules), " ".join(flows)])))
    files: list[dict[str, Any]] = []
    for entry in ranked:
        if isinstance(entry, str):
            path = _clean_text(entry)
            evidence = path
            base_confidence = 0.55
        elif isinstance(entry, dict):
            path = _clean_text(entry.get("path") or entry.get("file") or entry.get("name"))
            evidence = _clean_text(entry.get("evidence") or entry.get("reason") or entry.get("module") or entry.get("flow") or path)
            base_confidence = float(entry.get("confidence") or entry.get("score") or 0.55)
        else:
            continue
        if not path:
            continue
        haystack = set(_simple_keywords(f"{path} {evidence}"))
        overlap = len(terms & haystack)
        if terms and not overlap and len(files) >= 3:
            continue
        confidence = min(0.98, max(base_confidence, 0.5 + overlap * 0.08))
        files.append(
            {
                "path": path,
                "confidence": round(confidence, 2),
                "reason": evidence or "Ranked by Repository Intelligence for the selected context.",
                "evidence": evidence or path,
                "source": "repository_intelligence",
            }
        )
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in sorted(files, key=lambda value: float(value.get("confidence") or 0), reverse=True):
        path = _clean_text(entry.get("path"))
        if path and path not in seen:
            seen.add(path)
            deduped.append(entry)
    return deduped[:8]


def _capsule_rejected_context(planning_context: dict[str, Any]) -> list[dict[str, Any]]:
    rejected = planning_context.get("rejectedContext")
    if not isinstance(rejected, list):
        return []
    output: list[dict[str, Any]] = []
    for item in rejected[:12]:
        if isinstance(item, dict):
            output.append(
                {
                    "name": _clean_text(item.get("name") or item.get("title") or item.get("id")),
                    "type": _clean_text(item.get("type")) or "context",
                    "reason": _clean_text(item.get("reason")) or "Rejected by planning context selection.",
                }
            )
        else:
            output.append({"name": _clean_text(item), "type": "context", "reason": "Rejected by planning context selection."})
    names = {_clean_text(item.get("name")) for item in output if isinstance(item, dict)}
    if "Firmware Management" in names and "Firmware Update" not in names:
        output.append(
            {
                "name": "Firmware Update",
                "type": "module",
                "reason": "Rejected with Firmware Management because the selected story/task does not mention firmware rollout, version, upgrade, rollback, or compliance.",
            }
        )
    return [item for item in output if item["name"]]


def _intent_summary(intent: dict[str, Any], planning_context: dict[str, Any]) -> str:
    keywords = _string_list(intent.get("keywords") or intent.get("intent_keywords"))[:8]
    capability = ", ".join(_names_from_context(planning_context.get("selectedCapabilities"))[:3])
    problem = _clean_text(planning_context.get("userProblem"))
    parts = []
    if capability:
        parts.append(f"Capabilities: {capability}")
    if keywords:
        parts.append(f"Intent: {', '.join(keywords)}")
    if problem:
        parts.append(f"Problem: {problem}")
    return ". ".join(parts) or "Execution intent selected from parent story and task."


def _execution_boundary(task_title: str, modules: list[str], flows: list[str]) -> str:
    return _sentence(
        task_title,
        f"Limit changes to {', '.join(modules[:3]) or 'the selected modules'} and {', '.join(flows[:3]) or 'the selected flows'} from the context capsule.",
    )


def _capsule_summary(capsule: dict[str, Any]) -> str:
    return (
        f"Capsule {capsule.get('capsuleId')} uses modules {', '.join(capsule.get('selectedModules') or []) or 'none selected'} "
        f"and flows {', '.join(capsule.get('selectedFlows') or []) or 'none selected'}."
    )


def _engineering_rules_from_capsule(capsule: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    rules = [
        "Use only the modules, flows, dependencies, and files selected in the Context Capsule.",
        "Do not introduce rejected context into implementation scope.",
        "If repository file ranking is unavailable, inspect the repo before changing files.",
    ]
    rules.extend(_string_list(capsule.get("selectedStandards"))[:4])
    if not _string_list(capsule.get("selectedStandards")):
        rules.extend(_flatten_standards(profile.get("development_standards", {}))[:4])
    return _unique(rules)


def _active_capsule_profile_from_execution_package(context: dict[str, Any]) -> dict[str, Any]:
    public = context.get("context_capsule") if isinstance(context.get("context_capsule"), dict) else {}
    diagnostics = context.get("context_capsule_diagnostics") if isinstance(context.get("context_capsule_diagnostics"), dict) else {}
    if not public:
        return {}
    return {
        "_active_context_capsule": {
            "capsule_id": public.get("capsuleId"),
            "capsule_type": public.get("capsuleType") or "execution",
            "version": context.get("context_capsule_version") or 1,
            "source_version": public.get("knowledgeVersion"),
            "knowledge_version": public.get("knowledgeVersion"),
            "repository_snapshot_version": public.get("repositorySnapshotVersion"),
            "payload": {
                **public,
                "project_name": "",
                "domain": "",
                "project_type": "",
                "project_summary": public.get("intentSummary"),
                "modules": _string_list(public.get("selectedModules")),
                "flows": _string_list(public.get("selectedFlows")),
                "applications": _string_list(public.get("selectedApplications")),
                "standards": _string_list(public.get("selectedStandards")),
                "dependencies": _string_list(public.get("selectedDependencies")),
                "dev_context": context.get("implementation_boundary"),
                "ui_context": "; ".join(_string_list(context.get("affected_flows"))[:3]),
                "qa_context": "; ".join(_string_list(context.get("risks"))[:3]),
                "impacted_files": _string_list(context.get("recommended_files")),
            },
            "diagnostics": {
                "capsule_size_tokens": diagnostics.get("tokenEstimate") or public.get("tokenEstimate") or context.get("tokenEstimate") or 0,
                "source_size_tokens": context.get("context_capsule_source_size_tokens") or 0,
                "compression_ratio": context.get("context_capsule_compression_ratio") or 0,
            },
        }
    }


def _execution_package_phi_item(context: dict[str, Any]) -> dict[str, Any]:
    selected_task = context.get("selected_task") if isinstance(context.get("selected_task"), dict) else {}
    execution_source = context.get("execution_source") if isinstance(context.get("execution_source"), dict) else {}
    artifact_type = _clean_text(context.get("artifact_type") or execution_source.get("artifactType")) or ("Task" if selected_task else "Story")
    return {
        "id": _clean_text(selected_task.get("id")) or _clean_text(context.get("artifact_id")) or _clean_text(context.get("sourceWorkItemId")),
        "type": artifact_type,
        "title": _clean_text(selected_task.get("title")) or _clean_text(execution_source.get("title")) or _clean_text(context.get("task_focus")) or "Execution artifact",
        "state": _clean_text(selected_task.get("status")) or "Approved",
    }


def _attach_validation_to_items(items: list[dict[str, Any]], pipeline: dict[str, Any], item_type: str) -> list[dict[str, Any]]:
    planning_context = pipeline.get("planningContext") if isinstance(pipeline.get("planningContext"), dict) else {}
    feature_contexts = pipeline.get("featurePlanningContexts") if isinstance(pipeline.get("featurePlanningContexts"), dict) else {}
    repository_snapshot = _repository_snapshot_from_planning_context(planning_context)
    validated: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_context = feature_contexts.get(_clean_text(item.get("title")).lower()) or planning_context
        artifact = _item_to_planning_artifact(item, item_type, item_context)
        item_repository_snapshot = _repository_snapshot_from_planning_context(item_context) if item_context else repository_snapshot
        report = validateArtifact(item_context, artifact, {"repositorySnapshot": item_repository_snapshot}) if item_context else {}
        status = _clean_text(report.get("validationStatus")) or "NeedsReview"
        validated.append(
            {
                **item,
                "validation_report": report,
                "validation_status": status,
                "creation_allowed": status == "Approved",
                "manual_edit_allowed": status == "NeedsReview",
                "creation_blocked": status == "Rejected",
            }
        )
    return validated


def _repository_snapshot_from_planning_context(planning_context: dict[str, Any]) -> dict[str, Any]:
    return {
        "modules": _names_from_context(planning_context.get("selectedModules")),
        "flows": _names_from_context(planning_context.get("selectedFlows")),
        "dependencies": _names_from_context(planning_context.get("selectedDependencies")),
        "rankedFiles": [],
    }


def _item_to_planning_artifact(item: dict[str, Any], item_type: str, planning_context: dict[str, Any]) -> dict[str, Any]:
    evidence = {
        "planningContextVersion": planning_context.get("planningContextVersion") or planning_context.get("version") or "unknown",
        "capabilities": _names_from_context(planning_context.get("selectedCapabilities")),
        "modules": _string_list(item.get("selected_modules")) or _names_from_context(planning_context.get("selectedModules")),
        "flows": _string_list(item.get("selected_flows")) or _names_from_context(planning_context.get("selectedFlows")),
        "applications": _names_from_context(planning_context.get("selectedApplications")),
        "standards": _names_from_context(planning_context.get("selectedStandards")),
    }
    return {
        "title": _clean_text(item.get("title")) or item_type,
        "description": _clean_text(item.get("description")),
        "businessValue": _clean_text(item.get("business_value") or item.get("businessValue") or item.get("business_goal")) or _clean_text(planning_context.get("expectedOutcome")),
        "acceptanceCriteria": _string_list(item.get("acceptance_criteria") or item.get("acceptanceCriteria")),
        "personas": _string_list(item.get("personas") or item.get("primary_users")) or _names_from_context(planning_context.get("personas")),
        "dependencies": _string_list(item.get("dependencies")),
        "risks": _string_list(item.get("risks")),
        "assumptions": _string_list(item.get("assumptions")),
        "generatedUsing": evidence,
        "confidence": float(item.get("confidence") or planning_context.get("confidence") or 0.75),
        "validationStatus": "Pending",
    }


def _prompt_validation_payload(execution_context: dict[str, Any], title: str, content: str) -> dict[str, Any]:
    pipeline = execution_context.get("intelligence_pipeline") if isinstance(execution_context, dict) else {}
    planning_context = pipeline.get("planning_context") if isinstance(pipeline, dict) else {}
    if not isinstance(planning_context, dict) or not planning_context:
        return {}
    evidence = {
        "planningContextVersion": planning_context.get("planningContextVersion") or planning_context.get("version") or "unknown",
        "capabilities": _names_from_context(planning_context.get("selectedCapabilities")),
        "modules": _names_from_context(planning_context.get("selectedModules")),
        "flows": _names_from_context(planning_context.get("selectedFlows")),
        "applications": _names_from_context(planning_context.get("selectedApplications")),
        "standards": _names_from_context(planning_context.get("selectedStandards")),
    }
    artifact = {
        "title": title,
        "description": _clean_text(content)[:1400],
        "businessValue": planning_context.get("expectedOutcome") or "Execution guidance is ready for developer use.",
        "acceptanceCriteria": _string_list(execution_context.get("acceptance_criteria"))[:6] or ["Prompt covers the approved story scope."],
        "personas": _string_list(planning_context.get("personas")),
        "dependencies": _string_list(execution_context.get("dependencies")),
        "risks": _string_list(execution_context.get("risks")),
        "assumptions": [],
        "generatedUsing": evidence,
        "confidence": 0.82,
        "validationStatus": "Pending",
    }
    report = validateArtifact(planning_context, artifact, {})
    policy = _preview_policy([report])
    return {
        "validation_report": report,
        "validation_reports": [report],
        "validation_status": report["validationStatus"],
        "preview_policy": policy,
        "creation_allowed": bool(policy.get("allow_create")),
        "save_allowed": bool(policy.get("allow_save")),
        "manual_edit_allowed": bool(policy.get("allow_manual_edit")),
        "creation_blocked": bool(policy.get("block_creation")),
    }


def _execution_plan_skill_section(skill_payload: dict[str, Any]) -> str:
    skills = skill_payload.get("skills", []) if isinstance(skill_payload, dict) else []
    composition = skill_payload.get("composition", {}) if isinstance(skill_payload, dict) else {}
    if not skills:
        return ""
    lines = [
        "## Engineering Skills",
        "Apply these reusable HEI engineering skills while executing the task:",
    ]
    for skill in skills[:5]:
        name = str(skill.get("name") or "Engineering Skill").strip()
        category = str(skill.get("category") or "Architecture").strip()
        pattern = str(skill.get("implementationPattern") or skill.get("description") or "").strip()
        lines.append(f"- {name} ({category}): {pattern}")
    validation_rules = [
        str(rule).strip()
        for rule in composition.get("validationRules", [])[:5]
        if str(rule).strip()
    ]
    test_templates = [
        str(test).strip()
        for test in composition.get("testTemplates", [])[:5]
        if str(test).strip()
    ]
    if validation_rules:
        lines.append("")
        lines.append("Skill validation rules:")
        lines.extend(f"- {rule}" for rule in validation_rules)
    if test_templates:
        lines.append("")
        lines.append("Skill test expectations:")
        lines.extend(f"- {test}" for test in test_templates)
    return "\n".join(lines)


def _names_from_context(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value:
        if isinstance(item, dict):
            name = _clean_text(item.get("name") or item.get("title") or item.get("id"))
        else:
            name = _clean_text(item)
        if name and name not in output:
            output.append(name)
    return output


def _normalize_applications(value: Any) -> list[dict[str, str]]:
    if isinstance(value, list):
        apps: list[dict[str, str]] = []
        for item in value:
            if isinstance(item, dict):
                name = _clean_text(item.get("name"))
                app_type = _clean_text(item.get("type")) or _infer_application_type(name)
            else:
                name = _clean_text(item)
                app_type = _infer_application_type(name)
            if name:
                apps.append({"name": name, "type": app_type or "API"})
        return apps
    return []


def _normalize_repository_connection(value: Any) -> dict[str, str]:
    connection = value if isinstance(value, dict) else {}
    return {
        "repository_id": _clean_text(connection.get("repository_id")),
        "repository_name": _clean_text(connection.get("repository_name")),
        "branch": _clean_text(connection.get("branch")),
        "status": _clean_text(connection.get("status")) or "Not connected",
        "readme_path": _clean_text(connection.get("readme_path")) or "/README.md",
    }


def _normalize_connectors(value: Any, repository_connection: dict[str, str] | None = None) -> dict[str, Any]:
    connectors = value if isinstance(value, dict) else {}
    return {
        "azure_devops": _normalize_azure_devops_connector(
            connectors.get("azure_devops") if isinstance(connectors.get("azure_devops"), dict) else {},
            repository_connection,
        )
    }


def _normalize_azure_devops_connector(value: Any, repository_connection: dict[str, str] | None = None) -> dict[str, str]:
    connector = value if isinstance(value, dict) else {}
    repository_connection = repository_connection or {}
    return {
        "organization_url": _clean_text(connector.get("organization_url")) or os.getenv("ADO_ORG_URL", "").rstrip("/"),
        "ado_project": _clean_text(connector.get("ado_project")) or os.getenv("ADO_PROJECT", ""),
        "repository_id": _clean_text(connector.get("repository_id")) or _clean_text(repository_connection.get("repository_id")),
        "repository_name": _clean_text(connector.get("repository_name")) or _clean_text(repository_connection.get("repository_name")),
        "branch": _clean_text(connector.get("branch")) or _clean_text(repository_connection.get("branch")) or "main",
    }


def _repository_connection_from_connector(connector: dict[str, str], current: dict[str, str] | None = None) -> dict[str, str]:
    current = current or {}
    return {
        "repository_id": _clean_text(connector.get("repository_id")) or _clean_text(current.get("repository_id")),
        "repository_name": _clean_text(connector.get("repository_name")) or _clean_text(current.get("repository_name")),
        "branch": _clean_text(connector.get("branch")) or _clean_text(current.get("branch")) or "main",
        "status": _clean_text(current.get("status")) or ("Repository connected" if connector.get("repository_id") else "Not connected"),
        "readme_path": _clean_text(current.get("readme_path")) or "/README.md",
    }


def _legacy_azure_devops_connector(repository_connection: dict[str, str] | None = None) -> dict[str, str]:
    return _normalize_azure_devops_connector({}, repository_connection)


def _safe_profile_id(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(value).strip())
    return safe or "default"


def _normalize_project_session(session: dict[str, Any]) -> dict[str, Any]:
    session = session if isinstance(session, dict) else {}
    return {
        "active_project": _clean_text(session.get("active_project")),
        "project_id": _clean_text(session.get("project_id")),
        "auto_route_by_work_item_type": bool(session.get("auto_route_by_work_item_type", True)),
        "approval_workflow": session.get("approval_workflow") if isinstance(session.get("approval_workflow"), dict) else {},
        "knowledge_governance": session.get("knowledge_governance") if isinstance(session.get("knowledge_governance"), dict) else {},
        "last_active_workspace": _clean_text(session.get("last_active_workspace")) or _clean_text(session.get("last_workspace")) or "overview",
        "last_active_tab": _clean_text(session.get("last_active_tab")) or _clean_text(session.get("last_active_workspace")) or "overview",
        "last_work_item_id": session.get("last_work_item_id"),
        "last_work_item_type": _clean_text(session.get("last_work_item_type")),
        "last_work_item_title": _clean_text(session.get("last_work_item_title")),
        "last_repository": _clean_text(session.get("last_repository")) or _clean_text(session.get("repository_name")),
        "last_repository_id": _clean_text(session.get("last_repository_id")) or _clean_text(session.get("repository_id")),
        "last_branch": _clean_text(session.get("last_branch")) or _clean_text(session.get("branch")) or "main",
        "last_analysis_timestamp": _clean_text(session.get("last_analysis_timestamp")),
        "knowledge_version": _clean_text(session.get("knowledge_version")),
        "execution_context": session.get("execution_context") if isinstance(session.get("execution_context"), dict) else {},
        "execution_plan": session.get("execution_plan") if isinstance(session.get("execution_plan"), dict) else {},
        "dev_prompt": session.get("dev_prompt") if isinstance(session.get("dev_prompt"), dict) else {},
        "ui_prompt": session.get("ui_prompt") if isinstance(session.get("ui_prompt"), dict) else {},
        "qa_prompt": session.get("qa_prompt") if isinstance(session.get("qa_prompt"), dict) else {},
        "copilot_context": session.get("copilot_context") if isinstance(session.get("copilot_context"), dict) else {},
        "qa_test_suite": session.get("qa_test_suite") if isinstance(session.get("qa_test_suite"), dict) else {},
        "implementation_validation": session.get("implementation_validation") if isinstance(session.get("implementation_validation"), dict) else {},
        "pr_review": session.get("pr_review") if isinstance(session.get("pr_review"), dict) else {},
        "saved_at": _clean_text(session.get("saved_at")) or _now_iso(),
    }


def _knowledge_schema_version() -> str:
    return "project-intelligence-cache-v1"


def _context_capsule_types() -> set[str]:
    return {"project", "feature", "story", "execution", "qa"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _document_hashes(documents: dict[str, str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path, content in sorted((documents or {}).items()):
        clean_path = _clean_path(path)
        text = _clean_text(content)
        if clean_path and text:
            hashes[clean_path] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return hashes


def _knowledge_version(profile: dict[str, Any], document_hashes: dict[str, str] | None = None) -> str:
    registry = profile.get("knowledge_registry") if isinstance(profile.get("knowledge_registry"), dict) else {}
    payload = {
        "schema": _knowledge_schema_version(),
        "project_id": profile.get("project_id"),
        "repository": profile.get("repository_connection", {}).get("repository_id") if isinstance(profile.get("repository_connection"), dict) else "",
        "branch": profile.get("repository_connection", {}).get("branch") if isinstance(profile.get("repository_connection"), dict) else "",
        "source_files": registry.get("source_files"),
        "modules": registry.get("modules"),
        "flows": registry.get("flows"),
        "components": registry.get("components"),
        "document_hashes": document_hashes or {},
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def _project_summary(profile: dict[str, Any]) -> str:
    registry = profile.get("knowledge_registry") if isinstance(profile.get("knowledge_registry"), dict) else {}
    parts = [
        _clean_text(profile.get("project_name")) or "Project",
        _clean_text(profile.get("domain")),
        f"Modules: {', '.join(_string_list(registry.get('modules'))[:6])}" if _string_list(registry.get("modules")) else "",
        f"Flows: {', '.join(_string_list(registry.get('flows'))[:6])}" if _string_list(registry.get("flows")) else "",
    ]
    return ". ".join(part for part in parts if part)


def _build_context_capsule(
    capsule_type: str,
    profile: dict[str, Any],
    item: dict[str, Any] | None,
    cache: dict[str, Any] | None,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    capsule_type = capsule_type if capsule_type in _context_capsule_types() else "project"
    profile = _normalize_profile(profile)
    item = item or {}
    cache = cache or {}
    payload = _context_capsule_payload(capsule_type, profile, item)
    source_payload = _capsule_source_payload(capsule_type, profile, item, cache)
    source_size = _estimate_tokens(json.dumps(source_payload, ensure_ascii=True, separators=(",", ":")))
    capsule_size = _estimate_tokens(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))
    source_hash = _capsule_source_hash(capsule_type, profile, item, cache)
    previous_version = int((previous or {}).get("version") or 0)
    knowledge_version = _clean_text(cache.get("knowledge_version")) or _knowledge_version(profile)
    return {
        "capsule_id": f"{capsule_type}_{source_hash[:12]}",
        "capsule_type": capsule_type,
        "status": "ready",
        "version": previous_version + 1 if (previous or {}).get("source_hash") != source_hash else previous_version or 1,
        "created_at": _now_iso(),
        "last_refreshed": _now_iso(),
        "source_hash": source_hash,
        "source_version": knowledge_version,
        "knowledge_version": knowledge_version,
        "dependencies": _capsule_dependencies(capsule_type, profile, item),
        "parent_references": _capsule_parent_references(item),
        "payload": payload,
        "diagnostics": {
            "capsule_size_tokens": capsule_size,
            "source_size_tokens": source_size,
            "compression_ratio": round(capsule_size / max(source_size, 1), 3),
            "source_sections": _capsule_source_sections(source_payload),
        },
    }


def _context_capsule_payload(capsule_type: str, profile: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    registry = profile["knowledge_registry"]
    selection = profile.get("_knowledge_relevance") if isinstance(profile.get("_knowledge_relevance"), dict) else _select_knowledge_context(profile, item, capsule_type.title())
    modules = _selection_names(selection, "relevant_modules")
    flows = _selection_names(selection, "relevant_flows")
    standards = _selection_names(selection, "relevant_standards")
    relevance_payload = {
        "intent_keywords": _string_list(selection.get("intent", {}).get("keywords"))[:16],
        "rejected_context": selection.get("rejected_context", [])[:12],
        "relevance_scores": selection.get("relevance_scores", {}),
        "context_source": selection.get("context_source") or "knowledge_relevance_selector",
    }
    project_payload = {
        "project_summary": _project_summary(profile),
        "project_name": profile["project_name"],
        "domain": profile["domain"] or profile["knowledge_profile_preview"]["domain"],
        "project_type": profile["project_type"],
        "applications": _application_names(profile)[:6],
        "architecture_summary": _truncate_text(_architecture_summary_text(profile, registry), 700),
        "modules": modules or registry["modules"][:4],
        "flows": flows or registry["flows"][:4],
        "standards": standards or _unique([*_flatten_standards(profile["development_standards"]), *registry["standards"]])[:8],
        "roles": _users_for_profile(profile),
        "technology_stack": _compact_stack(profile),
        "knowledge_version": _knowledge_version(profile),
        **relevance_payload,
    }
    if capsule_type == "project":
        return project_payload
    if capsule_type == "feature":
        return {
            **project_payload,
            "feature_summary": _truncate_text(_sentence(_clean_text(item.get("title")) or "Feature", _clean_text(item.get("description"))), 260),
            "business_goal": _clean_text(item.get("business_goal")) or _clean_text(item.get("business_value")),
            "modules": modules,
            "flows": flows,
            "dependencies": _string_list(item.get("dependencies")) or _dependencies_for_profile(profile)[:5],
            "parent_epic": _clean_text(item.get("parent_epic") or item.get("epic_title")),
        }
    if capsule_type == "story":
        acceptance = _string_list(item.get("acceptance_criteria"))[:8]
        return {
            **project_payload,
            "story_summary": _truncate_text(_sentence(_clean_text(item.get("title")) or "Story", _clean_text(item.get("description"))), 260),
            "acceptance_criteria": acceptance,
            "modules": modules,
            "flows": flows,
            "roles": _users_for_profile(profile),
            "dependencies": _string_list(item.get("dependencies")) or _dependencies_for_profile(profile)[:5],
            "parent_feature": _clean_text(item.get("parent_feature") or item.get("feature_title")),
        }
    if capsule_type == "execution":
        return {
            **project_payload,
            "dev_context": _truncate_text(_sentence(_clean_text(item.get("title")) or "Execution", _clean_text(item.get("description"))), 220),
            "ui_context": ", ".join(_ui_considerations(profile, flows)[:4]),
            "qa_context": ", ".join(_qa_considerations(profile, flows)[:4]),
            "impacted_files": _string_list(item.get("recommended_files"))[:8],
            "modules": modules,
            "flows": flows,
            "standards": _unique([*_flatten_standards(profile["development_standards"]), *registry["standards"]])[:8],
        }
    if capsule_type == "qa":
        acceptance = _string_list(item.get("acceptance_criteria"))[:8]
        return {
            **project_payload,
            "coverage_context": _truncate_text(_sentence(_clean_text(item.get("title")) or "QA", _clean_text(item.get("description"))), 220),
            "regression_context": _unique([*modules, *flows])[:10],
            "risk_areas": _string_list(item.get("risks")) or _risks_for_profile(profile, _context_keywords(_clean_text(item.get("title")), _clean_text(item.get("description")), profile))[:6],
            "validation_areas": acceptance or _acceptance_criteria(_clean_text(item.get("title")) or "Story", flows, modules)[:6],
            "modules": modules,
            "flows": flows,
        }
    return project_payload


def _capsule_source_payload(capsule_type: str, profile: dict[str, Any], item: dict[str, Any], cache: dict[str, Any]) -> dict[str, Any]:
    registry = profile["knowledge_registry"]
    return {
        "capsule_type": capsule_type,
        "profile": {
            "project_id": profile.get("project_id"),
            "project_name": profile.get("project_name"),
            "domain": profile.get("domain"),
            "project_type": profile.get("project_type"),
            "description": profile.get("project_description"),
            "applications": profile.get("applications"),
            "technology_stack": profile.get("technology_stack"),
            "development_standards": profile.get("development_standards"),
            "ui_guidelines": profile.get("ui_guidelines"),
        },
        "knowledge_registry": registry,
        "knowledge_version": cache.get("knowledge_version") or _knowledge_version(profile),
        "source_files": cache.get("source_files") or registry.get("source_files"),
        "item": item,
    }


def _capsule_source_hash(capsule_type: str, profile: dict[str, Any], item: dict[str, Any] | None, cache: dict[str, Any] | None) -> str:
    payload = _capsule_source_payload(capsule_type, _normalize_profile(profile), item or {}, cache or {})
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _capsule_dependencies(capsule_type: str, profile: dict[str, Any], item: dict[str, Any]) -> list[str]:
    dependencies = ["project_profile", "knowledge_registry"]
    if profile["knowledge_registry"]["source_files"]:
        dependencies.append("repository_documents")
    if capsule_type in {"feature", "story", "execution", "qa"}:
        dependencies.append("work_item")
    if capsule_type in {"execution", "qa"}:
        dependencies.append("acceptance_criteria")
    return dependencies


def _capsule_parent_references(item: dict[str, Any]) -> dict[str, str]:
    return {
        key: _clean_text(item.get(key))
        for key in ["parent_epic", "parent_feature", "parent_story", "epic_title", "feature_title", "story_title"]
        if _clean_text(item.get(key))
    }


def _capsule_source_sections(source_payload: dict[str, Any]) -> dict[str, int]:
    return {
        key: _estimate_tokens(json.dumps(value, ensure_ascii=True, separators=(",", ":"), default=str))
        for key, value in source_payload.items()
    }


def _capsule_status_payload(capsules: dict[str, Any], profile: dict[str, Any], cache: dict[str, Any]) -> dict[str, Any]:
    knowledge_version = _clean_text(cache.get("knowledge_version")) or _knowledge_version(_normalize_profile(profile))
    items = []
    for capsule_type in ["project", "feature", "story", "execution", "qa"]:
        capsule = capsules.get(capsule_type) if isinstance(capsules.get(capsule_type), dict) else {}
        diagnostics = capsule.get("diagnostics") if isinstance(capsule.get("diagnostics"), dict) else {}
        ready = bool(capsule) and capsule.get("source_version") == knowledge_version
        items.append({
            "capsule_type": capsule_type,
            "status": "ready" if ready else ("refresh_required" if capsule else "missing"),
            "version": capsule.get("version") or 0,
            "last_refreshed": _clean_text(capsule.get("last_refreshed") or capsule.get("created_at")),
            "source_version": _clean_text(capsule.get("source_version")),
            "capsule_size_tokens": int(diagnostics.get("capsule_size_tokens") or 0),
            "source_size_tokens": int(diagnostics.get("source_size_tokens") or 0),
            "compression_ratio": diagnostics.get("compression_ratio") or 0,
        })
    return {
        "knowledge_version": knowledge_version,
        "capsules": items,
        "ready_count": sum(1 for item in items if item["status"] == "ready"),
        "total_count": len(items),
    }


def _knowledge_status_payload(
    *,
    profile: dict[str, Any],
    mapping: dict[str, Any],
    status: str,
    last_analyzed_at: str,
    source_files: list[str],
    document_hashes: dict[str, str],
    changed_files: list[str],
    invalidation_reasons: list[str],
) -> dict[str, Any]:
    return {
        "project_id": _clean_text(profile.get("project_id")),
        "project_name": _clean_text(profile.get("project_name")),
        "repository": _clean_text(mapping.get("repository_name")) or _clean_text(profile.get("repository_connection", {}).get("repository_name") if isinstance(profile.get("repository_connection"), dict) else ""),
        "repository_id": _clean_text(mapping.get("repository_id")) or _clean_text(profile.get("repository_connection", {}).get("repository_id") if isinstance(profile.get("repository_connection"), dict) else ""),
        "branch": _clean_text(mapping.get("branch")) or _clean_text(profile.get("repository_connection", {}).get("branch") if isinstance(profile.get("repository_connection"), dict) else "main"),
        "knowledge_status": status,
        "last_analyzed_at": last_analyzed_at,
        "knowledge_version": _knowledge_version(_normalize_profile(profile), document_hashes),
        "source_files": source_files,
        "changed_files": changed_files,
        "invalidation_reasons": invalidation_reasons,
        "document_hashes": document_hashes,
    }


def _normalize_artifact_state(value: Any) -> str:
    state = _clean_text(value).lower()
    if state in {"draft", "review", "approved", "locked", "published", "rejected", "archived"}:
        return state
    return "draft"


def _normalize_artifact_record(value: dict[str, Any]) -> dict[str, Any]:
    source = value.get("source_item") if isinstance(value.get("source_item"), dict) else {}
    return {
        "artifact_id": _clean_text(value.get("artifact_id")),
        "artifact_type": _clean_text(value.get("artifact_type") or value.get("type")) or "Artifact",
        "state": _normalize_artifact_state(value.get("state")),
        "title": _clean_text(value.get("title")),
        "payload": value.get("payload") if isinstance(value.get("payload"), (dict, list, str)) else {},
        "fingerprint": _clean_text(value.get("fingerprint")),
        "source_item": {
            "id": _clean_text(source.get("id")),
            "type": _clean_text(source.get("type")),
            "title": _clean_text(source.get("title")),
        },
        "version": int(value.get("version") or 1),
        "created_by": _clean_text(value.get("created_by")),
        "created_on": _clean_text(value.get("created_on")),
        "updated_on": _clean_text(value.get("updated_on")),
        "approved_by": _clean_text(value.get("approved_by")),
        "approved_on": _clean_text(value.get("approved_on")),
        "published_by": _clean_text(value.get("published_by")),
        "published_on": _clean_text(value.get("published_on")),
        "rejected_by": _clean_text(value.get("rejected_by")),
        "rejected_on": _clean_text(value.get("rejected_on")),
        "last_action": _clean_text(value.get("last_action")),
        "last_comments": _clean_text(value.get("last_comments")),
        "last_changed_by": _clean_text(value.get("last_changed_by")),
        "rollback_from_version": int(value.get("rollback_from_version") or 0),
        "rollback_to_version": int(value.get("rollback_to_version") or 0),
        "locked_on": _clean_text(value.get("locked_on")),
        "archived_on": _clean_text(value.get("archived_on")),
        "history": value.get("history") if isinstance(value.get("history"), list) else [],
    }


def _artifact_fingerprint(artifact_type: str, source_item: dict[str, Any], payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "artifact_type": artifact_type,
                "source_item": source_item,
                "payload": payload,
            },
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _normalize_readme_analysis(value: Any) -> dict[str, Any]:
    analysis = value if isinstance(value, dict) else {}
    return {
        "summary": _clean_text(analysis.get("summary")),
        "applications": _normalize_applications(analysis.get("applications")),
        "modules": _string_list(analysis.get("modules")),
        "flows": _string_list(analysis.get("flows")),
        "architecture_notes": _string_list(analysis.get("architecture_notes")),
    }


def _normalize_knowledge_registry(value: Any) -> dict[str, Any]:
    registry = value if isinstance(value, dict) else {}
    module_details = _normalize_module_details(registry.get("module_details") or registry.get("modules"))
    flow_details = _normalize_flow_details(registry.get("flow_details") or registry.get("flows"))
    component_details = _normalize_component_details(registry.get("component_details") or registry.get("components"))
    modules = _unique([*_registry_names(registry.get("modules")), *[item["name"] for item in module_details]])
    flows = _unique([*_registry_names(registry.get("flows")), *[item["name"] for item in flow_details]])
    components = _unique([*_registry_names(registry.get("components")), *[item["name"] for item in component_details]])
    return {
        "applications": _normalize_applications(registry.get("applications")),
        "modules": modules,
        "module_details": module_details,
        "flows": flows,
        "flow_details": flow_details,
        "components": components,
        "component_details": component_details,
        "architecture_notes": _string_list(registry.get("architecture_notes")),
        "technology_stack": _normalize_stack(registry.get("technology_stack")),
        "standards": _string_list(registry.get("standards")),
        "source_files": _string_list(registry.get("source_files")),
        "ranked_files": registry.get("ranked_files") if isinstance(registry.get("ranked_files"), list) else [],
        "repository_file_ranking": registry.get("repository_file_ranking") if isinstance(registry.get("repository_file_ranking"), list) else [],
    }


def _normalize_module_details(value: Any) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return details
    for item in value:
        if isinstance(item, dict):
            name = _clean_registry_name(item.get("name"))
            responsibilities = _string_list(item.get("responsibilities"))
            dependencies = _string_list(item.get("dependencies"))
            source_file = _clean_text(item.get("source_file"))
        else:
            name = _clean_registry_name(item)
            responsibilities = []
            dependencies = []
            source_file = ""
        if name:
            details.append({"name": name, "responsibilities": responsibilities, "dependencies": dependencies, "source_file": source_file})
    return _unique_details(details, "name")


def _normalize_flow_details(value: Any) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return details
    for item in value:
        if isinstance(item, dict):
            name = _clean_registry_name(item.get("name"))
            steps = _string_list(item.get("steps"))
            source_file = _clean_text(item.get("source_file"))
        else:
            name = _clean_registry_name(item)
            steps = []
            source_file = ""
        if name:
            details.append({"name": name, "steps": steps, "source_file": source_file})
    return _unique_details(details, "name")


def _normalize_component_details(value: Any) -> list[dict[str, str]]:
    details: list[dict[str, str]] = []
    if not isinstance(value, list):
        return details
    for item in value:
        if isinstance(item, dict):
            name = _clean_registry_name(item.get("name"))
            component_type = _clean_text(item.get("type")) or _component_type(name)
            source_file = _clean_text(item.get("source_file"))
        else:
            name = _clean_registry_name(item)
            component_type = _component_type(name)
            source_file = ""
        if name and _is_component_name(name):
            details.append({"name": name, "type": component_type, "source_file": source_file})
    return _unique_details(details, "name")


def _normalize_stack(value: Any) -> dict[str, list[str]]:
    categories = ["mobile", "backend", "firmware", "analytics", "frontend"]
    if isinstance(value, dict):
        return {category: _string_list(value.get(category)) for category in categories}
    legacy = _string_list(value)
    stack = {category: [] for category in categories}
    for item in legacy:
        category = _stack_category(item)
        stack[category].append(item)
    return stack


def _infer_applications(text: str) -> list[dict[str, str]]:
    lowered = text.lower()
    apps: list[dict[str, str]] = []
    if any(word in lowered for word in ["ios", "android", "mobile", "field mobile"]):
        apps.append({"name": "Mobile App", "type": "Mobile"})
    if any(word in lowered for word in ["backend", "api", "service", "asp.net"]):
        apps.append({"name": "Backend", "type": "Backend"})
    if "firmware" in lowered:
        apps.append({"name": "Firmware", "type": "Firmware"})
    if any(word in lowered for word in ["operations dashboard", "operator dashboard", "web portal"]):
        apps.append({"name": "Operations Dashboard", "type": "Web Portal"})
    if any(word in lowered for word in ["analytics", "report", "dashboard"]):
        apps.append({"name": "Analytics", "type": "Analytics"})
    return apps or [{"name": "Application", "type": "API"}]


def _infer_stack(text: str) -> dict[str, list[str]]:
    lowered = text.lower()
    stack = {
        "mobile": [],
        "backend": [],
        "firmware": [],
        "analytics": [],
        "frontend": [],
    }
    for label, needles in {
        "React": ["react"],
        "TypeScript": ["typescript", "ts"],
        "Node.js": ["node"],
        "Python": ["python"],
        "FastAPI": ["fastapi"],
        "ASP.NET Core": ["asp.net core", "aspnetcore"],
        "REST APIs": ["rest api", "rest apis"],
        "SQL Server": ["sql server"],
        "Azure Data Platform": ["azure data platform", "azure analytics", "azure"],
        "Databricks": ["databricks"],
        "Swift": ["swift", "ios"],
        "Kotlin": ["kotlin", "android"],
        "Android": ["android"],
        ".NET": [".net", "dotnet"],
        ".NET MAUI": [".net maui", "maui"],
        "Flutter": ["flutter"],
        "C": [" firmware c "],
        "C++": ["c++"],
    }.items():
        if any(needle in lowered for needle in needles):
            stack[_stack_category(label)].append(label)
    return {key: list(dict.fromkeys(values)) for key, values in stack.items()}


def _infer_domain(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ["hotel", "booking", "reservation"]):
        return "Travel and booking"
    if any(word in lowered for word in ["commerce", "checkout", "payment", "order"]):
        return "E-commerce"
    if any(word in lowered for word in ["grid", "fault", "outage", "linedefender"]):
        return "Utility Grid Management"
    if any(word in lowered for word in ["meter", "energy", "utility"]):
        return "Smart Metering"
    if any(word in lowered for word in ["community", "property", "tenant"]):
        return "Community management"
    return "General product delivery"


def _infer_project_type(text: str) -> str:
    lowered = text.lower()
    has_mobile = any(word in lowered for word in ["ios", "android", "mobile"])
    has_other_system = any(word in lowered for word in ["backend", "api", "service", "analytics", "dashboard", "firmware"])
    if "multi-system" in lowered or (has_mobile and has_other_system) or ("platform" in lowered and any(word in lowered for word in ["backend", "analytics", "firmware", "mobile"])):
        return "Multi-System Platform"
    if has_mobile:
        return "Mobile Application"
    if any(word in lowered for word in ["web", "portal"]):
        return "Web Application"
    if any(word in lowered for word in ["backend", "api", "service"]):
        return "Backend Service"
    if "firmware" in lowered:
        return "Embedded Firmware"
    if any(word in lowered for word in ["analytics", "dashboard", "report"]):
        return "Analytics Platform"
    return ""


def _infer_standards(text: str) -> list[str]:
    standards = ["Human approval before creation", "Traceable Azure DevOps work item hierarchy"]
    lowered = text.lower()
    if any(word in lowered for word in ["secure", "auth", "payment", "privacy"]):
        standards.append("Security and privacy review required")
    if any(word in lowered for word in ["accessibility", "wcag", "mobile"]):
        standards.append("Accessibility validation required")
    return standards


def _profile_context_lines(profile: dict[str, Any]) -> list[str]:
    lines = [
        f"Project Name: {profile['project_name'] or 'Not specified'}",
        f"Domain: {profile['domain'] or profile['knowledge_profile_preview']['domain'] or 'Not specified'}",
        f"Project Type: {profile['project_type'] or 'Not specified'}",
        f"Project Description: {profile['project_description'] or 'No project description captured yet.'}",
        f"Applications: {_format_applications(profile['applications']) or 'Not specified'}",
        f"Technology Stack: {_format_stack(profile['technology_stack']) or 'Not specified'}",
        f"UI Guidelines: primary={profile['ui_guidelines']['primary_color'] or 'n/a'}, secondary={profile['ui_guidelines']['secondary_color'] or 'n/a'}, typography={profile['ui_guidelines']['typography'] or 'n/a'}, components={profile['ui_guidelines']['component_library'] or 'n/a'}",
        f"Development Standards: {_format_standards(profile['development_standards']) or 'Not specified'}",
        f"Detected Modules: {', '.join(profile['knowledge_registry']['modules']) or 'Not detected yet'}",
        f"Detected Flows: {', '.join(profile['knowledge_registry']['flows']) or 'Not detected yet'}",
        f"Architecture Summary: {', '.join(profile['knowledge_registry']['architecture_notes'] or profile['readme_analysis']['architecture_notes']) or 'Not detected yet'}",
        f"Repository Sources: {', '.join(profile['repository_sources']) or 'Repository README scan coming next.'}",
    ]
    return lines


def _readiness(profile: dict[str, Any]) -> str:
    execution = _readiness_breakdown(profile)["execution_readiness"]
    if execution["status"] == "Ready":
        return "Execution Ready"
    profile_setup = _readiness_breakdown(profile)["profile_setup"]
    registry = _readiness_breakdown(profile)["knowledge_registry"]
    if profile_setup["status"] == "Ready" and registry["status"] in {"Ready", "Partial"}:
        return "Advanced"
    if profile_setup["status"] in {"Ready", "Partial"}:
        return "Intermediate"
    return "Basic"


def _readiness_breakdown(profile: dict[str, Any]) -> dict[str, Any]:
    registry = _normalize_knowledge_registry(profile.get("knowledge_registry"))
    stack = _normalize_stack(profile.get("technology_stack"))
    standards = profile.get("development_standards") if isinstance(profile.get("development_standards"), dict) else {}
    repository = _normalize_repository_connection(profile.get("repository_connection"))
    profile_checks = {
        "project_name": bool(_clean_text(profile.get("project_name"))),
        "description": bool(_clean_text(profile.get("project_description"))),
        "domain": bool(_clean_text(profile.get("domain"))),
        "project_type": bool(_clean_text(profile.get("project_type"))),
        "applications": bool(_normalize_applications(profile.get("applications")) or registry["applications"]),
        "technology_stack": any(stack.values()) or any(_normalize_stack(registry.get("technology_stack")).values()),
        "ui_guidelines": bool(profile.get("ui_guidelines") and _string_list(profile.get("ui_guidelines", {}).get("accessibility_rules"))),
        "development_standards": bool(_flatten_standards(standards) or registry["standards"]),
    }
    repository_checks = {
        "repository_connected": bool(repository["repository_id"] or repository["repository_name"]),
        "branch_selected": bool(repository["branch"]),
        "documents_discovered": bool(_string_list(profile.get("repository_sources")) or registry["source_files"]),
        "documents_analyzed": repository["status"] in {"README analyzed", "Repository documents analyzed"} or bool(registry["source_files"]),
    }
    registry_checks = {
        "modules": bool(registry["modules"]),
        "flows": bool(registry["flows"]),
        "components": bool(registry["components"]),
        "architecture": bool(registry["architecture_notes"]),
        "standards": bool(registry["standards"] or _flatten_standards(standards)),
    }
    execution_checks = {
        "profile_setup": _check_status(profile_checks) == "Ready",
        "repository_analyzed": repository_checks["documents_analyzed"],
        "applications_detected": profile_checks["applications"],
        "modules_detected": registry_checks["modules"],
        "flows_detected": registry_checks["flows"],
        "standards_available": registry_checks["standards"],
        "execution_package_support": True,
    }
    return {
        "profile_setup": _readiness_section(profile_checks),
        "repository_intelligence": _readiness_section(repository_checks),
        "knowledge_registry": _readiness_section(registry_checks),
        "execution_readiness": _readiness_section(execution_checks),
    }


def _readiness_section(checks: dict[str, bool]) -> dict[str, Any]:
    ready_count = len([ready for ready in checks.values() if ready])
    percent = round((ready_count / max(len(checks), 1)) * 100)
    return {
        "percent": percent,
        "status": _check_status(checks),
        "missing": [key for key, ready in checks.items() if not ready],
    }


def _check_status(checks: dict[str, bool]) -> str:
    ready_count = len([ready for ready in checks.values() if ready])
    if ready_count == len(checks):
        return "Ready"
    if ready_count:
        return "Partial"
    return "Missing"


def _flatten_standards(standards: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ["architecture_patterns", "coding_guidelines", "security_requirements", "testing_requirements"]:
        values.extend(_string_list(standards.get(key)))
    return values


def _format_applications(applications: list[dict[str, str]]) -> str:
    return ", ".join(f"{app['name']} ({app['type']})" for app in _dedupe_applications(applications))


def _dedupe_applications(applications: list[dict[str, str]]) -> list[dict[str, str]]:
    selected: dict[str, dict[str, str]] = {}
    for app in applications:
        name = _clean_title(_clean_text(app.get("name")))
        app_type = _clean_title(_clean_text(app.get("type")))
        if not name:
            continue
        key = _application_canonical_key(name, app_type)
        candidate = {"name": name, "type": app_type or "Application"}
        current = selected.get(key)
        if current is None or _application_specificity(candidate) > _application_specificity(current):
            selected[key] = candidate
    return list(selected.values())


def _application_canonical_key(name: str, app_type: str) -> str:
    text = f"{name} {app_type}".lower()
    if "mobile" in text:
        return "mobile"
    if "dashboard" in text or "portal" in text or "web" in text:
        return "portal"
    if "backend" in text or "api" in text:
        return "backend"
    if "analytics" in text:
        return "analytics"
    if "firmware" in text:
        return "firmware"
    return _clean_text(app_type or name).lower()


def _application_specificity(app: dict[str, str]) -> int:
    name = app.get("name", "")
    score = len(name)
    if any(word in name.lower() for word in ["api", "dashboard", "portal", "application", "platform"]):
        score += 20
    return score


def _format_stack(stack: dict[str, list[str]]) -> str:
    parts = []
    for category, values in stack.items():
        if values:
            parts.append(f"{category}: {', '.join(values)}")
    return "; ".join(parts)


def _format_standards(standards: dict[str, list[str]]) -> str:
    return "; ".join(_flatten_standards(standards))


def _infer_application_type(name: str) -> str:
    lowered = name.lower()
    if "mobile" in lowered or "ios" in lowered or "android" in lowered:
        return "Mobile"
    if "backend" in lowered or "service" in lowered:
        return "Backend"
    if "firmware" in lowered:
        return "Firmware"
    if "portal" in lowered or "web" in lowered:
        return "Web Portal"
    if "analytics" in lowered or "report" in lowered:
        return "Analytics"
    if "desktop" in lowered:
        return "Desktop"
    return "API"


def _stack_category(item: str) -> str:
    lowered = item.lower()
    if any(word in lowered for word in ["kotlin", "swift", "flutter", "maui"]):
        return "mobile"
    if any(word in lowered for word in ["fastapi", "python", "node", ".net", "dotnet", "asp.net", "rest api", "sql server"]):
        return "backend"
    if any(word in lowered for word in ["c++", "firmware"]):
        return "firmware"
    if any(word in lowered for word in ["analytics", "spark", "power bi", "dashboard", "azure data", "databricks"]):
        return "analytics"
    return "frontend"


def _analyze_readme_content(readme_content: str) -> dict[str, Any]:
    text = readme_content.strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    summary = _extract_summary(lines)
    module_details = _extract_module_details(text, "README.md")
    flow_details = _extract_flow_details(text, "README.md")
    modules = [item["name"] for item in module_details] or _extract_section_items(lines, ["modules", "packages", "services"])
    flows = [item["name"] for item in flow_details] or _extract_section_items(lines, ["flows", "workflows", "user journeys"])
    architecture_notes = _extract_architecture_notes(lines)
    applications = _extract_applications_from_readme(text)
    component_details = _extract_component_details(text, "README.md")
    components = [item["name"] for item in component_details]
    return {
        "summary": summary,
        "applications": applications,
        "modules": modules,
        "module_details": module_details,
        "flows": flows,
        "flow_details": flow_details,
        "architecture_notes": architecture_notes,
        "components": components,
        "component_details": component_details,
        "technology_stack": _infer_stack(text),
        "standards": [],
        "source_files": [],
    }


def _analyze_repository_documents(documents: dict[str, str]) -> dict[str, Any]:
    readme_summary = ""
    architecture_notes: list[str] = []
    detected_applications: list[dict[str, str]] = []
    detected_modules: list[str] = []
    module_details: list[dict[str, Any]] = []
    detected_flows: list[str] = []
    flow_details: list[dict[str, Any]] = []
    detected_components: list[str] = []
    component_details: list[dict[str, str]] = []
    ui_standards: list[str] = []
    development_standards: list[str] = []
    classified_standards = {
        "security": [],
        "coding": [],
        "testing": [],
        "ui": [],
    }
    detected_stack = _normalize_stack({})
    warnings: list[str] = []
    source_files: list[str] = []

    for path, content in documents.items():
        lowered_path = path.lower()
        source_files.append(path)
        parsed = _analyze_readme_content(content)
        detected_stack = _merge_stack(detected_stack, parsed.get("technology_stack", {}), _infer_stack(content))
        detected_modules.extend(_known_modules_from_text(content))
        detected_flows.extend(_known_flows_from_text(content))
        known_components = _known_components_from_text(content)
        detected_components.extend(known_components)
        component_details.extend({"name": name, "type": _component_type(name), "source_file": path} for name in known_components)
        detected_applications = _merge_applications(detected_applications, _applications_from_components(known_components))
        classified_standards = _merge_classified_standards(classified_standards, _classify_standards(_extract_standards(content, ["security", "coding standards", "testing", "ui guidelines", "accessibility", "architecture"])))
        if "readme" in lowered_path and not readme_summary:
            readme_summary = parsed["summary"]
            detected_applications = _merge_applications(detected_applications, parsed["applications"])
        if "architecture" in lowered_path:
            architecture_notes.extend(_extract_architecture_notes([line.strip() for line in content.splitlines() if line.strip()]))
            extracted_components = _extract_component_details(content, path)
            component_details.extend(extracted_components)
            detected_components.extend([item["name"] for item in extracted_components])
            detected_applications = _merge_applications(detected_applications, _extract_applications_from_readme(content))
        elif "modules" in lowered_path:
            extracted_modules = _extract_module_details(content, path)
            module_details.extend(extracted_modules)
            detected_modules.extend([item["name"] for item in extracted_modules] or _extract_module_names_from_root_lists(content))
        elif "flows" in lowered_path:
            extracted_flows = _extract_flow_details(content, path)
            flow_details.extend(extracted_flows)
            detected_flows.extend([item["name"] for item in extracted_flows] or _extract_flow_names_from_root_lists(content))
        elif "ui-guidelines" in lowered_path:
            ui_standards.extend(_extract_standards(content, ["ui guidelines", "accessibility", "design rules"]))
        elif "coding-standards" in lowered_path:
            development_standards.extend(_extract_standards(content, ["coding standards", "security", "testing", "architecture"]))
        else:
            detected_applications = _merge_applications(detected_applications, parsed["applications"])
            detected_modules.extend(parsed["modules"])
            module_details.extend(parsed["module_details"])
            detected_flows.extend(parsed["flows"])
            flow_details.extend(parsed["flow_details"])
            detected_components.extend(parsed["components"])
            component_details.extend(parsed["component_details"])
            architecture_notes.extend(parsed["architecture_notes"])
            ui_standards.extend(_extract_standards(content, ["ui guidelines", "accessibility", "design rules"]))
            development_standards.extend(_extract_standards(content, ["coding standards", "security", "testing", "architecture"]))

    if not documents:
        warnings.append("No repository documents were available for analysis.")

    architecture_notes = _clean_architecture_notes(architecture_notes)
    architecture_summary = _architecture_summary(documents, architecture_notes, detected_stack)
    module_details = _enrich_module_details(_unique_details(module_details, "name"))
    flow_details = _unique_details(flow_details, "name")
    component_details = _unique_details(component_details, "name")
    detected_modules = _clean_registry_names(_unique([*detected_modules, *[item["name"] for item in module_details]]), kind="module")
    detected_flows = _clean_registry_names(_unique([*detected_flows, *[item["name"] for item in flow_details]]), kind="flow")
    detected_components = _clean_registry_names(_unique([*detected_components, *[item["name"] for item in component_details]]), kind="component")
    standards = _unique([*ui_standards, *development_standards, *classified_standards["security"], *classified_standards["coding"], *classified_standards["testing"], *classified_standards["ui"]])
    return {
        "readme_summary": readme_summary,
        "architecture_summary": architecture_summary,
        "architecture_notes": _unique(architecture_notes),
        "detected_applications": detected_applications,
        "detected_modules": _unique(detected_modules),
        "module_details": module_details,
        "detected_flows": _unique(detected_flows),
        "flow_details": flow_details,
        "detected_components": _unique(detected_components),
        "component_details": component_details,
        "ui_standards": _unique(ui_standards),
        "development_standards": _unique(development_standards),
        "classified_standards": classified_standards,
        "technology_stack": detected_stack,
        "source_files": _unique(source_files),
        "warnings": warnings,
        "applications": detected_applications,
        "modules": _unique(detected_modules),
        "module_details": module_details,
        "flows": _unique(detected_flows),
        "flow_details": flow_details,
        "components": _unique(detected_components),
        "component_details": component_details,
        "standards": standards,
        "technology_stack": detected_stack,
    }


def _extract_document_items(content: str, sections: list[str]) -> list[str]:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    section_items = _extract_section_items(lines, sections)
    labelled_items = _extract_labelled_items(lines, sections)
    return _unique([*section_items, *labelled_items]) or _extract_bullets(content)


def _markdown_sections(content: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw in content.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            title = _clean_registry_name(stripped.lstrip("#").strip())
            current = {"level": level, "title": title, "lines": []}
            sections.append(current)
        elif current is not None:
            current["lines"].append(stripped)
    return sections


def _extract_module_details(content: str, source_file: str) -> list[dict[str, Any]]:
    sections = _markdown_sections(content)
    details: list[dict[str, Any]] = []
    module_parent_active = False
    for index, section in enumerate(sections):
        title = section["title"]
        lowered = title.lower()
        if _is_detail_section_title(lowered) and details:
            _attach_module_detail(details[-1], lowered, section["lines"])
            continue
        if _is_module_container_title(lowered):
            module_parent_active = True
            for name in _module_names_from_lines(section["lines"]):
                details.append({"name": name, "responsibilities": [], "dependencies": [], "source_file": source_file})
            continue
        if section["level"] <= 1 and not _is_module_container_title(lowered):
            module_parent_active = False
        if module_parent_active or lowered.endswith(" module"):
            if _is_detail_section_title(lowered):
                if details:
                    _attach_module_detail(details[-1], lowered, section["lines"])
                continue
            if _is_detail_section_title(lowered) and details:
                _attach_module_detail(details[-1], lowered, section["lines"])
                continue
            if _is_module_heading(title):
                detail = {
                    "name": _clean_registry_name(title.replace("Module", "").strip()) if lowered.endswith(" module") else title,
                    "responsibilities": [],
                    "dependencies": [],
                    "source_file": source_file,
                }
                detail["responsibilities"].extend(_section_detail_lines(section["lines"], ["responsibilities", "responsibility"]))
                detail["dependencies"].extend(_section_detail_lines(section["lines"], ["dependencies", "dependency"]))
                details.append(detail)
            elif _is_detail_section_title(lowered) and details:
                _attach_module_detail(details[-1], lowered or previous, section["lines"])
    inline = _extract_labelled_items([line.strip() for line in content.splitlines() if line.strip()], ["modules"])
    for name in inline:
        cleaned = _clean_registry_name(name)
        if _is_module_name(cleaned):
            details.append({"name": cleaned, "responsibilities": [], "dependencies": [], "source_file": source_file})
    return _unique_details(details, "name")


def _attach_module_detail(module: dict[str, Any], title: str, lines: list[str]) -> None:
    values = _clean_registry_names(_extract_bullets("\n".join(lines)) or [_clean_bullet(line) for line in lines], kind="detail")
    if "depend" in title:
        module["dependencies"] = _unique([*module.get("dependencies", []), *values])
    elif "respons" in title or "capabil" in title:
        module["responsibilities"] = _unique([*module.get("responsibilities", []), *values])


def _section_detail_lines(lines: list[str], labels: list[str]) -> list[str]:
    details: list[str] = []
    active = ""
    for line in lines:
        stripped = _clean_bullet(line)
        lowered = stripped.lower().rstrip(":")
        if any(label in lowered for label in labels):
            active = lowered
            if ":" in stripped:
                details.extend(_split_inline_values(stripped.split(":", 1)[1]))
            continue
        if active and line.strip().startswith(("-", "*")):
            details.append(stripped)
    return _unique(details)


def _module_names_from_lines(lines: list[str]) -> list[str]:
    names = []
    for line in lines:
        if not line.strip().startswith(("-", "*")):
            continue
        candidate = _clean_bullet(line).split(":", 1)[0]
        if _is_module_name(candidate):
            names.append(_clean_registry_name(candidate))
    return _unique(names)


def _extract_module_names_from_root_lists(content: str) -> list[str]:
    names = []
    for section in _markdown_sections(content):
        if _is_module_container_title(section["title"].lower()):
            names.extend(_module_names_from_lines(section["lines"]))
    names.extend(name for name in _extract_labelled_items([line.strip() for line in content.splitlines() if line.strip()], ["modules"]) if _is_module_name(name))
    return _unique(names)


def _extract_flow_details(content: str, source_file: str) -> list[dict[str, Any]]:
    sections = _markdown_sections(content)
    details: list[dict[str, Any]] = []
    flow_parent_active = False
    for section in sections:
        title = section["title"]
        lowered = title.lower()
        if _is_flow_container_title(lowered):
            flow_parent_active = True
            for name in _flow_names_from_lines(section["lines"]):
                details.append({"name": name, "steps": [], "source_file": source_file})
            continue
        if section["level"] <= 2 and not _is_flow_container_title(lowered):
            flow_parent_active = False
        if flow_parent_active or _is_flow_name(title):
            if _is_detail_section_title(lowered):
                if details:
                    details[-1]["steps"] = _unique([*details[-1].get("steps", []), *_extract_bullets("\n".join(section["lines"]))])
                continue
            if _is_flow_name(title):
                details.append({"name": _clean_registry_name(title), "steps": _extract_bullets("\n".join(section["lines"])), "source_file": source_file})
    inline = _extract_labelled_items([line.strip() for line in content.splitlines() if line.strip()], ["flows"])
    for name in inline:
        cleaned = _clean_registry_name(name)
        if _is_flow_name(cleaned):
            details.append({"name": cleaned, "steps": [], "source_file": source_file})
    return _unique_details(details, "name")


def _flow_names_from_lines(lines: list[str]) -> list[str]:
    names = []
    for line in lines:
        if not line.strip().startswith(("-", "*")):
            continue
        candidate = _clean_bullet(line).split(":", 1)[0]
        if _is_flow_name(candidate):
            names.append(_clean_registry_name(candidate))
    return _unique(names)


def _extract_flow_names_from_root_lists(content: str) -> list[str]:
    names = []
    for section in _markdown_sections(content):
        if _is_flow_container_title(section["title"].lower()):
            names.extend(_flow_names_from_lines(section["lines"]))
    names.extend(name for name in _extract_labelled_items([line.strip() for line in content.splitlines() if line.strip()], ["flows"]) if _is_flow_name(name))
    return _unique(names)


def _extract_component_details(content: str, source_file: str) -> list[dict[str, str]]:
    sections = _markdown_sections(content)
    details: list[dict[str, str]] = []
    for section in sections:
        if not _is_component_container_title(section["title"].lower()):
            continue
        for item in _extract_bullets("\n".join(section["lines"])):
            name = _clean_registry_name(item.split(":", 1)[0])
            if _is_component_name(name):
                details.append({"name": name, "type": _component_type(name), "source_file": source_file})
    labelled = _extract_labelled_items([line.strip() for line in content.splitlines() if line.strip()], ["components", "services", "systems"])
    for name in labelled:
        cleaned = _clean_registry_name(name)
        if _is_component_name(cleaned):
            details.append({"name": cleaned, "type": _component_type(cleaned), "source_file": source_file})
    return _unique_details(details, "name")


def _known_modules_from_text(text: str) -> list[str]:
    lowered = text.lower()
    mapping = {
        "Authentication": ["authentication", "login", "identity", "rbac"],
        "Device Management": ["device management", "device registration", "device inventory"],
        "Telemetry": ["telemetry", "meter reading", "sensor data"],
        "Fault Monitoring": ["fault monitoring", "fault event", "outage event"],
        "Firmware Management": ["firmware", "firmware update", "upgrade visibility"],
        "Asset Health": ["asset health", "device health", "health monitoring"],
        "Reporting": ["reporting", "reports", "reliability metrics"],
        "Device Layer": ["device layer", "field device", "edge device"],
    }
    return [name for name, needles in mapping.items() if any(needle in lowered for needle in needles)]


def _known_flows_from_text(text: str) -> list[str]:
    lowered = text.lower()
    mapping = {
        "Login Flow": ["login flow", "authentication flow", "sign in"],
        "Device Registration Flow": ["device registration", "register device"],
        "Fault Event Review Flow": ["fault event review", "review fault", "fault triage"],
        "Device Health Review Flow": ["device health review", "health review"],
        "Firmware Update Flow": ["firmware update", "firmware upgrade"],
        "Outage Investigation Flow": ["outage investigation", "investigate outage"],
    }
    return [name for name, needles in mapping.items() if any(needle in lowered for needle in needles)]


def _known_components_from_text(text: str) -> list[str]:
    lowered = text.lower()
    mapping = {
        "Mobile Application": ["mobile application", ".net maui", "field mobile", "ios", "android"],
        "Backend API": ["backend api", "rest api", "asp.net core", "api service"],
        "Operations Dashboard": ["operations dashboard", "operator dashboard", "react dashboard"],
        "Analytics Platform": ["analytics platform", "databricks", "power bi", "azure analytics"],
        "Telemetry Integration Layer": ["telemetry integration", "integration layer"],
        "Telemetry Service": ["telemetry service"],
        "Device Repository": ["device repository"],
        "Event Repository": ["event repository"],
    }
    return [name for name, needles in mapping.items() if any(needle in lowered for needle in needles)]


def _applications_from_components(components: list[str]) -> list[dict[str, str]]:
    return [{"name": name, "type": _infer_application_type(name)} for name in components if name in {"Mobile Application", "Backend API", "Operations Dashboard", "Analytics Platform"}]


def _enrich_module_details(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_enrich_module_detail(detail) for detail in details]


def _enrich_module_detail(detail: dict[str, Any]) -> dict[str, Any]:
    name = _clean_registry_name(detail.get("name"))
    responsibilities = _string_list(detail.get("responsibilities"))
    dependencies = _string_list(detail.get("dependencies"))
    defaults = {
        "Authentication": (["Login", "Token validation", "Role-based access control"], ["Identity Provider"]),
        "Device Management": (["Device registration", "Device inventory", "Device lookup"], ["Device Repository"]),
        "Telemetry": (["Telemetry ingestion", "Telemetry normalization", "Telemetry storage"], ["Telemetry Service", "Device Repository"]),
        "Fault Monitoring": (["Fault event ingestion", "Fault event storage", "Fault event analysis", "Fault notifications"], ["Telemetry Service", "Event Repository"]),
        "Firmware Management": (["Firmware package tracking", "Firmware rollout status", "Firmware update visibility"], ["Device Repository"]),
        "Asset Health": (["Asset health scoring", "Device condition review", "Health trend monitoring"], ["Telemetry Service"]),
        "Reporting": (["Operational reports", "Reliability metrics", "Exportable summaries"], ["Analytics Platform"]),
        "Device Layer": (["Device communication", "Telemetry publishing", "Firmware command handling"], ["Telemetry Integration Layer"]),
    }
    default_responsibilities, default_dependencies = defaults.get(name, ([], []))
    return {
        **detail,
        "name": name,
        "responsibilities": _unique([*responsibilities, *default_responsibilities]),
        "dependencies": _unique([*dependencies, *default_dependencies]),
    }


def _classify_standards(values: list[str]) -> dict[str, list[str]]:
    classified = {"security": [], "coding": [], "testing": [], "ui": []}
    for item in values:
        lowered = item.lower()
        if any(word in lowered for word in ["security", "role-based", "rbac", "oauth", "jwt", "secure", "audit", "permission", "tls"]):
            classified["security"].append(item)
        elif any(word in lowered for word in ["test", "qa", "coverage", "regression", "integration testing", "unit"]):
            classified["testing"].append(item)
        elif any(word in lowered for word in ["contrast", "touch", "accessibility", "offline", "ui", "wcag", "48dp"]):
            classified["ui"].append(item)
        else:
            classified["coding"].append(item)
    return {key: _unique(items) for key, items in classified.items()}


def _merge_classified_standards(base: dict[str, list[str]], incoming: dict[str, list[str]]) -> dict[str, list[str]]:
    return {
        "security": _unique([*base.get("security", []), *incoming.get("security", [])]),
        "coding": _unique([*base.get("coding", []), *incoming.get("coding", [])]),
        "testing": _unique([*base.get("testing", []), *incoming.get("testing", [])]),
        "ui": _unique([*base.get("ui", []), *incoming.get("ui", [])]),
    }


def _extract_labelled_items(lines: list[str], labels: list[str]) -> list[str]:
    items: list[str] = []
    normalized_labels = [label.lower().replace(" ", "") for label in labels]
    for line in lines:
        if ":" not in line:
            continue
        label, value = line.split(":", 1)
        normalized_label = label.lower().strip("# -*").replace(" ", "")
        if not any(normalized in normalized_label for normalized in normalized_labels):
            continue
        parts = [part.strip(" -*`") for part in value.replace(";", ",").split(",")]
        items.extend(part for part in parts if part)
    return _unique(items)


def _split_inline_values(value: str) -> list[str]:
    return [_clean_registry_name(part) for part in value.replace(";", ",").split(",") if _clean_registry_name(part)]


def _extract_bullets(content: str) -> list[str]:
    items: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(("-", "*")):
            items.append(_clean_bullet(stripped))
    return _unique(items)


def _clean_bullet(line: str) -> str:
    return _clean_registry_name(line.strip().lstrip("-* ").strip())


def _extract_summary(lines: list[str]) -> str:
    for line in lines:
        if not line.startswith("#") and len(line) > 24:
            return line[:500]
    return lines[0].lstrip("# ").strip()[:500] if lines else ""


def _extract_section_items(lines: list[str], section_names: list[str]) -> list[str]:
    items: list[str] = []
    in_section = False
    for line in lines:
        lowered = line.lower().strip("# ")
        if line.startswith("#"):
            in_section = any(name in lowered for name in section_names)
            continue
        if in_section:
            if line.startswith(("-", "*")):
                items.append(line.lstrip("-* ").split(":", 1)[0].strip())
            elif len(line.split()) <= 5:
                items.append(line.split(":", 1)[0].strip())
    return _unique(items)


def _extract_architecture_notes(lines: list[str]) -> list[str]:
    notes = _extract_section_items(lines, ["architecture", "design", "technical overview"])
    keyword_notes = [
        line.lstrip("-* ").strip()
        for line in lines
        if any(word in line.lower() for word in ["architecture", "mvvm", "repository pattern", "microservice", "event", "api", "database"])
    ]
    return _unique(notes + keyword_notes)[:10]


def _extract_standards(content: str, sections: list[str]) -> list[str]:
    values = []
    for section in _markdown_sections(content):
        if any(name in section["title"].lower() for name in sections):
            values.extend(_extract_bullets("\n".join(section["lines"])))
    values.extend(_extract_labelled_items([line.strip() for line in content.splitlines() if line.strip()], sections))
    values.extend(_known_standards_from_text(content))
    return _clean_registry_names(values, kind="standard")


def _known_standards_from_text(text: str) -> list[str]:
    lowered = text.lower()
    standards = []
    mapping = {
        "Role-based access control": ["role-based access", "rbac"],
        "Secure communication": ["secure communication", "tls", "https"],
        "Audit logging": ["audit logging", "audit log"],
        "Structured logging": ["structured logging"],
        "Input validation": ["input validation", "validate input"],
        "Unit and integration tests": ["unit and integration", "unit tests", "integration tests"],
        "Offline-first mobile handling": ["offline-first", "offline first"],
        "High contrast field UI": ["high contrast"],
        "48dp minimum touch target": ["48dp", "touch target"],
    }
    for label, needles in mapping.items():
        if any(needle in lowered for needle in needles):
            standards.append(label)
    return standards


def _clean_architecture_notes(notes: list[str]) -> list[str]:
    cleaned = []
    for note in notes:
        value = _clean_registry_name(note)
        if ":" in value and value.split(":", 1)[0].lower().strip() in {"architecture", "architecture notes", "notes"}:
            value = _clean_registry_name(value.split(":", 1)[1])
        if not value or len(value) < 12:
            continue
        lowered = value.lower()
        if any(token in lowered for token in ["```", "|", "+---", "sequence diagram", "mermaid"]):
            continue
        if lowered.startswith(("responsibilities", "dependencies", "fields", "steps")):
            continue
        cleaned.append(value.rstrip(".") + ".")
    return _unique(cleaned)[:8]


def _architecture_summary(documents: dict[str, str], notes: list[str], stack: dict[str, list[str]]) -> str:
    combined = "\n".join(documents.values())
    lowered = combined.lower()
    if "linedefender" in lowered or ("telemetry" in lowered and "fault" in lowered):
        parts = ["The platform consists of a .NET MAUI mobile application, ASP.NET Core backend services, React operations dashboard, Azure analytics platform, and telemetry integration layer"]
        technologies = []
        if any(pattern in lowered for pattern in ["mvvm", "model-view-viewmodel"]):
            technologies.append("MVVM")
        if "repository pattern" in lowered or "repository" in lowered:
            technologies.append("Repository Pattern")
        if "service layer" in lowered or "services" in lowered:
            technologies.append("Service Layer")
        if technologies:
            parts.append("It follows " + ", ".join(technologies) + " architecture")
        return ". ".join(parts).rstrip(".") + "."
    if notes:
        return _clean_registry_name(" ".join(notes[:3]))[:600].rstrip(".") + "."
    stack_text = _format_stack(stack)
    return f"Architecture uses {stack_text}." if stack_text else ""


def _merge_stack(*stacks: Any) -> dict[str, list[str]]:
    merged = _normalize_stack({})
    for stack in stacks:
        normalized = _normalize_stack(stack)
        for category, values in normalized.items():
            merged[category] = _unique([*merged.get(category, []), *values])
    return merged


def _clean_registry_names(values: list[str], kind: str) -> list[str]:
    cleaned = []
    for value in values:
        name = _clean_registry_name(value)
        if kind == "module" and not _is_module_name(name):
            continue
        if kind == "flow":
            if not _is_flow_name(name):
                continue
        if kind == "component" and not _is_component_name(name):
            continue
        if kind in {"standard", "detail"} and not name:
            continue
        cleaned.append(name)
    return _unique(cleaned)


def _clean_registry_name(value: Any) -> str:
    text = _clean_text(value)
    text = text.strip("`| ")
    text = text.replace("###", "").replace("##", "").replace("#", "")
    text = text.replace("```text", "").replace("```", "")
    text = text.strip("-*| ")
    text = text.split("  ")[0].strip()
    return text[:160].strip()


def _is_module_container_title(title: str) -> bool:
    return any(token == title or token in title for token in ["modules", "core modules", "domain modules", "application modules"])


def _is_flow_container_title(title: str) -> bool:
    return any(token == title or token in title for token in ["flows", "workflows", "user journeys", "scenarios"])


def _is_component_container_title(title: str) -> bool:
    return any(token == title or token in title for token in ["components", "services", "systems", "architecture components", "applications"])


def _is_detail_section_title(title: str) -> bool:
    return any(token in title for token in ["responsibilities", "dependencies", "steps", "fields", "rules"])


def _is_module_heading(title: str) -> bool:
    lowered = title.lower()
    return _is_module_name(title) and not _is_detail_section_title(lowered) and "flow" not in lowered


def _is_module_name(name: str) -> bool:
    cleaned = _clean_registry_name(name)
    lowered = cleaned.lower()
    if not cleaned or len(cleaned.split()) > 5:
        return False
    blocked = ["token management", "identity provider", "device id", "serial number", "timestamp", "responsibilities", "dependencies", "unit tests", "input validation", "audit logging", "risk", "future", "idea", "field"]
    if any(block in lowered for block in blocked):
        return False
    return any(word in lowered for word in ["auth", "device", "telemetry", "fault", "firmware", "asset", "report", "meter", "inventory", "billing", "outage", "monitoring", "repository", "layer"])


def _is_flow_name(name: str) -> bool:
    cleaned = _clean_registry_name(name)
    lowered = cleaned.lower()
    if not cleaned or len(cleaned.split()) > 7:
        return False
    if any(block in lowered for block in ["field", "timestamp", "serial number", "device id", "rules", "standards", "risk", "future"]):
        return False
    return "flow" in lowered or any(word in lowered for word in ["login", "lookup", "review", "investigation", "status", "upgrade", "onboarding", "inspection", "analytics", "triage", "rollout"])


def _is_component_name(name: str) -> bool:
    cleaned = _clean_registry_name(name)
    lowered = cleaned.lower()
    if not cleaned or len(cleaned.split()) > 7:
        return False
    blocked = ["device id", "serial number", "timestamp", "48dp", "touch target", "high contrast", "role-based access", "input validation", "audit logging", "unit tests", "future", "risk", "goal"]
    if any(block in lowered for block in blocked):
        return False
    return any(word in lowered for word in ["application", "api", "dashboard", "platform", "layer", "service", "repository", "portal", "database", "device", "integration", "screen", "timeline"])


def _component_type(name: str) -> str:
    lowered = name.lower()
    if "mobile" in lowered or "application" in lowered:
        return "application"
    if "dashboard" in lowered or "portal" in lowered:
        return "ui"
    if "database" in lowered or "repository" in lowered:
        return "database"
    if "device" in lowered and "service" not in lowered:
        return "device"
    if "analytics" in lowered:
        return "analytics"
    if "integration" in lowered or "layer" in lowered:
        return "integration"
    return "service"


def _ensure_suffix(value: str, suffix: str) -> str:
    cleaned = _clean_registry_name(value)
    return cleaned if not cleaned or cleaned.lower().endswith(suffix.lower()) else f"{cleaned} {suffix}"


def _unique_details(values: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for value in values:
        name = _clean_registry_name(value.get(key))
        lookup = name.lower()
        if not name or lookup in seen:
            continue
        seen.add(lookup)
        next_value = {**value, key: name}
        if "responsibilities" in next_value:
            next_value["responsibilities"] = _unique(_string_list(next_value.get("responsibilities")))
        if "dependencies" in next_value:
            next_value["dependencies"] = _unique(_string_list(next_value.get("dependencies")))
        if "steps" in next_value:
            next_value["steps"] = _unique(_string_list(next_value.get("steps")))
        result.append(next_value)
    return result


def _extract_applications_from_readme(text: str) -> list[dict[str, str]]:
    inferred = _infer_applications(text)
    return [] if inferred == [{"name": "Application", "type": "API"}] else inferred


def _merge_knowledge_registry(existing: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_knowledge_registry(existing)
    module_details = _unique_details([*normalized["module_details"], *_normalize_module_details(analysis.get("module_details") or analysis.get("modules"))], "name")
    flow_details = _unique_details([*normalized["flow_details"], *_normalize_flow_details(analysis.get("flow_details") or analysis.get("flows"))], "name")
    component_details = _unique_details([*normalized["component_details"], *_normalize_component_details(analysis.get("component_details") or analysis.get("components"))], "name")
    technology_stack = _merge_stack(normalized.get("technology_stack", {}), analysis.get("technology_stack", {}))
    return {
        "applications": _merge_applications(normalized["applications"], analysis.get("applications", [])),
        "modules": _unique([*normalized["modules"], *_registry_names(analysis.get("modules")), *[item["name"] for item in module_details]]),
        "module_details": module_details,
        "flows": _unique([*normalized["flows"], *_registry_names(analysis.get("flows")), *[item["name"] for item in flow_details]]),
        "flow_details": flow_details,
        "components": _unique([*normalized["components"], *_registry_names(analysis.get("components")), *[item["name"] for item in component_details]]),
        "component_details": component_details,
        "architecture_notes": _unique([*normalized["architecture_notes"], *_string_list(analysis.get("architecture_notes"))]),
        "technology_stack": technology_stack,
        "standards": _unique([*normalized["standards"], *_string_list(analysis.get("standards"))]),
        "source_files": _unique([*normalized["source_files"], *_string_list(analysis.get("source_files"))]),
    }


def _merge_development_standards(existing: dict[str, Any], detected: list[str]) -> dict[str, list[str]]:
    normalized = {
        "architecture_patterns": _string_list(existing.get("architecture_patterns")),
        "coding_guidelines": _string_list(existing.get("coding_guidelines")),
        "security_requirements": _string_list(existing.get("security_requirements")),
        "testing_requirements": _string_list(existing.get("testing_requirements")),
    }
    classified = _classify_standards(detected)
    normalized["security_requirements"].extend(classified["security"])
    normalized["testing_requirements"].extend(classified["testing"])
    for item in classified["coding"]:
        lowered = item.lower()
        if any(word in lowered for word in ["mvvm", "repository", "architecture", "pattern", "service layer"]):
            normalized["architecture_patterns"].append(item)
        else:
            normalized["coding_guidelines"].append(item)
    return {key: _unique(values) for key, values in normalized.items()}


def _merge_applications(existing: list[dict[str, str]], incoming: Any) -> list[dict[str, str]]:
    merged: dict[str, dict[str, str]] = {app["name"].lower(): app for app in _normalize_applications(existing)}
    for app in _normalize_applications(incoming):
        merged.setdefault(app["name"].lower(), app)
    return list(merged.values())


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = _clean_text(value)
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def _merge_external_knowledge(profile: dict[str, Any], knowledge_profile: dict[str, Any]) -> dict[str, Any]:
    if not knowledge_profile:
        return profile
    registry = _merge_knowledge_registry(profile["knowledge_registry"], knowledge_profile)
    return {
        **profile,
        "knowledge_registry": registry,
        "readme_analysis": {
            **profile["readme_analysis"],
            "architecture_notes": _unique([
                *profile["readme_analysis"]["architecture_notes"],
                *_string_list(knowledge_profile.get("architecture_notes")),
            ]),
        },
    }


def _clean_path(path: Any) -> str:
    return _clean_text(path).lstrip("/")


def _context_keywords(title: str, description: str, profile: dict[str, Any]) -> list[str]:
    text = " ".join(
        [
            title,
            description,
            profile.get("project_name", ""),
            profile.get("domain", ""),
            profile.get("project_type", ""),
            profile.get("project_description", ""),
            " ".join(profile["knowledge_registry"]["modules"]),
            " ".join(profile["knowledge_registry"]["flows"]),
        ]
    ).lower()
    keywords: list[str] = []
    for keyword in [
        "fault",
        "event",
        "telemetry",
        "health",
        "firmware",
        "upgrade",
        "device",
        "monitoring",
        "outage",
        "analytics",
        "dashboard",
        "authentication",
        "booking",
        "payment",
        "order",
        "meter",
        "field",
        "inspection",
        "otp",
        "login",
        "token",
        "session",
        "sms",
        "auth",
    ]:
        if keyword in text:
            keywords.append(keyword)
    return _unique(keywords)


DOMAIN_TERMS = [
    "Fault Event",
    "Telemetry",
    "Device Health",
    "Outage",
    "Recloser",
    "Firmware",
    "Asset Health",
    "Operations User",
    "Field Technician",
]


GENERIC_CONTENT_MARKERS = [
    "visible and testable",
    "complete workflow",
    "reviewable capability",
    "workflow is covered",
    "flow is covered",
    "validate feature",
    "implement feature",
    "generic dashboard",
    "business software",
]


def _generation_review(
    profile: dict[str, Any],
    artifacts: list[dict[str, Any]],
    preferred_modules: list[str] | None = None,
    keywords: list[str] | None = None,
) -> dict[str, Any]:
    registry = profile.get("knowledge_registry") or {}
    development_standards = profile.get("development_standards") or {}
    modules = _unique(preferred_modules or _extract_artifact_values(artifacts, ["impacted_modules", "affected_modules", "modules"]) or _string_list(registry.get("modules"))[:5])
    flows = _unique(_extract_artifact_values(artifacts, ["impacted_flows", "affected_flows", "flows"]) or _string_list(registry.get("flows"))[:5])
    applications = _unique(_extract_application_names_from_artifacts(artifacts) or _application_names(profile)[:5])
    standards = _unique([*_flatten_standards(development_standards), *registry.get("standards", [])])[:6]
    text = _artifact_text(artifacts)
    lowered = text.lower()
    keyword_set = set(keywords or [])
    domain_matches = [term for term in DOMAIN_TERMS if term.lower() in lowered or any(token in term.lower() for token in keyword_set)]
    generic_hits = [marker for marker in GENERIC_CONTENT_MARKERS if marker in lowered]
    module_hits = [module for module in modules if module.lower() in lowered]
    flow_hits = [flow for flow in flows if flow.lower() in lowered]
    knowledge_usage = 40
    if modules:
        knowledge_usage += 20
    if flows:
        knowledge_usage += 20
    if standards:
        knowledge_usage += 10
    if applications:
        knowledge_usage += 10
    module_coverage = int((len(module_hits) / len(modules)) * 100) if modules else 0
    flow_coverage = int((len(flow_hits) / len(flows)) * 100) if flows else 0
    domain_specificity = min(100, 35 + len(domain_matches) * 12 + len(keyword_set & {"fault", "telemetry", "health", "outage", "firmware", "device"}) * 8)
    generic_risk = min(100, len(generic_hits) * 20)
    quality_score = max(0, min(100, round((knowledge_usage + module_coverage + flow_coverage + domain_specificity + (100 - generic_risk)) / 5)))
    return {
        "modules_used": modules,
        "flows_used": flows,
        "standards_used": standards,
        "applications_used": applications,
        "domain_terms_used": _unique(domain_matches),
        "quality_scores": {
            "knowledge_usage": min(100, knowledge_usage),
            "module_coverage": module_coverage,
            "flow_coverage": flow_coverage,
            "domain_specificity": domain_specificity,
            "generic_content_risk": generic_risk,
            "overall": quality_score,
        },
        "generic_content_markers": generic_hits,
        "quality_gate": "passed" if quality_score >= 75 and generic_risk < 40 else "needs_review",
    }


def _artifact_text(artifacts: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        for key, value in artifact.items():
            if isinstance(value, str):
                chunks.append(value)
            elif isinstance(value, list):
                chunks.extend(str(item) for item in value if not isinstance(item, dict))
                for item in value:
                    if isinstance(item, dict):
                        chunks.append(_artifact_text([item]))
            elif isinstance(value, dict):
                chunks.append(_artifact_text([value]))
    return " ".join(chunks)


def _extract_artifact_values(artifacts: list[dict[str, Any]], keys: list[str]) -> list[str]:
    values: list[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        for key in keys:
            values.extend(_string_list(artifact.get(key)))
        for value in artifact.values():
            if isinstance(value, dict):
                values.extend(_extract_artifact_values([value], keys))
            elif isinstance(value, list):
                values.extend(_extract_artifact_values([item for item in value if isinstance(item, dict)], keys))
    return _unique(values)


def _extract_application_names_from_artifacts(artifacts: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    raw = _extract_artifact_values(artifacts, ["impacted_applications", "affected_applications", "applications"])
    for item in raw:
        if isinstance(item, str):
            names.append(item)
    return _unique(names)


CAPABILITY_TAXONOMY = [
    "Operational Awareness",
    "Fault Monitoring",
    "Alert Management",
    "Outage Investigation",
    "Reliability Analytics",
    "Maintenance",
    "Configuration",
    "Commissioning",
    "Asset Health",
    "Compliance",
    "Telemetry",
    "Device Management",
    "Firmware Management",
    "Diagnostics",
    "Outage Response",
    "Field Operations",
]


def _item_id(item: dict[str, Any], fallback: str = "") -> str:
    return _clean_text(item.get("id") or item.get("work_item_id") or item.get("draft_id") or item.get("title")) or fallback


def _source_intent(selection: dict[str, Any], fallback: list[str] | None = None) -> list[str]:
    intent = selection.get("intent") if isinstance(selection.get("intent"), dict) else {}
    return _string_list(intent.get("keywords")) or _string_list(fallback)[:16]


def _lineage_metadata(
    parent: dict[str, Any],
    parent_type: str,
    derived_from: str,
    selection: dict[str, Any],
    confidence: float = 0.82,
) -> dict[str, Any]:
    return {
        "parent_id": _item_id(parent),
        "parent_type": parent_type,
        "derived_from": derived_from,
        "source_intent": _source_intent(selection),
        "selected_modules": _selection_names(selection, "relevant_modules"),
        "selected_flows": _selection_names(selection, "relevant_flows"),
        "rejected_context": selection.get("rejected_context", []),
        "confidence": confidence,
    }


def _supported_capabilities_for_intent(keywords: list[str], profile: dict[str, Any]) -> list[str]:
    allowed = _capabilities_for_epic(keywords, profile)
    corpus = " ".join([*keywords, *profile["knowledge_registry"].get("modules", []), *profile["knowledge_registry"].get("flows", [])]).lower()
    if any(token in corpus for token in ["operation", "dashboard", "fault", "outage", "event", "asset", "reliability"]):
        allowed = _unique([*allowed, "Operational Awareness", "Fault Monitoring", "Alert Management", "Outage Investigation", "Reliability Analytics", "Asset Health"])
    if "firmware" not in corpus:
        allowed = [capability for capability in allowed if capability not in {"Firmware Management", "Maintenance", "Compliance"}]
    if not any(token in corpus for token in ["login", "token", "session", "auth", "register", "registration"]):
        allowed = [capability for capability in allowed if capability not in {"Commissioning", "Device Management"}]
    return [capability for capability in _unique(allowed) if capability in CAPABILITY_TAXONOMY]


def _capability_decomposition(epic_title: str, business_goal: str, keywords: list[str], profile: dict[str, Any]) -> dict[str, Any]:
    users = _users_for_profile(profile)
    problems = _user_problems_for_epic(keywords, profile)
    capabilities = _supported_capabilities_for_intent(keywords, profile)
    rejected: list[dict[str, Any]] = []
    feature_candidates = [_feature_from_capability(capability, keywords, users, profile) for capability in capabilities]
    features = _validate_capability_features(
        feature_candidates,
        epic_title,
        business_goal,
        keywords,
        profile,
        fallback_features=[],
        diagnostics={"rejected_similar_features": rejected},
    )
    if len(features) < 5:
        supplement = [_feature_from_capability(capability, keywords, users, profile) for capability in _supported_capabilities_for_intent(keywords, profile) if capability not in capabilities]
        features = _validate_capability_features(
            [*features, *supplement],
            epic_title,
            business_goal,
            keywords,
            profile,
            fallback_features=features,
            diagnostics={"rejected_similar_features": rejected},
        )
    return {
        "user_problems": problems,
        "capability_categories": [feature["capability"] for feature in features],
        "recommended_features": features[:10],
        "diagnostics": {
            "capability_categories_identified": [feature["capability"] for feature in features[:10]],
            "user_problems_identified": problems,
            "rejected_similar_features": rejected,
            "final_feature_count": min(len(features), 10),
        },
    }


def _primary_epic_goal(epic_analysis: dict[str, Any], title: str, description: str, profile: dict[str, Any]) -> str:
    goals = _string_list(epic_analysis.get("businessGoals") or epic_analysis.get("business_goals"))
    if goals:
        return goals[0]
    return _sentence(f"Improve {title}", description or profile["project_description"])


def _apply_capability_discovery_to_epic_analysis(epic_analysis: dict[str, Any], capability_context: dict[str, Any]) -> dict[str, Any]:
    discovery = capability_context.get("capabilityDiscovery") if isinstance(capability_context.get("capabilityDiscovery"), dict) else {}
    recommendations = discovery.get("recommendations") if isinstance(discovery.get("recommendations"), list) else []
    accepted = [item for item in recommendations if isinstance(item, dict) and item.get("accepted") and _clean_text(item.get("name"))]
    if not accepted:
        return epic_analysis

    rejected = capability_context.get("rejectedCapabilities") if isinstance(capability_context.get("rejectedCapabilities"), list) else []
    required_candidates = [
        CapabilityCandidate(
            name=_clean_text(item.get("name")),
            reason=_clean_text(item.get("reason")) or f"{_clean_text(item.get('name'))} was selected by capability discovery.",
            confidence=float(item.get("confidence") or 0.0),
            repository_evidence=_string_list(item.get("evidence")),
        ).to_dict()
        for item in accepted[:6]
    ]
    rejected_candidates = [
        CapabilityCandidate(
            name=_clean_text(item.get("name")),
            reason=_clean_text(item.get("reason")) or f"{_clean_text(item.get('name'))} was rejected by capability discovery.",
            confidence=float(item.get("confidence") or 0.0),
            repository_evidence=[],
        ).to_dict()
        for item in rejected
        if isinstance(item, dict) and _clean_text(item.get("name"))
    ]
    capability_priority = [
        CapabilityPriority(
            name=_clean_text(item.get("name")),
            priority=_capability_priority_label(index),
            reason=f"Ranked by capability discovery score {int(item.get('final', 0) or item.get('overall_score', 0) or 0)} with intent, repository, knowledge, and memory evidence.",
            rank=index,
        ).to_dict()
        for index, item in enumerate(accepted[:6], start=1)
    ]
    updated = dict(epic_analysis)
    updated["requiredCapabilities"] = required_candidates
    updated["required_capabilities"] = required_candidates
    updated["excludedCapabilities"] = rejected_candidates
    updated["excluded_capabilities"] = rejected_candidates
    updated["capabilityPriority"] = capability_priority
    updated["capability_priority"] = capability_priority
    boundary = updated.get("planningBoundary") if isinstance(updated.get("planningBoundary"), dict) else {}
    in_scope = [_clean_text(item.get("name")) for item in accepted[:6] if _clean_text(item.get("name"))]
    out_of_scope = _unique([
        *_string_list(boundary.get("outOfScope") or boundary.get("out_of_scope")),
        *[_clean_text(item.get("name")) for item in rejected if isinstance(item, dict) and _clean_text(item.get("name"))],
    ])
    updated["planningBoundary"] = {
        "inScope": in_scope,
        "outOfScope": out_of_scope,
        "in_scope": in_scope,
        "out_of_scope": out_of_scope,
    }
    updated["planning_boundary"] = updated["planningBoundary"]
    diagnostics = dict(updated.get("diagnostics") or {})
    diagnostics["capability_discovery_applied"] = True
    diagnostics["capability_discovery_threshold"] = discovery.get("threshold")
    diagnostics["capability_discovery_selected"] = len(required_candidates)
    diagnostics["capability_discovery_candidates"] = len(recommendations)
    diagnostics["capability_discovery_report"] = recommendations
    updated["diagnostics"] = diagnostics
    updated["confidence"] = round(max(float(updated.get("confidence") or 0), float(capability_context.get("confidence") or 0)), 2)
    return updated


def _capability_priority_label(rank: int) -> str:
    if rank <= 2:
        return "Critical"
    if rank <= 4:
        return "High"
    if rank <= 6:
        return "Medium"
    return "Low"


def _capability_review_for_feature(feature: dict[str, Any], reviews: list[dict[str, Any]]) -> dict[str, Any]:
    capability = _clean_text(feature.get("capability_category") or feature.get("capability"))
    for review in reviews:
        if isinstance(review, dict) and _clean_text(review.get("capabilityName")) == capability:
            return review
    return {}


def _option_parent_dna(options: dict[str, Any] | None) -> dict[str, Any] | None:
    options = options or {}
    dna = options.get("parent_dna") or options.get("parentDNA") or options.get("work_item_dna")
    return dna if isinstance(dna, dict) else None


def _work_item_from_dna(work_item: dict[str, Any], dna: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(dna, dict) or not dna:
        return work_item
    evidence = dna.get("repositoryEvidence") if isinstance(dna.get("repositoryEvidence"), dict) else {}
    boundary = dna.get("planningBoundary") if isinstance(dna.get("planningBoundary"), dict) else {}
    parts = [
        _clean_text(dna.get("capability")),
        _clean_text(dna.get("businessOutcome")),
        " ".join(_string_list(dna.get("responsibilities"))),
        " ".join(_string_list(dna.get("acceptanceThemes"))),
        " ".join(_string_list(boundary.get("inScope"))),
    ]
    return {
        **work_item,
        "description": _clean_text(" ".join(parts)) or _clean_text(work_item.get("description")),
        "business_goal": (_string_list(dna.get("businessGoals"))[:1] or [work_item.get("business_goal") or ""])[0],
        "business_outcome": dna.get("businessOutcome") or work_item.get("business_outcome"),
        "capability": dna.get("capability") or work_item.get("capability"),
        "responsibilities": _string_list(dna.get("responsibilities")) or _string_list(work_item.get("responsibilities")),
        "acceptance_criteria": _string_list(work_item.get("acceptance_criteria")) or _string_list(dna.get("acceptanceThemes")),
        "affected_modules": _string_list(evidence.get("modules")) or _string_list(work_item.get("affected_modules")),
        "affected_flows": _string_list(evidence.get("flows")) or _string_list(work_item.get("affected_flows")),
        "affected_applications": _string_list(evidence.get("applications")) or _string_list(work_item.get("affected_applications")),
        "files": _string_list(evidence.get("files")) or _string_list(work_item.get("files")),
        "dependencies": _string_list(dna.get("dependencies")) or _string_list(work_item.get("dependencies")),
        "constraints": _string_list(dna.get("constraints")) or _string_list(work_item.get("constraints")),
        "risks": _string_list(dna.get("risks")) or _string_list(work_item.get("risks")),
        "out_of_scope": _string_list(boundary.get("outOfScope")),
    }


def _with_selected_evidence(work_item: dict[str, Any], modules: list[str], flows: list[str], dependencies: list[str], risks: list[str]) -> dict[str, Any]:
    return {
        **work_item,
        "affected_modules": modules or _string_list(work_item.get("affected_modules")),
        "affected_flows": flows or _string_list(work_item.get("affected_flows")),
        "dependencies": dependencies or _string_list(work_item.get("dependencies")),
        "risks": risks or _string_list(work_item.get("risks")),
    }


def _with_child_dna(
    item: dict[str, Any],
    work_item_type: str,
    parent_dna: dict[str, Any],
    profile: dict[str, Any],
    *,
    capability_review: dict[str, Any] | None = None,
    validation_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    child_dna = generateDNA(
        item,
        work_item_type,
        profile=profile,
        capability_review=capability_review,
        parent_dna=parent_dna,
        validation_report=validation_report,
    )
    validation = validateDNA(parent_dna, child_dna)
    return {
        **item,
        "work_item_dna": child_dna,
        "dna_validation": validation,
        "dna_diagnostics": _dna_diagnostics(parent_dna, child_dna),
        "status": "blocked_by_dna_validation" if not validation["valid"] else item.get("status", "preview"),
    }


def _dna_diagnostics(parent_dna: dict[str, Any] | None, child_dna: dict[str, Any]) -> dict[str, Any]:
    evidence = child_dna.get("repositoryEvidence") if isinstance(child_dna.get("repositoryEvidence"), dict) else {}
    validation = validateDNA(parent_dna, child_dna)
    diff = compareDNA(parent_dna, child_dna) if parent_dna else {"changes": {}}
    inherited_fields = []
    extended_fields = []
    for field in ["businessGoals", "businessOutcome", "capability", "planningBoundary", "dependencies", "constraints", "engineeringStandards", "acceptanceThemes"]:
        if parent_dna and child_dna.get(field) == parent_dna.get(field):
            inherited_fields.append(field)
        elif child_dna.get(field):
            extended_fields.append(field)
    return {
        "dnaId": child_dna.get("dnaId"),
        "parentDNA": child_dna.get("parentDNA"),
        "dnaVersion": child_dna.get("version"),
        "inheritanceDepth": _dna_inheritance_depth(child_dna),
        "dnaValidationStatus": validation["status"],
        "inheritedFields": inherited_fields,
        "extendedFields": extended_fields,
        "rejectedContradictions": validation["issues"],
        "repositoryEvidenceCount": sum(len(_string_list(evidence.get(key))) for key in ["modules", "flows", "applications", "services", "files"]),
        "modules": _string_list(evidence.get("modules")),
        "flows": _string_list(evidence.get("flows")),
        "files": _string_list(evidence.get("files")),
        "confidence": child_dna.get("confidence"),
        "validationScore": child_dna.get("validationSummary", {}).get("score") if isinstance(child_dna.get("validationSummary"), dict) else 0,
        "changesSinceParent": diff.get("changes", {}),
    }


def _dna_inheritance_depth(dna: dict[str, Any]) -> int:
    depth = 0
    current = dna
    seen: set[str] = set()
    while isinstance(current, dict) and current.get("parentDNA") and current.get("parentDNA") not in seen:
        parent_id = str(current.get("parentDNA"))
        seen.add(parent_id)
        depth += 1
        break
    return depth


def _dna_error_response(payload: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    return {
        **payload,
        "blocked": True,
        "status": "blocked_by_dna_validation",
        "error": "Work Item DNA validation failed.",
        "failure_reason": "dna_validation_failed",
        "dna_validation": validation,
        "provider_used": "deterministic_fallback",
        "source": "dna_validation",
        "phi_status": "skipped",
        "fallback_used": False,
        "fallback_reason": "DNA validation blocked generation before provider execution.",
    }


def _basic_validation_score(modules: list[str], flows: list[str]) -> int:
    score = 70
    if modules:
        score += 10
    if flows:
        score += 10
    return min(score, 95)


def _capability_decomposition_from_epic_analysis(
    epic_title: str,
    business_goal: str,
    keywords: list[str],
    profile: dict[str, Any],
    epic_analysis: dict[str, Any],
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    options = options or {}
    users = _users_for_profile(profile)
    problems = _string_list(epic_analysis.get("businessProblems") or epic_analysis.get("business_problems")) or _user_problems_for_epic(keywords, profile)
    required = epic_analysis.get("requiredCapabilities") or epic_analysis.get("required_capabilities") or []
    required_capabilities = [_clean_text(item.get("name")) for item in required if isinstance(item, dict) and _clean_text(item.get("name"))]
    boundary = epic_analysis.get("planningBoundary") if isinstance(epic_analysis.get("planningBoundary"), dict) else {}
    out_of_scope = set(_string_list(boundary.get("outOfScope") or boundary.get("out_of_scope")))
    approved_capabilities = _approved_capabilities_from_options(options)
    capabilities = [capability for capability in required_capabilities if capability in CAPABILITY_TAXONOMY and capability not in out_of_scope]
    if approved_capabilities:
        capabilities = [capability for capability in capabilities if capability in approved_capabilities]
    feature_candidates = [_feature_from_capability(capability, keywords, users, profile) for capability in capabilities]
    rejected: list[dict[str, Any]] = []
    features = _validate_capability_features(
        feature_candidates,
        epic_title,
        business_goal,
        keywords,
        profile,
        fallback_features=[],
        diagnostics={"rejected_similar_features": rejected},
    )
    priority_by_name = {
        _clean_text(item.get("name")): item
        for item in (epic_analysis.get("capabilityPriority") or epic_analysis.get("capability_priority") or [])
        if isinstance(item, dict)
    }
    for feature in features:
        priority = priority_by_name.get(_clean_text(feature.get("capability")))
        if priority:
            feature["capability_priority"] = priority
        feature["derived_from_epic_analysis"] = True
    return {
        "user_problems": problems,
        "capability_categories": [feature["capability"] for feature in features],
        "recommended_features": features[:10],
        "diagnostics": {
            "source": "epic_analysis_intelligence",
            "capability_categories_identified": [feature["capability"] for feature in features[:10]],
            "required_capabilities": required_capabilities,
            "excluded_capabilities": _string_list(boundary.get("outOfScope") or boundary.get("out_of_scope")),
            "user_problems_identified": problems,
            "rejected_similar_features": rejected,
            "final_feature_count": min(len(features), 10),
            "feature_generation_mode": "one_capability_at_a_time",
            "approved_capability_count": len(approved_capabilities),
            "feature_generation_steps": [
                {
                    "capability": feature.get("capability"),
                    "feature_title": feature.get("title"),
                    "status": "generated_from_epic_analysis",
                }
                for feature in features[:10]
            ],
        },
    }


def _approved_capabilities_from_options(options: dict[str, Any]) -> set[str]:
    explicit = _string_list(options.get("approved_capabilities") or options.get("approvedCapabilityIds"))
    reviews = options.get("capability_review") or options.get("capabilityReview")
    if isinstance(reviews, list):
        explicit.extend(
            _clean_text(item.get("capabilityName") or item.get("capability_name") or item.get("name"))
            for item in reviews
            if isinstance(item, dict) and _clean_text(item.get("status")).lower() == "approved"
        )
    return {item for item in explicit if item}


def _capabilities_for_epic(keywords: list[str], profile: dict[str, Any]) -> list[str]:
    selected: list[str] = []
    keyword_set = set(keywords)
    modules_text = " ".join(profile["knowledge_registry"]["modules"]).lower()
    flows_text = " ".join(profile["knowledge_registry"]["flows"]).lower()
    corpus = " ".join([*keywords, modules_text, flows_text])
    if {"fault", "event", "monitoring"} & keyword_set or "fault" in corpus:
        selected.extend(["Operational Awareness", "Fault Monitoring", "Alert Management", "Outage Investigation", "Reliability Analytics"])
    if "outage" in corpus:
        selected.extend(["Outage Investigation", "Outage Response", "Field Operations"])
    if {"telemetry", "device"} & keyword_set or "telemetry" in corpus:
        selected.extend(["Telemetry", "Asset Health", "Diagnostics"])
    if {"firmware", "upgrade"} & keyword_set or "firmware" in corpus:
        selected.extend(["Firmware Management", "Maintenance", "Compliance"])
    if "report" in corpus or "analytics" in corpus:
        selected.extend(["Reliability Analytics"])
    if "configuration" in corpus or "settings" in corpus:
        selected.extend(["Configuration"])
    if "commission" in corpus or "onboard" in corpus:
        selected.extend(["Commissioning"])
    if not selected:
        selected.extend(["Operational Awareness", "Configuration", "Reliability Analytics", "Alert Management"])
    return [capability for capability in _unique(selected) if capability in CAPABILITY_TAXONOMY][:10]


def _user_problems_for_epic(keywords: list[str], profile: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    keyword_set = set(keywords)
    if {"fault", "event", "outage"} & keyword_set:
        problems.extend([
            "Operators need to detect critical events before they become outages.",
            "Field teams need enough event context to respond without manual investigation delays.",
            "Managers need reliability trends to prioritize operational improvements.",
        ])
    if {"telemetry", "health", "device"} & keyword_set:
        problems.append("Operators need device health signals correlated with operational events.")
    if {"firmware", "upgrade"} & keyword_set:
        problems.append("Teams need firmware rollout visibility and exception handling.")
    if not problems:
        domain = profile.get("domain") or "the product"
        problems.extend([
            f"Users need clearer operational visibility across {domain}.",
            "Teams need independently deliverable capabilities instead of one large ambiguous initiative.",
        ])
    return _unique(problems)


def _feature_from_capability(capability: str, keywords: list[str], users: list[str], profile: dict[str, Any]) -> dict[str, Any]:
    title = _capability_feature_title(capability, keywords, profile)
    modules = _modules_for_capability(capability, keywords, profile)
    flows = _flows_for_capability(capability, keywords, profile)
    applications, application_relevance = _relevant_applications_for_capability(capability, profile)
    outcome = _business_outcome_for_capability(capability, keywords)
    user_problem = _user_problem_for_capability(capability, keywords)
    primary_users = _users_for_capability(capability, users)
    return {
        "title": title,
        "description": _feature_description(title, capability, outcome, primary_users, modules, flows, profile, applications),
        "capability": capability,
        "business_outcome": outcome,
        "user_problem": user_problem,
        "primary_users": primary_users,
        "impacted_applications": [f"{app['name']} ({app['type']})" for app in applications],
        "application_relevance": application_relevance,
        "impacted_modules": modules,
        "impacted_flows": flows,
        "reasoning": f"{title} is a separate {capability.lower()} capability because it solves '{user_problem}' and can be delivered independently against {', '.join(modules) or 'the affected modules'}.",
    }


def _capability_feature_title(capability: str, keywords: list[str], profile: dict[str, Any]) -> str:
    corpus = " ".join([*keywords, *profile["knowledge_registry"]["modules"], *profile["knowledge_registry"]["flows"]]).lower()
    fault_context = "fault" in corpus or "outage" in corpus
    titles = {
        "Fault Monitoring": "Critical Fault Detection" if fault_context else "Operational Signal Detection",
        "Alert Management": "Operator Alerting" if fault_context else "Operational Alert Management",
        "Outage Investigation": "Outage Investigation Workspace" if "outage" in corpus or fault_context else "Issue Investigation Workspace",
        "Reliability Analytics": "Reliability Trend Analytics" if fault_context or "asset" in corpus else "Operational Trend Analytics",
        "Maintenance": "Maintenance Exception Handling",
        "Configuration": "Operational Rule Configuration",
        "Commissioning": "Device Commissioning Readiness",
        "Notifications": "Escalation Notifications" if fault_context else "Workflow Notifications",
        "Asset Health": "Device Health Correlation",
        "Compliance": "Operational Compliance Evidence",
        "Telemetry": "Telemetry Quality Assurance",
        "Device Management": "Device State Control",
        "Firmware Management": "Firmware Rollout Visibility",
        "Diagnostics": "Remote Diagnostic Support",
        "Operational Awareness": "Live Operations Awareness",
        "Outage Response": "Field Response Support",
        "Field Operations": "Field Response Coordination",
    }
    return titles.get(capability, f"{capability} Capability")


def _modules_for_capability(capability: str, keywords: list[str], profile: dict[str, Any]) -> list[str]:
    modules = profile["knowledge_registry"]["modules"]
    lowered = {module.lower(): module for module in modules}
    preferred: dict[str, list[str]] = {
        "Operational Awareness": ["report", "telemetry", "dashboard"],
        "Fault Monitoring": ["fault", "telemetry", "health"],
        "Alert Management": ["fault", "notification", "audit"],
        "Outage Investigation": ["fault", "telemetry", "health", "investigation"],
        "Reliability Analytics": ["report", "analytics", "asset", "telemetry"],
        "Asset Health": ["asset", "telemetry", "health"],
        "Telemetry": ["telemetry"],
        "Device Management": ["device"],
        "Firmware Management": ["firmware"],
        "Diagnostics": ["diagnostic", "telemetry", "device"],
        "Outage Response": ["fault", "device", "report"],
        "Field Operations": ["device", "fault"],
    }
    selected = []
    for token in preferred.get(capability, []):
        selected.extend(value for key, value in lowered.items() if token in key)
    if not selected:
        selected = modules[:2]
    return _unique(selected)[:3]


def _flows_for_capability(capability: str, keywords: list[str], profile: dict[str, Any]) -> list[str]:
    flows = profile["knowledge_registry"]["flows"]
    lowered = {flow.lower(): flow for flow in flows}
    preferred: dict[str, list[str]] = {
        "Operational Awareness": ["live", "status", "operation", "dashboard"],
        "Fault Monitoring": ["fault", "detail", "event"],
        "Alert Management": ["alert", "acknowledgement", "escalation"],
        "Outage Investigation": ["investigation", "timeline", "health"],
        "Reliability Analytics": ["trend", "analytics", "reliability"],
        "Asset Health": ["health", "device"],
        "Telemetry": ["telemetry", "health"],
        "Firmware Management": ["firmware", "upgrade"],
        "Outage Response": ["outage", "investigation"],
        "Field Operations": ["field", "outage"],
    }
    selected = []
    for token in preferred.get(capability, []):
        selected.extend(value for key, value in lowered.items() if token in key)
    if not selected:
        selected = flows[:2]
    return _unique(selected)[:3]


def _business_outcome_for_capability(capability: str, keywords: list[str]) -> str:
    outcomes = {
        "Fault Monitoring": "Faster detection of critical operating conditions.",
        "Alert Management": "Reduced response time through actionable operator notifications.",
        "Outage Investigation": "Faster root-cause analysis and outage triage.",
        "Reliability Analytics": "Better prioritization through reliability trends and operational insight.",
        "Asset Health": "Improved operational decisions through correlated device health.",
        "Telemetry": "Higher confidence in operational decisions through trusted telemetry quality.",
        "Firmware Management": "Safer rollout operations with visible upgrade status and exceptions.",
        "Field Operations": "Better field execution through focused response context.",
        "Operational Awareness": "Shared operational context across live events, assets, and response status.",
        "Outage Response": "Faster coordination from outage detection through field response.",
    }
    return outcomes.get(capability, f"Improved {capability.lower()} outcomes for the business.")


def _user_problem_for_capability(capability: str, keywords: list[str]) -> str:
    problems = {
        "Fault Monitoring": "critical events are not visible early enough",
        "Alert Management": "operators do not know which events require immediate action",
        "Outage Investigation": "teams lose time correlating event context during outages",
        "Reliability Analytics": "leaders lack trend evidence for prioritization",
        "Asset Health": "device health is disconnected from event review",
        "Telemetry": "telemetry quality issues reduce trust in decisions",
        "Firmware Management": "firmware rollout exceptions are hard to track",
        "Field Operations": "field teams lack response-ready context",
        "Operational Awareness": "live operational status is spread across disconnected views",
        "Outage Response": "outage response lacks a shared operational handoff",
    }
    return problems.get(capability, f"{capability.lower()} work is not structured as an independent capability")


def _users_for_capability(capability: str, users: list[str]) -> list[str]:
    defaults = {
        "Alert Management": ["Operations User", "Field Technician"],
        "Outage Investigation": ["Operations User", "Field Technician"],
        "Reliability Analytics": ["Operations Manager"],
        "Field Operations": ["Field Technician"],
        "Outage Response": ["Operations User", "Field Technician"],
    }
    return defaults.get(capability, users[:1] or ["Operations User"])


def _relevant_applications_for_capability(capability: str, profile: dict[str, Any], threshold: int = 50) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    apps = _dedupe_applications(profile["applications"] or profile["knowledge_registry"]["applications"])
    if not apps:
        apps = _default_applications_for_profile(profile)
    scored = []
    for app in apps:
        score = _application_relevance_score(capability, app)
        if score >= threshold:
            scored.append({**app, "score": score})
    if not scored and apps:
        scored = [{**apps[0], "score": _application_relevance_score(capability, apps[0])}]
    return [{"name": item["name"], "type": item["type"]} for item in scored], scored


def _default_applications_for_profile(profile: dict[str, Any]) -> list[dict[str, str]]:
    domain_text = _clean_text(profile.get("domain") or profile.get("project_description")).lower()
    if any(token in domain_text for token in ["utility", "grid", "meter", "fault", "telemetry", "field"]):
        return [
            {"name": "Operations Dashboard", "type": "Web Portal"},
            {"name": "Mobile Application", "type": "Mobile"},
            {"name": "Backend API", "type": "Backend"},
            {"name": "Analytics Platform", "type": "Analytics"},
            {"name": "Firmware", "type": "Firmware"},
        ]
    return [
        {"name": "Web Application", "type": "Web Portal"},
        {"name": "Backend API", "type": "Backend"},
    ]


def _application_relevance_score(capability: str, app: dict[str, str]) -> int:
    text = f"{app.get('name', '')} {app.get('type', '')}".lower()
    if "dashboard" in text or "portal" in text or "web" in text:
        category = "dashboard"
    elif "backend" in text or "api" in text:
        category = "backend"
    elif "mobile" in text:
        category = "mobile"
    elif "analytics" in text:
        category = "analytics"
    elif "firmware" in text:
        category = "firmware"
    else:
        category = "other"
    scores = {
        "Fault Monitoring": {"dashboard": 100, "mobile": 75, "backend": 90, "analytics": 25, "firmware": 10, "other": 40},
        "Alert Management": {"dashboard": 100, "mobile": 95, "backend": 90, "analytics": 30, "firmware": 10, "other": 40},
        "Outage Investigation": {"dashboard": 100, "mobile": 75, "backend": 90, "analytics": 45, "firmware": 10, "other": 40},
        "Reliability Analytics": {"analytics": 100, "dashboard": 90, "backend": 80, "mobile": 30, "firmware": 10, "other": 35},
        "Operational Awareness": {"dashboard": 95, "mobile": 80, "backend": 80, "analytics": 60, "firmware": 10, "other": 45},
        "Outage Response": {"mobile": 90, "dashboard": 85, "backend": 85, "analytics": 50, "firmware": 15, "other": 45},
        "Firmware Management": {"firmware": 100, "backend": 85, "dashboard": 70, "mobile": 45, "analytics": 30, "other": 35},
    }
    return scores.get(capability, {"dashboard": 75, "mobile": 65, "backend": 70, "analytics": 55, "firmware": 40, "other": 45}).get(category, 45)


def _relevance_scores_for_items(capability: str, items: list[str], kind: str) -> list[dict[str, Any]]:
    return [{"name": item, "score": _item_relevance_score(capability, item, kind)} for item in items]


def _filter_relevant_items(capability: str, items: list[str], kind: str, threshold: int = 50) -> tuple[list[str], list[dict[str, Any]]]:
    scored = _relevance_scores_for_items(capability, _unique(items), kind)
    relevant = [item for item in scored if int(item.get("score") or 0) >= threshold]
    if not relevant and scored:
        relevant = [max(scored, key=lambda item: int(item.get("score") or 0))]
    return [str(item["name"]) for item in relevant], relevant


def _item_relevance_score(capability: str, item: str, kind: str) -> int:
    text = item.lower()
    preferred = {
        "Fault Monitoring": ["fault", "event", "telemetry", "health", "detail", "review"],
        "Alert Management": ["alert", "acknowledgement", "escalation", "notification", "fault"],
        "Outage Investigation": ["investigation", "outage", "fault", "timeline", "health"],
        "Reliability Analytics": ["analytics", "trend", "report", "reliability", "metrics"],
        "Operational Awareness": ["live", "status", "operation", "monitoring", "dashboard"],
        "Outage Response": ["outage", "field", "response", "fault", "device"],
        "Asset Health": ["asset", "health", "device", "telemetry"],
        "Telemetry": ["telemetry", "ingestion", "quality", "device"],
        "Firmware Management": ["firmware", "upgrade", "rollout", "device"],
    }
    tokens = preferred.get(capability, [])
    score = 25
    for token in tokens:
        if token in text:
            score += 30 if kind == "flow" else 25
    return min(score, 100)


def _feature_description(
    name: str,
    capability: str,
    outcome: str,
    users: list[str],
    modules: list[str],
    flows: list[str],
    profile: dict[str, Any],
    applications: list[dict[str, str]] | None = None,
) -> str:
    user_text = ", ".join(users[:3]) or "operations users"
    module_text = ", ".join(modules[:3]) or "the selected project modules"
    flow_text = ", ".join(flows[:3]) or "the selected delivery flows"
    selected_applications = applications or []
    application_text = ", ".join(f"{app['name']} ({app['type']})" for app in selected_applications[:3]) or "the selected application boundary"
    problem = _user_problem_for_capability(capability, [])
    sentences = [
        f"{name} gives {user_text} a focused {capability.lower()} capability for situations where {problem}.",
        f"It should connect {module_text} through {flow_text}, with user-facing touchpoints in {application_text}.",
        f"The feature should provide clear review states, actionable operational context, permission-aware access, and validation paths that support the approved outcome.",
        f"Expected value: {outcome}",
    ]
    return " ".join(sentences)


def _feature_business_goal(name: str, capability: str) -> str:
    goals = {
        "Fault Monitoring": "Allow operators to identify critical LineDefender fault events immediately after occurrence.",
        "Alert Management": "Ensure operators and field technicians receive actionable notifications for events requiring response.",
        "Outage Investigation": "Help operations teams investigate outages with correlated event, device, and status context.",
        "Reliability Analytics": "Give operations managers reliability trends that support prioritization and planning.",
        "Asset Health": "Correlate device health signals with operational events for better triage.",
        "Telemetry": "Expose telemetry quality and freshness so users can trust operational decisions.",
        "Firmware Management": "Make firmware rollout status and exceptions visible before they affect operations.",
        "Operational Awareness": "Provide a shared live view of operational events, assets, and response status.",
        "Outage Response": "Coordinate outage response from detection through field action.",
        "Field Operations": "Give field teams response-ready context before they act on an issue.",
    }
    return goals.get(capability, f"Define an independently deliverable capability for {name}.")


def _feature_acceptance_criteria(name: str, capability: str, outcome: str, modules: list[str], flows: list[str]) -> list[str]:
    criteria_by_capability = {
        "Fault Monitoring": [
            "Operator can view all active critical fault events in a single list.",
            "Event list displays Device ID, Fault Type, Severity, Event Time, and Current Status.",
            "Critical events are visually differentiated from warning and informational events.",
            "Newly ingested critical events appear in the event list within 60 seconds.",
            "Operator can open detailed event information from the event list.",
            "System displays a clear unavailable-data message when event data cannot be loaded.",
            "All event list and event detail access actions are audit logged.",
        ],
        "Alert Management": [
            "Operator receives an alert when a critical fault event is created.",
            "Alert displays Device ID, Fault Type, Severity, Event Time, and Recommended Action.",
            "Operator can acknowledge an alert and the acknowledgement is timestamped.",
            "Escalation status changes are visible within 60 seconds of update.",
            "Field technician can identify alerts assigned for field response.",
            "Duplicate alerts for the same active event are suppressed or grouped.",
        ],
        "Outage Investigation": [
            "Operator can open an outage investigation workspace from a fault event.",
            "Workspace shows related device, telemetry, event timeline, and current status.",
            "Operator can filter investigation events by severity, device, and time range.",
            "Workspace highlights missing telemetry or stale device status data.",
            "Investigation notes are saved with user and timestamp.",
            "Workspace preserves the investigation trail for audit review.",
        ],
        "Reliability Analytics": [
            "Operations manager can view reliability trends by device, fault type, and time period.",
            "Dashboard shows event counts, severity distribution, and response-time trends.",
            "User can compare current reliability trends against the previous period.",
            "Trend data can be filtered by module, flow, or impacted asset group.",
            "Dashboard indicates when analytics data is incomplete or delayed.",
        ],
        "Operational Awareness": [
            "Operator can view live operational status across active events and affected assets.",
            "Live view separates critical, warning, and normal operating states.",
            "Status updates refresh within 60 seconds of source data change.",
            "Operator can navigate from live status to related event details.",
            "Unavailable or stale status data is clearly identified.",
        ],
        "Outage Response": [
            "Operator can identify outage events requiring coordinated response.",
            "Response view shows impacted devices, current event status, and assigned owner.",
            "Field technician can see response instructions for assigned outage work.",
            "Status changes are captured with timestamp and user identity.",
            "Response history remains available after the outage is resolved.",
        ],
        "Asset Health": [
            "Operator can view device health status for affected assets.",
            "Health view displays Device ID, Health Score, Last Telemetry Time, Active Fault Count, and Current Status.",
            "Assets with degraded health are visually separated from healthy assets.",
            "Operator can open health details showing recent telemetry and related fault events.",
            "System identifies stale or missing health data with a clear message.",
            "Health status changes are retained with timestamp and source signal.",
        ],
        "Telemetry": [
            "Operator can view telemetry freshness and quality status for affected devices.",
            "Telemetry view displays Device ID, Last Reading Time, Signal Quality, Missing Reading Count, and Ingestion Status.",
            "Telemetry gaps older than the configured threshold are highlighted.",
            "User can filter telemetry quality by device, severity, and time range.",
            "System displays a clear message when telemetry is delayed or unavailable.",
            "Telemetry quality checks are logged with timestamp and evaluated rule.",
        ],
        "Firmware Management": [
            "Operator can view firmware rollout status by device and firmware version.",
            "Rollout view displays Device ID, Current Version, Target Version, Upgrade Status, and Last Attempt Time.",
            "Failed or stalled upgrades are visually differentiated from successful upgrades.",
            "Operator can open rollout details for failure reason and retry eligibility.",
            "System displays unavailable-device messaging when firmware status cannot be refreshed.",
            "Firmware status changes are audit logged with user or source identity.",
        ],
        "Field Operations": [
            "Field technician can view assigned response work with device, location, severity, and current status.",
            "Response details display required action, safety notes, and last known telemetry.",
            "Technician can update response status and add completion notes.",
            "Status changes are visible to operations users within 60 seconds.",
            "System handles offline or unavailable response data with a clear message.",
            "Field updates are saved with user identity, timestamp, and device reference.",
        ],
    }
    default_criteria = [
        f"User can complete the primary {name} action without manual data lookup.",
        f"Screen response displays identifier, status, timestamp, owner, and latest update for {name}.",
        f"User can filter {name} records by status, severity, and time range.",
        f"System handles unavailable data with a clear user-facing message.",
        f"Relevant actions are saved with user identity, timestamp, and affected record.",
        f"{name} updates are visible within 60 seconds of source data change.",
    ]
    criteria, _ = _reject_generic_acceptance_criteria(_unique(criteria_by_capability.get(capability, default_criteria)))
    return criteria


def _feature_dependencies(capability: str, modules: list[str], flows: list[str]) -> list[str]:
    dependencies = {
        "Fault Monitoring": ["Telemetry Service", "Event Repository", "Severity Classification Rules", "Audit Logging Service"],
        "Alert Management": ["Notification Service", "Event Repository", "User Assignment Service", "Audit Logging Service"],
        "Outage Investigation": ["Event Timeline Service", "Telemetry Service", "Device State Service", "Investigation Notes Store"],
        "Reliability Analytics": ["Analytics Data Mart", "Reporting Pipeline", "Telemetry Aggregation Service"],
        "Operational Awareness": ["Live Status Service", "Event Repository", "Device State Service"],
        "Outage Response": ["Outage Coordination Service", "Field Assignment Service", "Device Communication Layer"],
        "Asset Health": ["Asset Health Service", "Telemetry Service", "Device Registry"],
        "Telemetry": ["Telemetry Ingestion Service", "Telemetry Quality Rules", "Device Communication Layer"],
        "Firmware Management": ["Firmware Registry", "Device Communication Layer", "Rollout Tracking Service"],
    }
    return dependencies.get(capability, ["Authentication Service", "Audit Logging Service", "Project Data Service"])


def _feature_risks(capability: str) -> list[str]:
    risks = {
        "Fault Monitoring": ["Delayed telemetry ingestion", "Duplicate fault events", "Incorrect severity classification", "Event processing latency"],
        "Alert Management": ["Alert fatigue from noisy rules", "Duplicate notifications", "Delayed escalation delivery", "Incorrect owner assignment"],
        "Outage Investigation": ["Missing event correlation", "Stale device status", "Incomplete outage timeline", "Manual notes becoming inconsistent"],
        "Reliability Analytics": ["Incomplete historical data", "Delayed aggregation jobs", "Misleading trend interpretation", "Unclear metric definitions"],
        "Operational Awareness": ["Stale live status", "Disconnected source systems", "Permission gaps across operational views"],
        "Outage Response": ["Delayed field updates", "Unclear ownership", "Connectivity interruptions during response"],
        "Asset Health": ["Conflicting health signals", "Missing telemetry history", "False positive degradation signals"],
        "Telemetry": ["Telemetry gaps", "Clock drift between devices", "Ingestion backlog"],
        "Firmware Management": ["Interrupted rollout", "Version mismatch", "Device communication failure"],
    }
    return risks.get(capability, ["Dependency readiness risk", "Incomplete operational validation", "Adoption risk"])


def _validate_capability_features(
    features: Any,
    epic_title: str,
    business_goal: str,
    keywords: list[str],
    profile: dict[str, Any],
    fallback_features: list[dict[str, Any]] | None = None,
    diagnostics: Any = None,
) -> list[dict[str, Any]]:
    rejected = diagnostics.get("rejected_similar_features") if isinstance(diagnostics, dict) else None
    if rejected is None:
        rejected = []
    normalized: list[dict[str, Any]] = []
    seen_capabilities: dict[str, dict[str, Any]] = {}
    for raw in features if isinstance(features, list) else []:
        feature = _normalize_capability_feature(raw, keywords, profile)
        title = feature.get("title", "")
        reason = _feature_rejection_reason(feature, epic_title, business_goal)
        if reason:
            rejected.append({"title": title, "reason": reason, "similarity": round(_max_feature_similarity(title, epic_title, business_goal), 3)})
            continue
        capability = _clean_text(feature.get("capability_category") or feature.get("capability"))
        existing = seen_capabilities.get(capability)
        if existing:
            keep_existing = _feature_strength(existing) >= _feature_strength(feature)
            weaker = feature if keep_existing else existing
            stronger = existing if keep_existing else feature
            rejected.append(
                {
                    "title": weaker.get("title"),
                    "reason": f"duplicate capability coverage for {capability}; kept {stronger.get('title')}",
                    "similarity": round(_feature_overlap(stronger, weaker), 3),
                    "duplicate_of": stronger.get("title"),
                    "capability": capability,
                }
            )
            if not keep_existing:
                normalized = [item for item in normalized if item is not existing]
                normalized.append(feature)
                seen_capabilities[capability] = feature
            continue
        if title and title not in [item["title"] for item in normalized]:
            normalized.append(feature)
            seen_capabilities[capability] = feature
        if len(normalized) >= 10:
            break
    if len(normalized) < 5 and fallback_features:
        for feature in fallback_features:
            enriched = _normalize_capability_feature(feature, keywords, profile)
            capability = _clean_text(enriched.get("capability_category") or enriched.get("capability"))
            if (
                not _feature_rejection_reason(enriched, epic_title, business_goal)
                and capability not in seen_capabilities
                and enriched["title"] not in [item["title"] for item in normalized]
            ):
                normalized.append(enriched)
                seen_capabilities[capability] = enriched
            if len(normalized) >= 5:
                break
    return normalized[:10]


def _normalize_capability_feature(raw: Any, keywords: list[str], profile: dict[str, Any]) -> dict[str, Any]:
    item = raw if isinstance(raw, dict) else {"title": _clean_text(raw)}
    capability = _clean_text(item.get("capability"))
    if capability not in CAPABILITY_TAXONOMY:
        capability = _infer_capability_from_title(_clean_text(item.get("title")), keywords)
    users = _string_list(item.get("primary_users") or item.get("users")) or _users_for_capability(capability, _users_for_profile(profile))
    raw_modules = _string_list(item.get("impacted_modules") or item.get("modules")) or _modules_for_capability(capability, keywords, profile)
    raw_flows = _string_list(item.get("impacted_flows") or item.get("flows")) or _flows_for_capability(capability, keywords, profile)
    modules, module_relevance = _filter_relevant_items(capability, raw_modules, "module")
    flows, flow_relevance = _filter_relevant_items(capability, raw_flows, "flow")
    outcome = _clean_text(item.get("business_outcome")) or _business_outcome_for_capability(capability, keywords)
    title = _clean_title(_clean_text(item.get("title")) or _capability_feature_title(capability, keywords, profile))
    applications, application_relevance = _relevant_applications_for_capability(capability, profile)
    user_problem = _clean_text(item.get("user_problem")) or _user_problem_for_capability(capability, keywords)
    business_goal = _clean_text(item.get("business_goal")) or _feature_business_goal(title, capability)
    acceptance_criteria = _feature_acceptance_criteria(title, capability, outcome, modules, flows)
    return {
        "title": title,
        "description": _feature_description(title, capability, outcome, users, modules, flows, profile, applications),
        "business_goal": business_goal,
        "capability": capability,
        "capability_category": capability,
        "business_outcome": outcome,
        "business_value": outcome,
        "user_problem": user_problem,
        "primary_users": users,
        "primary_personas": users,
        "impacted_applications": [f"{app['name']} ({app['type']})" for app in applications],
        "application_relevance": application_relevance,
        "impacted_modules": modules,
        "module_relevance": module_relevance,
        "impacted_flows": flows,
        "flow_relevance": flow_relevance,
        "dependencies": _feature_dependencies(capability, modules, flows),
        "risks": _feature_risks(capability),
        "acceptance_criteria": acceptance_criteria,
        "acceptance_criteria_count": len(acceptance_criteria),
        "acceptance_criteria_quality_score": _acceptance_criteria_quality_score(acceptance_criteria),
        "status": "preview",
        "reasoning": _clean_text(item.get("reasoning")) or f"{title} is independently deliverable as a {capability.lower()} capability.",
    }


def _infer_capability_from_title(title: str, keywords: list[str]) -> str:
    lowered = title.lower()
    if "alert" in lowered or "notification" in lowered:
        return "Alert Management"
    if "investigation" in lowered or "workspace" in lowered:
        return "Outage Investigation"
    if "analytics" in lowered or "trend" in lowered or "classification" in lowered or "prioritization" in lowered:
        return "Reliability Analytics"
    if "health" in lowered:
        return "Asset Health"
    if "telemetry" in lowered:
        return "Telemetry"
    if "firmware" in lowered:
        return "Firmware Management"
    if "field" in lowered or "response" in lowered:
        return "Field Operations"
    if "report" in lowered:
        return "Reliability Analytics"
    return "Fault Monitoring" if "fault" in " ".join(keywords).lower() or "fault" in lowered else "Operational Awareness"


def _feature_rejection_reason(feature: dict[str, Any], epic_title: str, business_goal: str) -> str:
    title = feature.get("title", "")
    lowered = title.lower()
    if not title:
        return "missing feature title"
    if _max_feature_similarity(title, epic_title, business_goal) >= 0.58:
        return "too similar to epic or business goal"
    if lowered.endswith("dashboard") and not any(word in lowered for word in ["analytics", "health", "reporting"]):
        return "generic dashboard-only feature"
    for key in ["user_problem", "business_outcome", "capability"]:
        if not feature.get(key):
            return f"missing {key}"
    if not feature.get("impacted_modules"):
        return "missing impacted modules"
    if not feature.get("impacted_flows"):
        return "missing impacted flows"
    return ""


def _feature_strength(feature: dict[str, Any]) -> float:
    score = 0.0
    score += len(_string_list(feature.get("acceptance_criteria"))) * 0.12
    score += len(_string_list(feature.get("impacted_modules"))) * 0.08
    score += len(_string_list(feature.get("impacted_flows"))) * 0.08
    score += float(feature.get("confidence") or 0.82)
    if _clean_text(feature.get("business_goal")):
        score += 0.12
    if _clean_text(feature.get("business_value") or feature.get("business_outcome")):
        score += 0.12
    return score


def _feature_overlap(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_text = " ".join(
        [
            _clean_text(left.get("capability_category") or left.get("capability")),
            _clean_text(left.get("user_problem")),
            _clean_text(left.get("business_goal")),
            _clean_text(left.get("business_value") or left.get("business_outcome")),
            " ".join(_string_list(left.get("impacted_modules"))),
            " ".join(_string_list(left.get("impacted_flows"))),
            " ".join(_string_list(left.get("acceptance_criteria"))),
        ]
    )
    right_text = " ".join(
        [
            _clean_text(right.get("capability_category") or right.get("capability")),
            _clean_text(right.get("user_problem")),
            _clean_text(right.get("business_goal")),
            _clean_text(right.get("business_value") or right.get("business_outcome")),
            " ".join(_string_list(right.get("impacted_modules"))),
            " ".join(_string_list(right.get("impacted_flows"))),
            " ".join(_string_list(right.get("acceptance_criteria"))),
        ]
    )
    return _token_similarity(left_text, right_text)


def _max_feature_similarity(title: str, epic_title: str, business_goal: str) -> float:
    return max(_token_similarity(title, epic_title), _token_similarity(title, business_goal))


def _token_similarity(left: str, right: str) -> float:
    left_tokens = set(_meaningful_tokens(left))
    right_tokens = set(_meaningful_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _meaningful_tokens(value: str) -> list[str]:
    stopwords = {"the", "and", "or", "for", "with", "into", "from", "real", "time", "improve", "provide", "visibility", "dashboard"}
    return [token for token in _split_words(value.lower()) if token and token not in stopwords]


def _split_words(value: str) -> list[str]:
    chars = [ch.lower() if ch.isalnum() else " " for ch in value]
    return [part for part in "".join(chars).split() if part]


def _recommended_stories(feature_title: str, modules: list[str], flows: list[str], profile: dict[str, Any]) -> list[dict[str, Any]]:
    return _story_decomposition(feature_title, modules, flows, profile, {})["recommended_stories"]


def _review_story_journeys(journeys: list[dict[str, Any]], options: dict[str, Any] | None) -> list[dict[str, Any]]:
    options = options or {}
    approved = {str(item) for item in _string_list(options.get("approved_journey_ids") or options.get("approvedJourneyIds"))}
    rejected = {str(item) for item in _string_list(options.get("rejected_journey_ids") or options.get("rejectedJourneyIds"))}
    edits = options.get("journey_edits") or options.get("journeyEdits") or {}
    edits = edits if isinstance(edits, dict) else {}
    reviewed: list[dict[str, Any]] = []
    for index, journey in enumerate(journeys):
        if not isinstance(journey, dict):
            continue
        journey_id = str(journey.get("journeyId") or journey.get("journey_id") or "")
        edited = dict(journey)
        edit_payload = edits.get(journey_id) if journey_id else None
        if isinstance(edit_payload, dict):
            for key in ["journeyName", "businessResponsibility", "businessValue", "persona", "acceptanceThemes"]:
                if key in edit_payload:
                    edited[key] = edit_payload[key]
        if journey_id in rejected:
            edited["status"] = "rejected"
        elif not approved or journey_id in approved:
            edited["status"] = "approved"
        else:
            edited["status"] = "draft"
        edited["order"] = int(edited.get("order") or index + 1)
        reviewed.append(edited)
    return reviewed


def _story_plan_from_analysis(story_analysis: dict[str, Any], stories: list[dict[str, Any]]) -> dict[str, Any]:
    diagnostics = story_analysis.get("diagnostics") if isinstance(story_analysis.get("diagnostics"), dict) else {}
    coverage: list[str] = []
    for story in stories:
        coverage.extend(_string_list(story.get("coverage_area") or story.get("business_responsibility")))
    coverage = _unique(coverage)
    quality_scores = [int(story.get("story_quality_score") or story.get("validationReport", {}).get("summary", {}).get("score") or 80) for story in stories]
    return {
        "recommended_stories": stories,
        "diagnostics": {
            "capabilities_identified": _unique([story.get("business_responsibility") or story.get("user_goal") or story.get("title") for story in stories]),
            "user_actions_identified": _unique([story.get("goal") or story.get("user_action") or story.get("title") for story in stories]),
            "capability_count": int(diagnostics.get("journeyCount") or len(stories)),
            "action_count": int(diagnostics.get("journeyCount") or len(stories)),
            "generated_story_count": len(stories),
            "story_coverage_areas": coverage,
            "story_quality_score": round(sum(quality_scores) / len(quality_scores), 1) if quality_scores else 0,
            "acceptance_criteria_quality_score": 85 if stories else 0,
            "acceptance_criteria_count": sum(len(story.get("acceptance_criteria") or []) for story in stories),
            "rejected_generic_criteria": [],
            "minimum_story_count": 1,
            "small_feature": False,
            "journey_count": int(diagnostics.get("journeyCount") or len(stories)),
            "repository_coverage": int(diagnostics.get("repositoryCoverage") or 0),
            "knowledge_coverage": int(diagnostics.get("knowledgeCoverage") or 0),
            "dependency_count": int(diagnostics.get("dependencyCount") or 0),
            "validation_score": int(diagnostics.get("validationScore") or 0),
            "story_readiness": diagnostics.get("storyReadiness") or "NEEDS_REVIEW",
        },
    }


def _story_decomposition(feature_title: str, modules: list[str], flows: list[str], profile: dict[str, Any], feature: dict[str, Any]) -> dict[str, Any]:
    capability = _infer_capability_from_title(feature_title, _context_keywords(feature_title, "", profile))
    actions = _story_actions_for_capability(capability, feature_title)
    personas = _users_for_capability(capability, _users_for_profile(profile))
    stories: list[dict[str, Any]] = []
    rejected_generic_criteria: list[str] = []
    for index, action in enumerate(actions[:10]):
        persona = personas[index % len(personas)] if personas else "Operations User"
        title = _clean_story_title(action["title"])
        story = {
            "title": title,
            "description": f"As a {persona}, I want {action['want']} so that {action['benefit']}.",
            "persona": persona,
            "user_goal": action["goal"],
            "user_action": action["want"],
            "coverage_area": action["coverage_area"],
            "acceptance_criteria": _story_acceptance_for_action(action, persona),
            "modules_used": modules[:3],
            "flows_used": flows[:3],
            "confidence": 0.82 if modules or flows else 0.58,
            "supporting_context": {
                "modules": modules[:3],
                "flows": flows[:3],
            },
        }
        story, rejected = _apply_story_quality_gate(story, action, persona)
        rejected_generic_criteria.extend(rejected)
        if not _story_contains_rejected_terms(story):
            stories.append(story)
    is_small = _is_small_feature(feature)
    if len(stories) < 5 and not is_small:
        expanded_actions = _story_actions_for_capability("", feature_title)
        for action in expanded_actions:
            if len(stories) >= 5:
                break
            if action["coverage_area"] in {story["coverage_area"] for story in stories}:
                continue
            persona = personas[len(stories) % len(personas)] if personas else "Operations User"
            story = {
                "title": _clean_story_title(action["title"]),
                "description": f"As a {persona}, I want {action['want']} so that {action['benefit']}.",
                "persona": persona,
                "user_goal": action["goal"],
                "user_action": action["want"],
                "coverage_area": action["coverage_area"],
                "acceptance_criteria": _story_acceptance_for_action(action, persona),
                "modules_used": modules[:3],
                "flows_used": flows[:3],
                "confidence": 0.82 if modules or flows else 0.58,
                "supporting_context": {"modules": modules[:3], "flows": flows[:3]},
            }
            story, rejected = _apply_story_quality_gate(story, action, persona)
            rejected_generic_criteria.extend(rejected)
            if not _story_contains_rejected_terms(story):
                stories.append(story)
    if len(stories) < 4 and not is_small:
        raise ValueError(f"Story decomposition produced {len(stories)} stories for {feature_title}; minimum is 4.")
    coverage = _unique([story["coverage_area"] for story in stories])
    quality_scores = [int(story.get("story_quality_score") or 0) for story in stories]
    ac_quality_scores = [int(story.get("acceptance_criteria_quality_score") or 0) for story in stories]
    average_quality = round(sum(quality_scores) / len(quality_scores), 1) if quality_scores else 0
    return {
        "recommended_stories": stories[:10],
        "diagnostics": {
            "capabilities_identified": _unique([story["user_goal"] for story in stories]),
            "user_actions_identified": _unique([story["user_action"] for story in stories]),
            "capability_count": len(_unique([story["user_goal"] for story in stories])),
            "action_count": len(actions),
            "generated_story_count": len(stories[:10]),
            "story_coverage_areas": coverage,
            "story_quality_score": average_quality,
            "acceptance_criteria_quality_score": round(sum(ac_quality_scores) / len(ac_quality_scores), 1) if ac_quality_scores else 0,
            "acceptance_criteria_count": sum(len(story.get("acceptance_criteria") or []) for story in stories[:10]),
            "rejected_generic_criteria": _unique(rejected_generic_criteria),
            "minimum_story_count": 1 if is_small else 4,
            "small_feature": is_small,
        },
    }


def _story_actions_for_capability(capability: str, feature_title: str) -> list[dict[str, str]]:
    actions = {
        "Fault Monitoring": [
            {"title": "View Active Critical Fault Events", "want": "to view active critical fault events", "benefit": "I can identify issues that need immediate attention", "goal": "Detect critical events", "coverage_area": "View"},
            {"title": "Open Critical Fault Event Details", "want": "to open detailed information for a critical fault event", "benefit": "I can understand the device, severity, timing, and current status", "goal": "Review event details", "coverage_area": "Details"},
            {"title": "Search Critical Events by Device", "want": "to search critical events by device or event identifier", "benefit": "I can quickly find the event I need to review", "goal": "Find event", "coverage_area": "Search"},
            {"title": "Filter Critical Events by Severity and Status", "want": "to filter critical events by severity and status", "benefit": "I can focus on the highest priority events first", "goal": "Prioritize event review", "coverage_area": "Filter"},
            {"title": "See Newly Arrived Critical Events Quickly", "want": "new critical events to appear quickly", "benefit": "I can respond without waiting for manual refresh or delayed reports", "goal": "Maintain live awareness", "coverage_area": "Notifications"},
            {"title": "Recognize Unavailable Event Data", "want": "to see a clear message when event data is unavailable", "benefit": "I know when the system cannot provide complete information", "goal": "Handle data gaps", "coverage_area": "Empty states"},
            {"title": "Review Critical Event Access History", "want": "to know when critical event details were accessed", "benefit": "I can support audit and operational traceability", "goal": "Audit event access", "coverage_area": "Audit requirements"},
        ],
        "Alert Management": [
            {"title": "Receive Critical Fault Alerts", "want": "to receive alerts for critical fault events", "benefit": "I can respond before an issue escalates", "goal": "Get notified", "coverage_area": "Notifications"},
            {"title": "Review Alert Details Before Acting", "want": "to review alert details before taking action", "benefit": "I can decide the right response with enough context", "goal": "Understand alert context", "coverage_area": "Details"},
            {"title": "Search Assigned Alerts", "want": "to search alerts assigned to me", "benefit": "I can find a specific alert quickly", "goal": "Find alert", "coverage_area": "Search"},
            {"title": "Filter Alerts by Severity and Owner", "want": "to filter alerts by severity and owner", "benefit": "I can focus on alerts that need my response", "goal": "Prioritize alerts", "coverage_area": "Filter"},
            {"title": "Acknowledge Assigned Alerts", "want": "to acknowledge alerts assigned to me", "benefit": "the team can see that response is underway", "goal": "Confirm ownership", "coverage_area": "Audit requirements"},
            {"title": "Avoid Duplicate Alert Noise", "want": "related duplicate alerts to be grouped", "benefit": "I can focus on the actual event instead of repeated notifications", "goal": "Reduce alert noise", "coverage_area": "Error handling"},
        ],
        "Outage Investigation": [
            {"title": "Start an Outage Investigation", "want": "to start an outage investigation from a fault event", "benefit": "I can begin triage from the event that triggered concern", "goal": "Begin investigation", "coverage_area": "View"},
            {"title": "Review Event Timeline", "want": "to review the timeline of related events", "benefit": "I can understand what happened before and after the outage", "goal": "Understand sequence", "coverage_area": "Details"},
            {"title": "Search Investigation Evidence", "want": "to search investigation evidence by device or event", "benefit": "I can locate the information needed for triage", "goal": "Find evidence", "coverage_area": "Search"},
            {"title": "Filter Investigation Evidence", "want": "to filter investigation evidence by severity, device, and time", "benefit": "I can find relevant evidence quickly", "goal": "Narrow evidence", "coverage_area": "Filter"},
            {"title": "Add Investigation Notes", "want": "to add notes during the investigation", "benefit": "the team has a shared record of findings", "goal": "Capture findings", "coverage_area": "Audit requirements"},
            {"title": "Review Missing or Stale Data", "want": "to see when investigation data is missing or stale", "benefit": "I can avoid drawing conclusions from incomplete information", "goal": "Assess data quality", "coverage_area": "Empty states"},
        ],
        "Reliability Analytics": [
            {"title": "View Reliability Trends", "want": "to view reliability trends over time", "benefit": "I can identify recurring operational issues", "goal": "Analyze trends", "coverage_area": "View"},
            {"title": "Review Trend Details", "want": "to review details behind a reliability trend", "benefit": "I can understand what contributed to the trend", "goal": "Review details", "coverage_area": "Details"},
            {"title": "Search Reliability Results", "want": "to search reliability results by asset or event type", "benefit": "I can locate the trends relevant to my decision", "goal": "Find results", "coverage_area": "Search"},
            {"title": "Filter Trends by Asset Group", "want": "to filter reliability trends by asset group", "benefit": "I can focus on the areas with highest operational impact", "goal": "Focus analysis", "coverage_area": "Filter"},
            {"title": "Compare Current and Previous Periods", "want": "to compare current reliability against previous periods", "benefit": "I can see whether reliability is improving or declining", "goal": "Compare performance", "coverage_area": "Details"},
            {"title": "Identify Incomplete Trend Data", "want": "to see when trend data is incomplete", "benefit": "I can trust the analysis before using it for decisions", "goal": "Validate analytics quality", "coverage_area": "Empty states"},
        ],
    }
    return actions.get(
        capability,
        [
            {"title": f"Use {feature_title}", "want": f"to use {feature_title.lower()} for my daily work", "benefit": "I can complete the intended outcome reliably", "goal": "Complete user outcome", "coverage_area": "View"},
            {"title": f"Review {feature_title} Details", "want": f"to review {feature_title.lower()} details", "benefit": "I can make an informed decision", "goal": "Review details", "coverage_area": "Details"},
            {"title": f"Search {feature_title} Records", "want": f"to search {feature_title.lower()} records", "benefit": "I can find the item I need quickly", "goal": "Find records", "coverage_area": "Search"},
            {"title": f"Filter {feature_title} Results", "want": f"to filter {feature_title.lower()} results", "benefit": "I can focus on the most relevant items", "goal": "Narrow results", "coverage_area": "Filter"},
            {"title": f"Handle {feature_title} Exceptions", "want": f"to understand when {feature_title.lower()} data is unavailable", "benefit": "I can recover without confusion", "goal": "Handle exceptions", "coverage_area": "Error handling"},
            {"title": f"Confirm {feature_title} Outcome", "want": f"to confirm the outcome of {feature_title.lower()}", "benefit": "I know the capability worked as expected", "goal": "Confirm outcome", "coverage_area": "Audit requirements"},
        ],
    )


def _is_small_feature(feature: dict[str, Any]) -> bool:
    markers = [
        feature.get("size"),
        feature.get("story_size"),
        feature.get("complexity"),
        feature.get("scope"),
    ]
    tags = feature.get("tags") if isinstance(feature.get("tags"), list) else []
    text = " ".join(str(value).lower() for value in [*markers, *tags] if value)
    return "small" in text or "xs" in text


def _story_action_from_title(title: str, flows: list[str] | None = None, modules: list[str] | None = None) -> dict[str, str]:
    cleaned_title = _clean_title(title)
    lowered = cleaned_title.lower()
    action_word = "Use"
    if any(token in lowered for token in ["open", "detail", "details", "review"]):
        coverage = "Details"
        action_word = "Open"
    elif "search" in lowered or "find" in lowered:
        coverage = "Search"
        action_word = "Search"
    elif "filter" in lowered:
        coverage = "Filter"
        action_word = "Filter"
    elif any(token in lowered for token in ["list", "view", "display", "show", "see"]):
        coverage = "View"
        action_word = "View"
    elif any(token in lowered for token in ["acknowledge", "audit", "history"]):
        coverage = "Audit requirements"
        action_word = "Review"
    elif any(token in lowered for token in ["notify", "alert"]):
        coverage = "Notifications"
        action_word = "Review"
    else:
        coverage = "View"
    subject = _story_domain_subject(cleaned_title, flows or [], modules or [])
    return {
        "title": cleaned_title,
        "want": f"to {action_word.lower()} {subject.lower()}",
        "benefit": "I can complete the approved operational outcome with the right context",
        "goal": subject,
        "coverage_area": coverage,
        "primary_action": action_word,
    }


def _story_domain_subject(title: str, flows: list[str], modules: list[str]) -> str:
    lowered = title.lower()
    if "fault" in lowered and "detail" in lowered:
        return "Critical Fault Event Details"
    if "fault" in lowered:
        return "Critical Fault Events"
    if "device" in lowered and "health" in lowered:
        return "Device Health Context"
    if "telemetry" in lowered:
        return "Telemetry Context"
    for value in [*flows, *modules]:
        cleaned = _clean_title(value)
        if cleaned:
            return cleaned
    return _clean_title(title)


def _story_acceptance_for_action(action: dict[str, str], persona: str) -> list[str]:
    coverage = action.get("coverage_area", "")
    if coverage == "View":
        return [
            f"{persona} can view the relevant records for {action['goal'].lower()} from the approved entry point.",
            "The list displays Device ID, Fault Type, Severity, Event Timestamp, Current Status, and Device Health when available.",
            "Records can be sorted by Severity and Timestamp, including Event Timestamp as the time value.",
            "User can refresh the list without duplicating existing records or losing the current view.",
            "An empty state explains when no matching records are available.",
            "Users without permission see an access-restricted message instead of the records.",
        ]
    if coverage == "Details":
        return [
            f"{persona} can open a critical fault event from the event list.",
            "Event details display Device ID, Fault Type, Severity, Event Timestamp, Current Status, Location, and Connectivity Status.",
            "Device Health, Firmware Version, Telemetry Context, Event History, and Outage Context are displayed when available.",
            "Missing fields are labeled as unavailable without hiding the remaining details.",
            "User can return to the previous screen without losing filters or search text.",
            "Access follows role-based permissions for event detail views.",
            "Event detail access is audit logged with user identity, timestamp, and event identifier.",
        ]
    if coverage == "Search":
        return [
            "User can enter Device ID or Event ID as search text.",
            "User can execute the search from keyboard or search action.",
            "Matching critical events are displayed with Device ID, Fault Type, Severity, Event Timestamp, and Current Status.",
            "Partial matches are supported for Device ID and Event ID.",
            "Search results are returned within 3 seconds for normal project data volume.",
            "A no-results message is displayed when no matching events are found.",
            "Users without search permission see an access-restricted message.",
        ]
    if coverage == "Filter":
        return [
            "User can filter results by Severity, Status, and Time Range.",
            "Multiple selected filters are applied together.",
            "User can reset all filters with one action.",
            "Filtered results display Device ID, Fault Type, Severity, Event Timestamp, and Current Status.",
            "An empty-results message is displayed when filters match no records.",
            "Filter options only expose values the user is authorized to view.",
        ]
    if coverage == "Notifications":
        return [
            f"{persona} is notified when a relevant critical event requires attention.",
            "Notification displays Device ID, Fault Type, Severity, Timestamp, and Status.",
            "New notifications appear within 60 seconds of event ingestion.",
            "User can open event details directly from the notification.",
            "Duplicate notifications for the same active event are grouped or suppressed.",
            "Notification access follows user permission settings.",
            "User sees an unavailable notification message when event details cannot be loaded.",
        ]
    if coverage == "Empty states":
        return [
            "User sees a clear empty-state message when no records are available.",
            "Empty state displays the affected Device ID, Status, or Time Range when that context is known.",
            "Empty state explains whether no data exists or data is temporarily unavailable.",
            "User is offered a retry or refresh action when the empty state may be temporary.",
            "Empty state does not display stale records as current data.",
            "Users without permission see an access-restricted empty state.",
        ]
    if coverage == "Error handling":
        return [
            "User sees a clear error message when the requested action cannot be completed.",
            "Error message does not expose internal service, repository, module, or API details.",
            "User can retry the failed action when retry is safe.",
            "Validation errors identify the field or choice that needs correction.",
            "The system preserves the user's current search, filter, or selected context after the error.",
        ]
    if coverage == "Audit requirements":
        return [
            "User action is recorded with user identity, timestamp, action type, and affected record identifier.",
            "Audit entry is created when details are viewed, alerts are acknowledged, notes are added, or status is changed.",
            "Audit history can be reviewed by an authorized operations or support user.",
            "Audit entries remain available after the related event is resolved.",
            "Unavailable audit history is clearly indicated without hiding the current event details.",
        ]
    return [
        f"{persona} can complete the requested action for {action['goal'].lower()}.",
        "The result displays the fields required for the user decision.",
        "Unavailable data is clearly identified.",
        "The action result is observable and repeatable for QA validation.",
    ]


def _apply_story_quality_gate(story: dict[str, Any], action: dict[str, str], persona: str) -> tuple[dict[str, Any], list[str]]:
    criteria = [str(item).strip() for item in story.get("acceptance_criteria", []) if str(item).strip()]
    cleaned, rejected = _reject_generic_acceptance_criteria(criteria)
    categories = _acceptance_criteria_categories(cleaned)
    if len(cleaned) < 4 or not _has_required_acceptance_categories(categories):
        regenerated, more_rejected = _reject_generic_acceptance_criteria(_story_acceptance_for_action(action, persona))
        cleaned = regenerated
        rejected.extend(more_rejected)
        categories = _acceptance_criteria_categories(cleaned)
    story["acceptance_criteria"] = cleaned
    story["acceptance_criteria_count"] = len(cleaned)
    story["acceptance_criteria_categories"] = categories
    story["acceptance_criteria_quality_score"] = _acceptance_criteria_quality_score(cleaned)
    score = _story_quality_score(story)
    if score < STORY_QUALITY_THRESHOLD:
        regenerated, more_rejected = _reject_generic_acceptance_criteria(_story_acceptance_for_action(action, persona))
        story["acceptance_criteria"] = regenerated
        story["acceptance_criteria_count"] = len(regenerated)
        story["acceptance_criteria_categories"] = _acceptance_criteria_categories(regenerated)
        story["acceptance_criteria_quality_score"] = _acceptance_criteria_quality_score(regenerated)
        rejected.extend(more_rejected)
        score = _story_quality_score(story)
    story["story_quality_score"] = score
    story["quality_gate"] = "passed" if score >= STORY_QUALITY_THRESHOLD else "failed"
    return story, rejected


STORY_QUALITY_THRESHOLD = 80
GENERIC_ACCEPTANCE_PHRASES = [
    "visible and testable",
    "workflow covered",
    "workflow is covered",
    "flow covered end to end",
    "covered end to end",
    "integration validated",
    "integrations are validated",
    "stakeholder confirms",
    "stakeholders can confirm",
    "stakeholder confirmation",
    "end-to-end covered",
    "end to end covered",
    "capability supported",
]


def _reject_generic_acceptance_criteria(criteria: list[str]) -> tuple[list[str], list[str]]:
    accepted = []
    rejected = []
    for criterion in criteria:
        lowered = criterion.lower()
        if any(phrase in lowered for phrase in GENERIC_ACCEPTANCE_PHRASES):
            rejected.append(criterion)
        else:
            accepted.append(criterion)
    return accepted, rejected


def _story_quality_score(story: dict[str, Any]) -> int:
    score = 0
    user_action = str(story.get("user_action") or "").strip()
    description = str(story.get("description") or "")
    criteria = [str(item) for item in story.get("acceptance_criteria") or []]
    coverage = str(story.get("coverage_area") or "").strip()
    if user_action and not _story_contains_rejected_terms({"title": "", "description": user_action}):
        score += 20
    if " so that " in description and len(description.split(" so that ", 1)[-1].strip()) >= 12:
        score += 20
    categories = _acceptance_criteria_categories(criteria)
    ac_score = int(story.get("acceptance_criteria_quality_score") or _acceptance_criteria_quality_score(criteria))
    if len(criteria) >= 4 and not _reject_generic_acceptance_criteria(criteria)[1] and _has_required_acceptance_categories(categories):
        score += 25
    if _criteria_are_testable(criteria):
        score += 20
    if coverage:
        score += 15
    if ac_score >= 80:
        score += 5
    return min(score, 100)


REQUIRED_ACCEPTANCE_CATEGORIES = ["Functional Behavior", "Data Display", "Error Handling", "Permission/Security"]


def _acceptance_criteria_categories(criteria: list[str]) -> list[str]:
    text = " ".join(criteria).lower()
    categories: list[str] = []
    if any(token in text for token in ["can ", "open", "view", "search", "filter", "refresh", "return", "execute", "reset"]):
        categories.append("Functional Behavior")
    if any(token in text for token in ["device id", "fault type", "severity", "timestamp", "status", "device health", "location", "telemetry", "event history", "outage", "firmware", "field"]):
        categories.append("Data Display")
    if any(token in text for token in ["missing", "unavailable", "empty", "no-results", "error", "invalid", "retry", "stale"]):
        categories.append("Error Handling")
    if any(token in text for token in ["permission", "authorization", "authorized", "access-restricted", "role-based", "audit", "logged", "identity"]):
        categories.append("Permission/Security")
    return categories


def _has_required_acceptance_categories(categories: list[str]) -> bool:
    return all(category in categories for category in REQUIRED_ACCEPTANCE_CATEGORIES)


def _acceptance_criteria_quality_score(criteria: list[str]) -> int:
    if not criteria:
        return 0
    score = 0
    rejected = _reject_generic_acceptance_criteria(criteria)[1]
    categories = _acceptance_criteria_categories(criteria)
    if not rejected:
        score += 20
    if len(criteria) >= 4:
        score += 20
    if _criteria_are_testable(criteria):
        score += 20
    category_score = int((len(set(categories) & set(REQUIRED_ACCEPTANCE_CATEGORIES)) / len(REQUIRED_ACCEPTANCE_CATEGORIES)) * 30)
    score += category_score
    measurable_terms = ["within", "seconds", "timestamp", "status", "id", "logged", "returned", "displayed"]
    if sum(1 for criterion in criteria if any(term in criterion.lower() for term in measurable_terms)) >= 3:
        score += 10
    return min(score, 100)


def _criteria_are_testable(criteria: list[str]) -> bool:
    if len(criteria) < 4:
        return False
    testable_tokens = [
        "can ",
        "display",
        "within ",
        "message",
        "returned",
        "recorded",
        "timestamp",
        "filter",
        "sort",
        "search",
        "permission",
        "audit",
        "no-results",
        "empty",
    ]
    matches = 0
    for criterion in criteria:
        lowered = criterion.lower()
        if any(token in lowered for token in testable_tokens):
            matches += 1
    return matches >= 3


def _clean_story_title(title: str) -> str:
    blocked = {"workflow", "integration", "repository", "service", "api", "module"}
    words = [word for word in _clean_title(title).split() if word.lower() not in blocked]
    return " ".join(words) or _clean_title(title)


def _story_contains_rejected_terms(story: dict[str, Any]) -> bool:
    rejected = ["workflow", "integration", "repository", "service", "api", "module"]
    text = f"{story.get('title', '')} {story.get('description', '')}".lower()
    return any(term in text for term in rejected)


def _select_relevant_items(items: list[str], title: str, description: str, fallback_count: int = 3) -> list[str]:
    if not items:
        return []
    text = f"{title} {description}".lower()
    scored = []
    for item in items:
        tokens = [token for token in item.lower().replace("-", " ").split() if len(token) > 2]
        score = sum(1 for token in tokens if token in text)
        scored.append((score, item))
    selected = [item for score, item in sorted(scored, key=lambda pair: pair[0], reverse=True) if score > 0]
    return _unique(selected or items[:fallback_count])[:fallback_count]


def _relevance_keyword_set(text: str) -> set[str]:
    stop_words = {"with", "from", "that", "this", "into", "when", "then", "they", "their", "want", "user", "users", "story", "feature", "epic"}
    normalized = _clean_text(text).replace("-", " ").replace("_", " ").lower()
    return {word.strip(".,:;()[]{}") for word in normalized.split() if len(word.strip(".,:;()[]{}")) > 2 and word.strip(".,:;()[]{}") not in stop_words}


class KnowledgeRelevanceSelector:
    """Selects the smallest useful knowledge slice for a work item intent."""

    POSITIVE_RULES: list[tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = [
        (("fault", "fault event", "critical event"), ("Fault Monitoring", "Telemetry"), ("Fault Event Review",)),
        (("outage", "investigation", "triage"), ("Fault Monitoring", "Telemetry", "Device Management", "Asset Health"), ("Outage Investigation", "Fault Event Review", "Device Health Review")),
        (("telemetry", "freshness", "signal"), ("Telemetry",), ("Telemetry Review", "Device Health Review")),
        (("access", "restriction", "permission", "unauthorized"), ("Authentication", "Authorization"), ("Login",)),
        (("device health", "asset health"), ("Device Management", "Asset Health", "Telemetry"), ("Device Health Review",)),
        (("firmware", "version", "rollout", "upgrade", "rollback", "compliance", "device update"), ("Firmware", "Firmware Management", "Firmware Update"), ("Firmware Rollout", "Firmware Review")),
        (("login", "token", "session", "authentication", "authorization", "auth"), ("Authentication", "Authorization"), ("Login", "Token Refresh")),
        (("report", "reporting", "trend", "dashboard", "kpi", "metric", "metrics", "analysis", "analytics"), ("Analytics", "Reporting"), ("Analytics", "Reporting", "Dashboard")),
    ]

    NEGATIVE_RULES: list[tuple[tuple[str, ...], tuple[str, ...], str]] = [
        (
            ("firmware", "version", "rollout", "upgrade", "rollback", "compliance", "device update"),
            ("firmware",),
            "story does not mention firmware, rollout, version, upgrade, rollback, or compliance",
        ),
        (
            ("session", "login", "token", "authentication", "authorization", "auth"),
            ("token refresh",),
            "story does not mention session expiry, login, token, authentication refresh, or authorization failure",
        ),
        (
            ("report", "reporting", "trend", "dashboard", "kpi", "metric", "metrics", "analysis", "analytics"),
            ("analytics", "reporting"),
            "story does not mention reporting, trend, dashboard, KPI, metrics, or analysis",
        ),
    ]

    def select(
        self,
        work_item_text: str,
        work_item_type: str,
        parent_context: dict[str, Any] | None,
        project_id: str,
        knowledge_registry: dict[str, Any],
        repository_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        text = _clean_text(work_item_text)
        parent_text = _clean_text(" ".join(str(value) for value in (parent_context or {}).values()))
        combined = f"{text} {parent_text}".lower()
        intent = self.extract_intent(combined, work_item_type, parent_context)
        rejected: list[dict[str, Any]] = []
        scores: dict[str, float] = {}
        modules = self._select_items(
            _string_list(knowledge_registry.get("modules")),
            "module",
            combined,
            intent,
            rejected,
            scores,
        )
        flows = self._select_items(
            _string_list(knowledge_registry.get("flows")),
            "flow",
            combined,
            intent,
            rejected,
            scores,
        )
        dependencies = self._dependencies(combined, [item["name"] for item in modules], [item["name"] for item in flows])
        standards = self._standards(combined, knowledge_registry)
        files = self._ranked_files(combined, repository_snapshot or knowledge_registry)
        token_estimate = _estimate_tokens(json.dumps({"intent": intent, "modules": modules, "flows": flows, "dependencies": dependencies}, ensure_ascii=True))
        return {
            "project_id": project_id,
            "intent": intent,
            "relevant_modules": modules,
            "relevant_flows": flows,
            "relevant_dependencies": dependencies,
            "relevant_standards": standards,
            "relevant_files": files,
            "rejected_context": rejected,
            "relevance_scores": scores,
            "token_estimate": token_estimate,
            "context_source": "knowledge_relevance_selector",
        }

    def extract_intent(self, text: str, work_item_type: str = "", parent_context: dict[str, Any] | None = None) -> dict[str, Any]:
        keywords = sorted(_relevance_keyword_set(text))
        phrases = [
            phrase
            for phrase in [
                "outage investigation",
                "fault event",
                "device health",
                "telemetry freshness",
                "token refresh",
                "firmware rollout",
                "firmware upgrade",
                "access restriction",
            ]
            if phrase in text
        ]
        roles = [role for role in ["operations user", "field technician", "operator", "administrator", "support analyst"] if role in text]
        actions = [action for action in ["review", "open", "start", "triage", "investigate", "monitor", "filter", "search", "notify", "validate"] if action in text]
        domain_objects = [obj for obj in ["fault event", "outage", "device", "telemetry", "device health", "firmware", "token", "session", "dashboard"] if obj in text]
        return {
            "primary_capability": phrases[0] if phrases else (keywords[0] if keywords else _clean_text(work_item_type).lower()),
            "user_role": roles[0] if roles else "",
            "business_action": actions[0] if actions else "",
            "affected_domain_objects": domain_objects,
            "explicit_modules": [],
            "explicit_flows": phrases,
            "keywords": _unique([*phrases, *roles, *actions, *domain_objects, *keywords])[:24],
        }

    def _select_items(
        self,
        items: list[str],
        item_type: str,
        text: str,
        intent: dict[str, Any],
        rejected: list[dict[str, Any]],
        scores: dict[str, float],
    ) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        for item in items:
            name = _clean_text(item)
            if not name:
                continue
            lowered = name.lower()
            negative_reason = self._negative_reason(lowered, text)
            if negative_reason:
                rejected.append(
                    {
                        "name": name,
                        "type": item_type,
                        "confidence": 0.05,
                        "reason": f"{name} removed because {negative_reason}.",
                        "evidence": [],
                        "source": "negative_relevance_rule",
                    }
                )
                scores[name] = 0.05
                continue
            score, evidence, reason = self._score_item(lowered, text, intent)
            if score >= 0.34:
                scores[name] = round(score, 2)
                selected.append(
                    {
                        "name": name,
                        "type": item_type,
                        "confidence": round(score, 2),
                        "reason": reason,
                        "evidence": evidence[:5],
                        "source": "repository_intelligence",
                    }
                )
            else:
                scores[name] = round(score, 2)
        selected.sort(key=lambda item: item["confidence"], reverse=True)
        return selected[:6]

    def _score_item(self, item_name: str, text: str, intent: dict[str, Any]) -> tuple[float, list[str], str]:
        evidence: list[str] = []
        score = 0.0
        item_tokens = _relevance_keyword_set(item_name)
        text_tokens = _relevance_keyword_set(text)
        matches = sorted(item_tokens.intersection(text_tokens))
        if matches:
            score += min(0.55, 0.22 * len(matches))
            evidence.extend(matches)
        for cues, module_targets, flow_targets in self.POSITIVE_RULES:
            if any(cue in text for cue in cues):
                targets = [*module_targets, *flow_targets]
                if any(target.lower() in item_name or item_name in target.lower() for target in targets):
                    score += 0.72
                    evidence.extend([cue for cue in cues if cue in text][:2])
        if any(keyword in item_name for keyword in _string_list(intent.get("keywords"))):
            score += 0.2
        reason = "Matched work item intent through repository knowledge."
        return min(score, 0.98), _unique(evidence), reason

    def _negative_reason(self, item_name: str, text: str) -> str:
        for required_cues, blocked_names, reason in self.NEGATIVE_RULES:
            if any(blocked in item_name for blocked in blocked_names) and not any(cue in text for cue in required_cues):
                return reason
        return ""

    def _dependencies(self, text: str, modules: list[str], flows: list[str]) -> list[dict[str, Any]]:
        impact = {"affected_modules": modules, "affected_flows": flows}
        keywords = sorted(_relevance_keyword_set(text))
        deps = []
        if any(keyword in keywords for keyword in ["otp", "sms"]):
            deps.extend(["Auth Service", "SMS Provider"])
        if any(keyword in keywords for keyword in ["fault", "event"]):
            deps.extend(["Event Repository", "Fault Classification Rules"])
        if "telemetry" in keywords or any("Telemetry" in module for module in modules):
            deps.extend(["Telemetry Service", "Device Connectivity"])
        if any(keyword in keywords for keyword in ["login", "token", "session", "auth"]):
            deps.extend(["Auth Service", "Session Store"])
        if "firmware" in keywords:
            deps.extend(["Firmware Version Service", "Device Update Channel"])
        deps.extend(f"{module} owner review" for module in impact["affected_modules"][:2])
        deps.extend(f"{flow} regression coverage" for flow in impact["affected_flows"][:2])
        return [
            {"name": dep, "type": "dependency", "confidence": 0.72, "reason": "Derived from selected modules and flows.", "evidence": modules[:2] + flows[:2], "source": "knowledge_relevance_selector"}
            for dep in _unique(deps)[:8]
        ]

    def _standards(self, text: str, registry: dict[str, Any]) -> list[dict[str, Any]]:
        standards = _string_list(registry.get("standards"))
        selected = []
        for standard in standards[:8]:
            selected.append(
                {"name": standard, "type": "standard", "confidence": 0.45, "reason": "Project standard applies unless contradicted by the work item.", "evidence": [], "source": "knowledge_registry"}
            )
        return selected

    def _ranked_files(self, text: str, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        raw_files = snapshot.get("ranked_files") or snapshot.get("repository_file_ranking") or []
        ranked: list[dict[str, Any]] = []
        for item in raw_files if isinstance(raw_files, list) else []:
            if isinstance(item, str):
                path = item
                score = 0.4
            elif isinstance(item, dict):
                path = _clean_text(item.get("path") or item.get("file") or item.get("name"))
                score = float(item.get("score") or item.get("confidence") or 0.4)
            else:
                continue
            if path:
                ranked.append({"name": path, "type": "file", "confidence": round(score, 2), "reason": "Repository-ranked file.", "evidence": [], "source": "repository_file_ranking"})
        return ranked[:8]


KNOWLEDGE_RELEVANCE_SELECTOR = KnowledgeRelevanceSelector()


def _selection_names(selection: dict[str, Any], key: str) -> list[str]:
    return [item["name"] for item in selection.get(key, []) if isinstance(item, dict) and _clean_text(item.get("name"))]


def _relevance_metadata(selection: dict[str, Any]) -> dict[str, Any]:
    return {
        "intent_keywords": _string_list(selection.get("intent", {}).get("keywords"))[:24],
        "selected_modules": _selection_names(selection, "relevant_modules"),
        "selected_flows": _selection_names(selection, "relevant_flows"),
        "selected_dependencies": _selection_names(selection, "relevant_dependencies"),
        "rejected_context": selection.get("rejected_context", []),
        "relevance_scores": selection.get("relevance_scores", {}),
        "token_estimate": selection.get("token_estimate", 0),
        "context_source": selection.get("context_source") or "knowledge_relevance_selector",
    }


def _select_knowledge_context(
    profile: dict[str, Any],
    work_item: dict[str, Any],
    work_item_type: str,
    parent_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = " ".join(
        [
            _clean_text(work_item.get("title")),
            _clean_text(work_item.get("description")),
            " ".join(_string_list(work_item.get("acceptance_criteria"))),
            " ".join(_string_list(work_item.get("business_outcomes"))),
        ]
    )
    return KNOWLEDGE_RELEVANCE_SELECTOR.select(
        text,
        work_item_type,
        parent_context,
        _clean_text(profile.get("project_id")),
        profile.get("knowledge_registry") or {},
        profile.get("knowledge_registry") or {},
    )


def _profile_with_relevance(profile: dict[str, Any], selection: dict[str, Any]) -> dict[str, Any]:
    registry = dict(profile.get("knowledge_registry") or {})
    selected_modules = _selection_names(selection, "relevant_modules")
    selected_flows = _selection_names(selection, "relevant_flows")
    selected_standards = _selection_names(selection, "relevant_standards")
    registry["modules"] = selected_modules
    registry["flows"] = selected_flows
    if selected_standards:
        registry["standards"] = selected_standards
    return {
        **profile,
        "applications": _applications_for_selection(profile, selection),
        "knowledge_registry": registry,
        "_knowledge_relevance": selection,
    }


def _applications_for_selection(profile: dict[str, Any], selection: dict[str, Any]) -> list[dict[str, str]]:
    apps = _dedupe_applications(profile.get("applications") or profile.get("knowledge_registry", {}).get("applications") or [])
    if not apps:
        return apps
    context = " ".join([
        *(_selection_names(selection, "relevant_modules")),
        *(_selection_names(selection, "relevant_flows")),
        *(_source_intent(selection)),
    ]).lower()
    selected: list[dict[str, str]] = []
    for app in apps:
        app_text = f"{app.get('name', '')} {app.get('type', '')}".lower()
        if "firmware" in app_text and "firmware" not in context:
            continue
        if "analytics" in app_text and not any(token in context for token in ["analytics", "report", "trend", "metric", "kpi", "reliability"]):
            continue
        selected.append(app)
    return selected or apps[:1]


def _business_outcomes(keywords: list[str], profile: dict[str, Any]) -> list[str]:
    outcomes = []
    if "fault" in keywords:
        outcomes.append("Faster detection and review of fault events")
    if "telemetry" in keywords or "health" in keywords:
        outcomes.append("Improved visibility into telemetry and device health")
    if "firmware" in keywords:
        outcomes.append("Safer firmware rollout tracking and upgrade transparency")
    if not outcomes:
        outcomes.append(f"Clearer delivery outcomes for {profile.get('project_name') or 'the project'}")
    outcomes.append("Traceable planning artifacts aligned to project standards")
    return _unique(outcomes)


def _users_for_profile(profile: dict[str, Any]) -> list[str]:
    domain = (profile.get("domain") or "").lower()
    if any(word in domain for word in ["utility", "meter", "asset", "field"]):
        return ["Operations user", "Field technician", "Support analyst", "Platform administrator"]
    if any(word in domain for word in ["hospitality", "property"]):
        return ["Guest", "Property manager", "Operations manager"]
    if "retail" in domain:
        return ["Customer", "Store operator", "Support analyst"]
    return ["End user", "Operations user", "Administrator"]


def _application_names(profile: dict[str, Any]) -> list[str]:
    apps = _dedupe_applications(profile["applications"] or profile["knowledge_registry"]["applications"])
    return [app["name"] for app in apps]


def _constraints_for_profile(profile: dict[str, Any]) -> list[str]:
    constraints = _flatten_standards(profile["development_standards"])
    if profile["ui_guidelines"]["accessibility_rules"]:
        constraints.extend(profile["ui_guidelines"]["accessibility_rules"])
    if profile["technology_stack"]:
        constraints.append("Align implementation with configured technology stack")
    return _unique(constraints) or ["Human approval required before work item creation"]


def _risks_for_profile(profile: dict[str, Any], keywords: list[str]) -> list[str]:
    risks = []
    if "firmware" in keywords:
        risks.append("Firmware rollout visibility may depend on device connectivity and version reporting")
    if "telemetry" in keywords:
        risks.append("Telemetry gaps can reduce confidence in health and monitoring views")
    if "fault" in keywords:
        risks.append("Fault classification rules must be validated against operational expectations")
    if not profile["knowledge_registry"]["modules"]:
        risks.append("Repository intelligence is limited; affected modules should be confirmed manually")
    return _unique(risks) or ["Dependencies and rollout risks should be reviewed before delivery"]


def _dependencies_for_profile(profile: dict[str, Any]) -> list[str]:
    dependencies = []
    modules = profile["knowledge_registry"]["modules"]
    flows = profile["knowledge_registry"]["flows"]
    if modules:
        dependencies.append(f"Module alignment: {', '.join(modules[:4])}")
    if flows:
        dependencies.append(f"Flow coverage: {', '.join(flows[:4])}")
    if profile["readme_analysis"]["architecture_notes"]:
        dependencies.append("Architecture notes from README must be respected")
    return dependencies or ["Project profile and owner review"]


def _acceptance_criteria(title: str, flows: list[str], modules: list[str]) -> list[str]:
    action = _story_action_from_title(title, flows, modules)
    criteria = _story_acceptance_for_action(action, "User")
    cleaned, _rejected = _reject_generic_acceptance_criteria(criteria)
    return cleaned


def _ui_considerations(profile: dict[str, Any], flows: list[str]) -> list[str]:
    considerations = []
    if profile["ui_guidelines"]["component_library"]:
        considerations.append(f"Use {profile['ui_guidelines']['component_library']} components")
    if profile["ui_guidelines"]["accessibility_rules"]:
        considerations.extend(profile["ui_guidelines"]["accessibility_rules"])
    considerations.extend(f"Show clear state transitions for {flow}" for flow in flows[:2])
    return _unique(considerations) or ["Confirm whether UI changes are required"]


def _technical_considerations(profile: dict[str, Any], modules: list[str]) -> list[str]:
    considerations = []
    if modules:
        considerations.append(f"Coordinate changes across {', '.join(modules)}")
    if profile["readme_analysis"]["architecture_notes"]:
        considerations.extend(profile["readme_analysis"]["architecture_notes"][:3])
    if any(profile["technology_stack"].values()):
        considerations.append(f"Use stack: {_format_stack(profile['technology_stack'])}")
    return _unique(considerations)


def _qa_considerations(profile: dict[str, Any], flows: list[str]) -> list[str]:
    considerations = []
    testing = profile["development_standards"]["testing_requirements"]
    considerations.extend(testing)
    considerations.extend(f"Validate positive, negative, and regression paths for {flow}" for flow in flows[:3])
    return _unique(considerations) or ["Create positive, negative, and regression coverage"]


QA_TEST_CATEGORIES = [
    "Positive Tests",
    "Negative Tests",
    "Boundary Tests",
    "Permission Tests",
    "Error Handling Tests",
    "Regression Candidates",
]


def _qa_test_suite(
    title: str,
    description: str,
    acceptance: list[str],
    modules: list[str],
    flows: list[str],
    dependencies: list[str],
    profile: dict[str, Any],
    keywords: list[str],
) -> dict[str, Any]:
    domain = _clean_text(profile.get("domain")) or profile["knowledge_profile_preview"].get("domain") or "Project domain"
    acceptance = _unique(acceptance)
    modules = _unique(modules)[:5]
    flows = _unique(flows)[:5]
    dependencies = _unique(dependencies)[:6]
    tests: list[dict[str, Any]] = []
    next_id = 1
    for test in [
        *_qa_positive_tests(title, acceptance, flows, modules),
        *_qa_negative_tests(title, modules, keywords),
        *_qa_boundary_tests(title, keywords),
        *_qa_permission_tests(title),
        *_qa_error_tests(title, dependencies, keywords),
        *_qa_regression_tests(title, modules, flows, dependencies),
    ]:
        test["test_id"] = f"TC{next_id:03d}"
        tests.append(test)
        next_id += 1
    coverage = _qa_coverage_summary(acceptance, tests)
    breakdown = _qa_coverage_breakdown(tests, acceptance)
    return {
        "test_suite": {
            "title": f"{title} QA Test Suite",
            "domain": domain,
            "story": {"title": title, "description": description},
            "modules": modules,
            "flows": flows,
            "dependencies": dependencies,
            "test_cases": tests,
        },
        "coverage_summary": coverage,
        "coverage_score": _qa_coverage_score(breakdown, coverage),
        "coverage_breakdown": breakdown,
        "generated_test_count": len(tests),
        "coverage_gaps": coverage["uncovered_acceptance_criteria"],
    }


def _append_missing_qa_tests(
    base_suite: dict[str, Any],
    acceptance: list[str],
    title: str,
    modules: list[str],
    flows: list[str],
    dependencies: list[str],
    keywords: list[str],
) -> dict[str, Any]:
    existing_suite = base_suite.get("test_suite") if isinstance(base_suite.get("test_suite"), dict) else {}
    existing_tests = existing_suite.get("test_cases") if isinstance(existing_suite.get("test_cases"), list) else []
    current_tests = [dict(test) for test in existing_tests if isinstance(test, dict)]
    coverage = AcceptanceCoverageEngine().analyze(acceptance, current_tests)
    gaps = TestGapAnalyzer().analyze(acceptance, current_tests)
    next_id = len(current_tests) + 1
    generated: list[dict[str, Any]] = []

    for index, criterion in enumerate(gaps.get("untestedAcceptanceCriteria", []), start=1):
        primary = _qa_case(
            "Functional",
            f"Validate {title.lower()} - missing acceptance criterion {index}",
            ["Approved story and data prerequisites are available."],
            ["Execute the user path for the target acceptance criterion.", "Verify the expected outcome exactly matches the acceptance criterion."],
            criterion,
            "High",
            "Medium",
        )
        primary["covers_acceptance_criteria"] = [criterion]
        primary["test_id"] = f"TC{next_id:03d}"
        next_id += 1
        generated.append(primary)

        secondary_category = "Permission" if any(token in criterion.lower() for token in ["permission", "role", "unauthorized", "access", "security"]) else "Regression"
        secondary = _qa_case(
            secondary_category,
            f"{secondary_category} check for {title.lower()} - acceptance criterion {index}",
            ["Primary behavior is available for verification."],
            ["Exercise the guarded or follow-on path for the acceptance criterion.", "Confirm the criterion remains satisfied without regressions."],
            criterion,
            "Medium",
            "Medium",
        )
        secondary["covers_acceptance_criteria"] = [criterion]
        secondary["test_id"] = f"TC{next_id:03d}"
        next_id += 1
        generated.append(secondary)

    existing_categories = {category_for(test) for test in current_tests}
    for category in ["Functional", "Negative", "Permission", "Regression"]:
        if category in existing_categories:
            continue
        if category == "Functional":
            extra = _qa_positive_test(title, acceptance, flows, modules)
        elif category == "Negative":
            extra = (_qa_negative_tests(title, modules, keywords) or [_qa_case("Negative", f"Negative path for {title.lower()}", ["Approved context exists."], ["Execute an invalid or unsupported path.", "Verify the system rejects the action safely."], "System rejects invalid behavior safely.", "Medium", "Medium")])[0]
        elif category == "Permission":
            extra = (_qa_permission_tests(title) or [_qa_case("Permission", f"Permission check for {title.lower()}", ["Role-restricted access exists."], ["Attempt access with an unauthorized role.", "Verify access is denied."], "Unauthorized users cannot access the behavior.", "High", "High")])[0]
        else:
            extra = (_qa_regression_tests(title, modules, flows, dependencies) or [_qa_case("Regression", f"Regression check for {title.lower()}", ["Existing behavior is available."], ["Repeat the previously supported path.", "Verify no regression is introduced."], "Existing behavior remains intact.", "Medium", "Medium")])[0]
        extra["test_id"] = f"TC{next_id:03d}"
        next_id += 1
        generated.append(extra)

    merged_tests = current_tests + generated
    if not generated:
        return base_suite
    updated_coverage = _qa_coverage_summary(acceptance, merged_tests)
    updated_breakdown = _qa_coverage_breakdown(merged_tests, acceptance)
    return {
        **base_suite,
        "test_suite": {
            **existing_suite,
            "test_cases": merged_tests,
        },
        "coverage_summary": updated_coverage,
        "coverage_score": _qa_coverage_score(updated_breakdown, updated_coverage),
        "coverage_breakdown": updated_breakdown,
        "generated_test_count": len(merged_tests),
        "coverage_gaps": updated_coverage["uncovered_acceptance_criteria"],
        "gap_fill_summary": {
            "untested_acceptance_criteria_before": coverage.get("missingCount", 0),
            "generated_missing_tests": len(generated),
            "remaining_gaps": len(updated_coverage.get("uncovered_acceptance_criteria", [])),
        },
    }


def _attach_qa_intelligence(
    suite: dict[str, Any],
    story: dict[str, Any],
    profile: dict[str, Any],
    execution_package: dict[str, Any] | None = None,
    execution_plan: dict[str, Any] | str | None = None,
    implementation_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    test_suite = suite.get("test_suite") if isinstance(suite.get("test_suite"), dict) else {}
    tests = test_suite.get("test_cases") if isinstance(test_suite.get("test_cases"), list) else []
    acceptance = _string_list(story.get("acceptance_criteria")) or _string_list(test_suite.get("acceptance_criteria"))
    if not acceptance:
        acceptance = _string_list(test_suite.get("story", {}).get("acceptance_criteria") if isinstance(test_suite.get("story"), dict) else [])
    qa_artifact = QAWorkspaceService().evaluate(
        story=story,
        acceptance_criteria=acceptance,
        execution_package=execution_package or {},
        execution_plan=execution_plan,
        repository_snapshot=profile.get("repository_snapshot") if isinstance(profile.get("repository_snapshot"), dict) else {},
        knowledge_registry=profile.get("knowledge_registry") if isinstance(profile.get("knowledge_registry"), dict) else {},
        engineering_graph=profile.get("engineering_graph") if isinstance(profile.get("engineering_graph"), dict) else {},
        implementation_validation=implementation_validation or {},
        tests=tests,
    )
    readiness = qa_artifact.get("qaReadiness", {})
    recommendation = qa_artifact.get("releaseRecommendation", {})
    return {
        **suite,
        "qa_intelligence": qa_artifact,
        "qa_readiness": readiness,
        "release_recommendation": recommendation,
        "qa_status": readiness.get("status") or "Needs Review",
        "release_status": recommendation.get("recommendation") or "Needs More Testing",
    }


def _normalize_phi_qa_suite(incoming: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    suite = incoming.get("test_suite") if isinstance(incoming.get("test_suite"), dict) else {}
    base_suite = base.get("test_suite") if isinstance(base.get("test_suite"), dict) else {}
    tests_input = suite.get("test_cases") or incoming.get("test_cases") or []
    tests: list[dict[str, Any]] = []
    for index, item in enumerate(tests_input if isinstance(tests_input, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        category = _clean_text(item.get("category")) or "Positive Tests"
        if category not in QA_TEST_CATEGORIES:
            category = _normalize_qa_category(category)
        tests.append(
            {
                "test_id": _clean_text(item.get("test_id")) or f"TC{index:03d}",
                "category": category,
                "title": _clean_text(item.get("title")) or f"Validate {base_suite.get('story', {}).get('title') or 'story behavior'}",
                "preconditions": _string_list(item.get("preconditions")) or ["Approved story and acceptance criteria are available."],
                "steps": _string_list(item.get("steps")) or ["Execute the approved user behavior.", "Verify the expected outcome."],
                "expected_result": _clean_text(item.get("expected_result") or item.get("expected")) or "Expected behavior is observed.",
                "priority": _clean_text(item.get("priority")) or "Medium",
                "risk_level": _clean_text(item.get("risk_level")) or "Medium",
                "covers_acceptance_criteria": item.get("covers_acceptance_criteria") if isinstance(item.get("covers_acceptance_criteria"), list) else [],
            }
        )
    if not tests:
        return {}
    for index, test in enumerate(tests, start=1):
        test["test_id"] = _clean_text(test.get("test_id")) or f"TC{index:03d}"
    acceptance = _string_list(base.get("test_suite", {}).get("acceptance_criteria")) or _string_list(base.get("acceptance_criteria"))
    if not acceptance:
        story = base_suite.get("story") if isinstance(base_suite.get("story"), dict) else {}
        acceptance = _string_list(story.get("acceptance_criteria"))
    coverage_summary = incoming.get("coverage_summary") if isinstance(incoming.get("coverage_summary"), dict) else _qa_coverage_summary(acceptance, tests)
    coverage_breakdown = incoming.get("coverage_breakdown") if isinstance(incoming.get("coverage_breakdown"), dict) else _qa_coverage_breakdown(tests, acceptance)
    coverage_score = int(incoming.get("coverage_score") or _qa_coverage_score(coverage_breakdown, coverage_summary))
    normalized_suite = {
        **base_suite,
        **suite,
        "test_cases": tests,
    }
    return {
        "test_suite": normalized_suite,
        "coverage_summary": coverage_summary,
        "coverage_score": coverage_score,
        "coverage_breakdown": coverage_breakdown,
        "generated_test_count": int(incoming.get("generated_test_count") or len(tests)),
        "coverage_gaps": _string_list(incoming.get("coverage_gaps")) or _string_list(coverage_summary.get("uncovered_acceptance_criteria")),
    }


def _normalize_qa_category(value: str) -> str:
    lowered = value.lower()
    if "negative" in lowered:
        return "Negative Tests"
    if "boundary" in lowered or "edge" in lowered:
        return "Boundary Tests"
    if "permission" in lowered or "role" in lowered or "access" in lowered:
        return "Permission Tests"
    if "error" in lowered or "failure" in lowered or "exception" in lowered:
        return "Error Handling Tests"
    if "regression" in lowered:
        return "Regression Candidates"
    return "Positive Tests"


def _qa_positive_tests(title: str, acceptance: list[str], flows: list[str], modules: list[str]) -> list[dict[str, Any]]:
    if not acceptance:
        expected = f"{title} completes successfully."
        flow = flows[0] if flows else "approved user flow"
        module = modules[0] if modules else "affected module"
        return [_qa_case(
            "Positive Tests",
            f"Open valid {title.lower()}",
            [f"User has permission for {flow}.", f"{module} data is available."],
            [
                f"Navigate to the {flow} entry point.",
                f"Select a valid record for {title}.",
                "Review the displayed result.",
            ],
            expected,
            "High",
            "Medium",
            [0],
        )]
    
    tests = []
    for i, criterion in enumerate(acceptance):
        flow = flows[min(i, len(flows) - 1)] if flows else "approved user flow"
        module = modules[min(i, len(modules) - 1)] if modules else "affected module"
        tests.append(_qa_case(
            "Positive Tests",
            f"Validate {title.lower()} - scenario {i + 1}",
            [f"User has permission for {flow}.", f"{module} data is available."],
            [
                f"Navigate to the {flow} entry point.",
                f"Exercise the target functionality for {title}.",
                "Verify the expected outcome matches the acceptance criterion.",
            ],
            criterion,
            "High",
            "Medium",
            [i],
        ))
    return tests

def _qa_negative_tests(title: str, modules: list[str], keywords: list[str]) -> list[dict[str, Any]]:
    record_name = "Event ID" if any(word in keywords for word in ["fault", "event"]) else "Record ID"
    tests = [
        _qa_case(
            "Negative Tests",
            f"Reject invalid {record_name}",
            ["User is signed in.", f"No active data exists for the invalid {record_name}."],
            [f"Enter an invalid {record_name}.", f"Attempt to open {title}."],
            "System displays a clear not-found or invalid-data message without showing stale data.",
            "High",
            "High",
            [1],
        ),
        _qa_case(
            "Negative Tests",
            f"Handle deleted {title.lower()} record",
            ["A previously available record has been deleted or archived."],
            ["Open the deleted or archived record from a saved link.", "Refresh the result."],
            "System explains that the record is no longer available and does not expose partial data.",
            "Medium",
            "Medium",
            [2],
        ),
    ]
    if any("device" in module.lower() or "telemetry" in module.lower() for module in modules):
        tests.append(
            _qa_case(
                "Negative Tests",
                "Handle missing device data",
                ["The selected device has incomplete or missing telemetry data."],
                [f"Open {title} for the affected device.", "Review the displayed fields."],
                "Available fields remain visible and missing device data is labeled as unavailable.",
                "High",
                "High",
                [3],
            )
        )
    return tests


def _qa_boundary_tests(title: str, keywords: list[str]) -> list[dict[str, Any]]:
    subject = "fault events" if any(word in keywords for word in ["fault", "event"]) else "records"
    return [
        _qa_case(
            "Boundary Tests",
            f"Display first and last {subject}",
            [f"At least two {subject} exist in the data set."],
            ["Open the list view.", "Select the first record.", "Return and select the last record."],
            "First and last records open successfully with the correct details.",
            "Medium",
            "Medium",
            [0, 1],
        ),
        _qa_case(
            "Boundary Tests",
            "Support long identifiers and maximum result set",
            ["Data includes a long identifier and the maximum supported result count."],
            ["Load the result list.", "Search or filter for the long identifier.", "Review pagination or result limits."],
            "Long identifiers remain readable and maximum results are handled without truncating required fields.",
            "Medium",
            "Medium",
            [1],
        ),
    ]


def _qa_permission_tests(title: str) -> list[dict[str, Any]]:
    return [
        _qa_case(
            "Permission Tests",
            "Operator access is allowed",
            ["User has Operator role."],
            [f"Open {title}.", "Perform the primary view action."],
            "Operator can complete the permitted action and see authorized data.",
            "High",
            "Medium",
            [0],
        ),
        _qa_case(
            "Permission Tests",
            "Unauthorized user access is restricted",
            ["User has no permission for the story scope."],
            [f"Attempt to open {title}.", "Review the response."],
            "User sees an access-restricted message and no protected data is displayed.",
            "High",
            "High",
            [2],
        ),
    ]


def _qa_error_tests(title: str, dependencies: list[str], keywords: list[str]) -> list[dict[str, Any]]:
    primary_dependency = dependencies[0] if dependencies else "Backend service"
    timeout_name = "Telemetry timeout" if "telemetry" in keywords else "Backend timeout"
    return [
        _qa_case(
            "Error Handling Tests",
            f"Recover from {primary_dependency} failure",
            [f"{primary_dependency} is unavailable or returns an error."],
            [f"Open {title}.", "Trigger a refresh or load action."],
            "System displays a recoverable error message and preserves the user's current context.",
            "High",
            "High",
            [3],
        ),
        _qa_case(
            "Error Handling Tests",
            timeout_name,
            ["The request exceeds the expected response threshold."],
            [f"Open {title} while the dependency is delayed.", "Wait for timeout handling."],
            "System shows a timeout message and offers retry when retry is safe.",
            "High",
            "High",
            [3],
        ),
        _qa_case(
            "Error Handling Tests",
            "Network error during refresh",
            ["Network connectivity is interrupted."],
            ["Open the story view.", "Refresh while network is unavailable."],
            "System shows a network error without losing previously loaded safe data.",
            "Medium",
            "Medium",
            [3],
        ),
    ]


def _qa_regression_tests(title: str, modules: list[str], flows: list[str], dependencies: list[str]) -> list[dict[str, Any]]:
    areas = _unique([*modules[:3], *flows[:3], *dependencies[:2]])
    if not areas:
        areas = ["Primary user flow"]
    tests = []
    for area in areas[:5]:
        tests.append(
            _qa_case(
                "Regression Candidates",
                f"Regression check for {area}",
                [f"{area} exists in the approved project scope."],
                [f"Execute the existing regression path for {area}.", f"Verify {title} did not change expected behavior."],
                f"{area} remains stable after the story change.",
                "Medium",
                "Medium",
                [],
            )
        )
    return tests


def _qa_case(
    category: str,
    title: str,
    preconditions: list[str],
    steps: list[str],
    expected: str,
    priority: str,
    risk_level: str,
    covers: list[int],
) -> dict[str, Any]:
    return {
        "test_id": "",
        "category": category,
        "title": title,
        "preconditions": preconditions,
        "steps": steps,
        "expected_result": expected,
        "priority": priority,
        "risk_level": risk_level,
        "covers_acceptance_criteria": covers,
    }


def _qa_coverage_summary(acceptance: list[str], tests: list[dict[str, Any]]) -> dict[str, Any]:
    covered_indexes = []
    for index, criterion in enumerate(acceptance):
        if any(_qa_test_covers_criterion(test, criterion) for test in tests):
            covered_indexes.append(index)
    uncovered = [criterion for index, criterion in enumerate(acceptance) if index not in covered_indexes]
    percent = int(round((len(covered_indexes) / len(acceptance)) * 100)) if acceptance else 100
    return {
        "acceptance_criteria_count": len(acceptance),
        "covered_acceptance_criteria_count": len(covered_indexes),
        "coverage_percent": percent,
        "covered_acceptance_criteria": [acceptance[index] for index in covered_indexes],
        "uncovered_acceptance_criteria": uncovered,
    }


def _qa_test_covers_criterion(test: dict[str, Any], criterion: str) -> bool:
    criterion_lower = criterion.lower()
    test_text = " ".join(
        [
            str(test.get("title") or ""),
            str(test.get("expected_result") or ""),
            " ".join(_string_list(test.get("preconditions"))),
            " ".join(_string_list(test.get("steps"))),
        ]
    ).lower()
    if any(token in criterion_lower for token in ["permission", "role", "unauthorized", "access"]):
        return any(token in test_text for token in ["permission", "operator", "unauthorized", "access-restricted", "authorized"])
    if any(token in criterion_lower for token in ["missing", "unavailable", "error", "timeout", "network", "retry"]):
        return any(token in test_text for token in ["missing", "unavailable", "error", "timeout", "network", "retry"])
    if any(token in criterion_lower for token in ["display", "device id", "fault type", "severity", "timestamp", "status", "location"]):
        return any(token in test_text for token in ["display", "device", "fault", "severity", "identifier", "details", "record"])
    if any(token in criterion_lower for token in ["open", "view", "select", "refresh"]):
        return any(token in test_text for token in ["open", "view", "select", "refresh", "valid"])
    criterion_terms = _qa_coverage_terms(criterion_lower)
    test_terms = _qa_coverage_terms(test_text)
    if not criterion_terms:
        return False
    overlap = criterion_terms & test_terms
    return len(overlap) >= min(3, len(criterion_terms))


def _qa_coverage_terms(text: str) -> set[str]:
    stop_words = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "when",
        "from",
        "this",
        "into",
        "user",
        "can",
        "are",
        "is",
        "a",
        "an",
        "of",
        "to",
    }
    return {word.strip(".,:;()[]{}").lower() for word in text.split() if len(word.strip(".,:;()[]{}")) > 3 and word.lower() not in stop_words}


def _qa_coverage_breakdown(tests: list[dict[str, Any]], acceptance: list[str]) -> dict[str, Any]:
    counts = {category: sum(1 for test in tests if test["category"] == category) for category in QA_TEST_CATEGORIES}
    return {
        "positive_coverage": counts["Positive Tests"],
        "negative_coverage": counts["Negative Tests"],
        "boundary_coverage": counts["Boundary Tests"],
        "permission_coverage": counts["Permission Tests"],
        "error_coverage": counts["Error Handling Tests"],
        "regression_coverage": counts["Regression Candidates"],
        "category_counts": counts,
        "acceptance_criteria_count": len(acceptance),
    }


def _qa_coverage_score(breakdown: dict[str, Any], summary: dict[str, Any]) -> int:
    score = 0
    if breakdown["positive_coverage"] >= 1:
        score += 20
    if breakdown["negative_coverage"] >= 2:
        score += 20
    if breakdown["permission_coverage"] >= 2:
        score += 15
    if breakdown["error_coverage"] >= 2:
        score += 20
    if breakdown["regression_coverage"] >= 2:
        score += 15
    if int(summary.get("coverage_percent") or 0) >= 80:
        score += 10
    return min(score, 100)


def _sentence(title: str, detail: str) -> str:
    detail = _clean_text(detail)
    if detail:
        return detail if detail.endswith(".") else f"{detail}."
    return f"{title}."


def _clean_title(value: str) -> str:
    acronyms = {"api": "API", "ui": "UI", "ux": "UX", "qa": "QA", "jwt": "JWT", "oauth": "OAuth", "http": "HTTP", "https": "HTTPS", "rest": "REST"}
    words = []
    for word in _clean_text(value).replace("_", " ").replace("-", " ").split():
        lowered = word.lower()
        words.append(acronyms.get(lowered, word.capitalize()))
    return " ".join(words)


def _remove_generic_names(values: list[str]) -> list[str]:
    generic_tokens = ["feature slice", "story 1", "story 2", "slice 1", "slice 2"]
    return [value for value in values if not any(token in value.lower() for token in generic_tokens)]


def _impact_modules(profile: dict[str, Any], title: str, description: str, keywords: list[str], fallback_count: int = 3) -> list[str]:
    modules = profile["knowledge_registry"]["modules"]
    selected = _select_relevant_items(modules, title, description, fallback_count=fallback_count)
    if any(keyword in keywords for keyword in ["otp", "login", "token", "session", "auth"]):
        selected = _unique(["Authentication", *selected])
    if any(keyword in keywords for keyword in ["fault", "event"]):
        selected = _unique(["Fault Monitoring", *selected])
    if "telemetry" in keywords:
        selected = _unique(["Telemetry", *selected])
    if "firmware" in keywords:
        selected = _unique(["Firmware Update", *selected])
    return selected[:fallback_count + 2]


def _impact_flows(profile: dict[str, Any], title: str, description: str, keywords: list[str], fallback_count: int = 3) -> list[str]:
    flows = _select_relevant_items(profile["knowledge_registry"]["flows"], title, description, fallback_count=fallback_count)
    if any(keyword in keywords for keyword in ["otp", "login", "auth"]):
        flows = _unique(["Login", "Token Refresh", *flows])
    if any(keyword in keywords for keyword in ["fault", "event"]):
        flows = _unique(["Fault Event Review", *flows])
    if "telemetry" in keywords:
        flows = _unique(["Telemetry Review", *flows])
    if "firmware" in keywords:
        flows = _unique(["Firmware Rollout", *flows])
    return flows[:fallback_count + 2]


def _impact_applications(profile: dict[str, Any], keywords: list[str]) -> list[str]:
    apps = _application_names(profile)
    if apps:
        return apps
    if any(keyword in keywords for keyword in ["otp", "login", "fault", "telemetry"]):
        return ["Mobile App", "Backend API"]
    return ["Application"]


def _impact_components(profile: dict[str, Any], modules: list[str], flows: list[str]) -> list[str]:
    components = profile["knowledge_registry"]["components"]
    if components:
        return components[:6]
    generated = []
    generated.extend(f"{module} component" for module in modules[:3])
    generated.extend(f"{flow} screen" for flow in flows[:2])
    return _unique(generated)


def _impact_dependencies(profile: dict[str, Any], keywords: list[str], modules: list[str], flows: list[str]) -> list[str]:
    dependencies = []
    if any(keyword in keywords for keyword in ["otp", "sms"]):
        dependencies.extend(["Auth Service", "SMS Provider"])
    if any(keyword in keywords for keyword in ["token", "session", "login", "auth"]):
        dependencies.extend(["Auth Service", "Session Store", "Token Refresh"])
    if any(keyword in keywords for keyword in ["fault", "event"]):
        dependencies.extend(["Event Repository", "Fault Classification Rules"])
    if "telemetry" in keywords:
        dependencies.extend(["Telemetry Service", "Device Connectivity"])
    if "firmware" in keywords:
        dependencies.extend(["Firmware Version Service", "Device Update Channel"])
    dependencies.extend(_dependencies_for_profile(profile))
    dependencies.extend(f"{module} owner review" for module in modules[:2])
    dependencies.extend(f"{flow} regression coverage" for flow in flows[:2])
    return _unique(dependencies)[:10]


def _impact_risks(profile: dict[str, Any], keywords: list[str], modules: list[str], flows: list[str]) -> list[str]:
    risks = []
    if any(keyword in keywords for keyword in ["otp", "login", "token", "session", "auth"]):
        risks.extend(["Session invalidation", "Token compatibility", "Authentication failure handling"])
    if any(keyword in keywords for keyword in ["fault", "event"]):
        risks.extend(["Large event history performance", "Fault detail accuracy"])
    if "telemetry" in keywords:
        risks.extend(["Connectivity issues", "Telemetry freshness gaps"])
    if "firmware" in keywords:
        risks.extend(["Version mismatch during rollout", "Partial device upgrade visibility"])
    risks.extend(_risks_for_profile(profile, keywords))
    if not modules and not flows:
        risks.append("Impact confidence is limited without repository intelligence")
    return _unique(risks)[:10]


def _integration_points(profile: dict[str, Any], modules: list[str], flows: list[str]) -> list[str]:
    points = []
    points.extend(f"{module} API" for module in modules[:4])
    points.extend(f"{flow} workflow" for flow in flows[:4])
    if profile["readme_analysis"]["architecture_notes"]:
        points.append("Architecture constraints from README")
    return _unique(points) or ["Project profile integration points"]


def _recommended_reviewers(profile: dict[str, Any], modules: list[str], flows: list[str]) -> list[str]:
    reviewers = ["Product owner"]
    if modules:
        reviewers.append("Module owner")
    if flows:
        reviewers.append("QA lead")
    if any(app["type"] in ["Mobile", "Web Portal"] for app in profile["applications"]):
        reviewers.append("UI engineer")
    if any(profile["technology_stack"].values()):
        reviewers.append("Technical lead")
    return _unique(reviewers)


def _cross_team_dependencies(profile: dict[str, Any], modules: list[str]) -> list[str]:
    dependencies = []
    app_types = {app["type"] for app in profile["applications"]}
    if len(app_types) > 1:
        dependencies.append(f"Coordinate across {', '.join(sorted(app_types))} teams")
    dependencies.extend(f"{module} module owner alignment" for module in modules[:3])
    return _unique(dependencies) or ["Product and engineering alignment"]


def _program_dependencies(profile: dict[str, Any], modules: list[str], flows: list[str]) -> list[str]:
    dependencies = _cross_team_dependencies(profile, modules)
    dependencies.extend(f"{flow} rollout sequencing" for flow in flows[:3])
    dependencies.append("Release planning and stakeholder communication")
    return _unique(dependencies)


def _rollout_strategy(profile: dict[str, Any], keywords: list[str]) -> list[str]:
    strategy = ["Start with a controlled pilot", "Validate telemetry and support signals before broad rollout"]
    if any(keyword in keywords for keyword in ["firmware", "device", "fault", "telemetry"]):
        strategy.extend(["Roll out by device cohort", "Monitor operational dashboards after each cohort"])
    if any(app["type"] in ["Mobile", "Web Portal"] for app in profile["applications"]):
        strategy.append("Coordinate UI release notes and user enablement")
    return _unique(strategy)


def _execution_readiness_score(profile: dict[str, Any], has_impact: bool = False) -> dict[str, Any]:
    registry_data = _normalize_knowledge_registry(profile.get("knowledge_registry"))
    applications = _normalize_applications(profile.get("applications")) or registry_data["applications"]
    repository_analyzed = profile["repository_connection"]["status"] in {"README analyzed", "Repository documents analyzed"} or bool(registry_data["source_files"])
    project_profile = 25 if profile.get("project_description") else 0
    repository = 25 if repository_analyzed else 0
    registry = 20 if (registry_data["modules"] and registry_data["flows"] and applications) else 0
    impact = 15 if has_impact else 0
    standards = 15 if (_flatten_standards(profile["development_standards"]) or registry_data["standards"]) else 0
    score = project_profile + repository + registry + impact + standards
    has_required_intelligence = bool(repository_analyzed and registry_data["modules"] and registry_data["flows"] and applications)
    if score >= 85 and has_required_intelligence:
        label = "Ready"
    elif score >= 40:
        label = "Partially Ready"
    else:
        label = "Not Ready"
    return {
        "score": score,
        "label": label,
        "result": label,
        "breakdown": {
            "project_profile": project_profile,
            "repository_intelligence": repository,
            "knowledge_registry": registry,
            "impact_analysis": impact,
            "development_standards": standards,
        },
    }


def _project_phi_json(
    operation: str,
    profile: dict[str, Any],
    item: dict[str, Any],
    deterministic: dict[str, Any],
    options: dict[str, Any] | None,
    expected_keys: list[str],
) -> dict[str, Any]:
    prompt_attempts = _project_phi_prompt_attempts(operation, profile, item, deterministic, expected_keys)
    return _project_phi_probe(prompt_attempts, options, expected_keys=expected_keys)


def _project_phi_probe(
    prompt_attempts: list[tuple[str, dict[str, Any]]] | str,
    options: dict[str, Any] | None,
    expected_keys: list[str] | None = None,
) -> dict[str, Any]:
    options = options or {}
    attempts = prompt_attempts if isinstance(prompt_attempts, list) else [(prompt_attempts, _with_final_prompt_diagnostics(PROJECT_PHI_SYSTEM_PROMPT, prompt_attempts, {}))]
    context_diagnostics = attempts[0][1] if attempts else {}
    force_provider = _clean_text(options.get("force_provider"))
    allow_fallback = bool(options.get("allow_fallback", False))
    deterministic_only = _clean_text(options.get("mode")) == "deterministic_only" or force_provider == "deterministic_fallback"
    if deterministic_only:
        return {
            "used": False,
            "blocked": False,
            "parsed": {},
            "metadata": _with_context_diagnostics(_fallback_metadata("deterministic_fallback", "deterministic_only mode selected."), context_diagnostics),
        }
    if force_provider == "domain_fallback":
        return {
            "used": False,
            "blocked": False,
            "parsed": {},
            "metadata": _with_context_diagnostics(_fallback_metadata("domain_fallback", "domain_fallback provider was forced."), context_diagnostics),
        }
    use_phi = force_provider == "azure_phi" or _project_phi_enabled_by_default()
    if not use_phi:
        metadata = _with_context_diagnostics(
            _fallback_metadata("domain_fallback", "AI_GEN_PROJECT_INTELLIGENCE_USE_PHI disabled Project Intelligence Phi calls."),
            context_diagnostics,
        )
        metadata["phi_status"] = "skipped"
        return _fallback_or_block(metadata, force_provider, allow_fallback)
    provider = get_refinement_provider()
    if provider is None or not provider.is_enabled():
        metadata = _fallback_metadata("deterministic_fallback", "Azure Phi provider is not configured.")
        metadata["phi_status"] = "not_configured"
        metadata = _with_context_diagnostics(metadata, context_diagnostics)
        return _fallback_or_block(metadata, force_provider, allow_fallback)
    health = provider.health_snapshot() if hasattr(provider, "health_snapshot") else {}
    health_status = str(health.get("health") or "").lower()
    if force_provider != "azure_phi" and health_status == "unhealthy":
        metadata = _fallback_metadata("domain_fallback", f"Azure Phi health is {health.get('health') or 'unknown'}.")
        metadata.update(_provider_status_metadata(provider, {}, health))
        metadata["provider_used"] = "domain_fallback"
        metadata["source"] = "domain_fallback"
        metadata["fallback_used"] = True
        metadata["fallback_reason"] = f"Azure Phi health is {health.get('health') or 'unknown'}."
        metadata = _with_context_diagnostics(metadata, context_diagnostics)
        return _fallback_or_block(metadata, force_provider, allow_fallback)
    last_guard_diagnostics: dict[str, Any] | None = None
    last_probe: dict[str, Any] = {}
    last_failure_diagnostics: dict[str, Any] = {}
    for prompt, attempt_diagnostics in attempts:
        context_diagnostics = dict(attempt_diagnostics or {})
        if not context_diagnostics.get("operation") and options.get("operation"):
            context_diagnostics["operation"] = _clean_text(options.get("operation"))
        if int(context_diagnostics.get("final_prompt_tokens") or 0) > int(context_diagnostics.get("model_context_limit") or 0):
            last_guard_diagnostics = context_diagnostics
            logger.warning(
                "project-intelligence phi adaptive_context_retry operation=%s retry_attempt=%s final_prompt_tokens=%s model_context_limit=%s compressed_context_tokens=%s largest_sections=%s",
                context_diagnostics.get("operation") or "unknown",
                context_diagnostics.get("retry_attempt"),
                context_diagnostics.get("final_prompt_tokens"),
                context_diagnostics.get("model_context_limit"),
                context_diagnostics.get("compressed_context_tokens"),
                context_diagnostics.get("largest_context_sections"),
            )
            continue
        logger.info(
            "project-intelligence phi prompt_ready retry_attempt=%s final_prompt_tokens=%s model_context_limit=%s compressed_context_tokens=%s compression_ratio=%s",
            context_diagnostics.get("retry_attempt"),
            context_diagnostics.get("final_prompt_tokens"),
            context_diagnostics.get("model_context_limit"),
            context_diagnostics.get("compressed_context_tokens"),
            context_diagnostics.get("compression_ratio"),
        )
        try:
            prompt_payload = json.loads(prompt)
        except (TypeError, ValueError):
            prompt_payload = {"prompt": prompt}
        probe = probe_json_with_budget(
            provider,
            _prompt_budget_sections(prompt_payload if isinstance(prompt_payload, dict) else {"prompt": prompt}),
            operation=str(context_diagnostics.get("operation") or "project_intelligence"),
            system_prompt=PROJECT_PHI_SYSTEM_PROMPT,
            max_tokens=int(options.get("max_tokens") or 900),
            timeout_seconds=int(options.get("timeout_seconds")) if options.get("timeout_seconds") else None,
            response_format_enabled=False,
            allow_retry_without_response_format=True,
        )
        last_probe = probe
        parsed = probe.get("parsed_json") if isinstance(probe.get("parsed_json"), dict) else {}
        has_expected = bool(parsed) and (not expected_keys or any(key in parsed for key in expected_keys))
        metadata = _with_context_diagnostics(_provider_status_metadata(provider, probe, health), context_diagnostics)
        if has_expected:
            metadata.update(
                {
                    "provider_used": "azure_phi",
                    "source": "azure_phi",
                    "phi_status": "success",
                    "fallback_used": False,
                    "fallback_reason": "",
                }
            )
            return {"used": True, "blocked": False, "parsed": parsed, "metadata": metadata}
        if _should_persist_feature_generation_failure(context_diagnostics, probe):
            last_failure_diagnostics = _persist_feature_generation_failure(
                prompt=prompt,
                probe=probe,
                context_diagnostics=context_diagnostics,
                provider=provider,
                expected_keys=expected_keys or [],
            )
            metadata.update(last_failure_diagnostics)
        if (probe.get("failure_reason") or probe.get("status")) != "prompt_too_long":
            break
    if last_guard_diagnostics and not last_probe:
        context_diagnostics = last_guard_diagnostics
        logger.warning(
            "project-intelligence phi blocked_by_budget_guard operation=%s final_prompt_tokens=%s model_context_limit=%s compressed_context_tokens=%s largest_sections=%s",
            context_diagnostics.get("operation") or "unknown",
            context_diagnostics.get("final_prompt_tokens"),
            context_diagnostics.get("model_context_limit"),
            context_diagnostics.get("compressed_context_tokens"),
            context_diagnostics.get("largest_context_sections"),
        )
        metadata = _fallback_metadata("domain_fallback" if allow_fallback else "azure_phi", _budget_guard_reason(context_diagnostics))
        metadata.update(_provider_status_metadata(provider, {}, health))
        metadata.update(
            {
                "provider_used": "domain_fallback" if allow_fallback else "azure_phi",
                "source": "domain_fallback" if allow_fallback else "azure_phi",
                "phi_status": "blocked_by_budget_guard",
                "fallback_used": allow_fallback,
                "fallback_reason": _budget_guard_reason(context_diagnostics),
                "prompt_too_long_stage": "before_provider_call",
            }
        )
        metadata = _with_context_diagnostics(metadata, context_diagnostics)
        return _fallback_or_block(metadata, force_provider, allow_fallback)
    probe = last_probe
    metadata = _with_context_diagnostics(_provider_status_metadata(provider, probe, health), context_diagnostics)
    metadata.update(
        {
            "provider_used": "domain_fallback" if allow_fallback else "azure_phi",
            "source": "domain_fallback" if allow_fallback else "azure_phi",
            "phi_status": probe.get("failure_reason") or probe.get("status") or "unusable_response",
            "fallback_used": allow_fallback,
            "fallback_reason": probe.get("failure_message") or probe.get("parse_error") or "Azure Phi returned unusable structured output.",
            "prompt_too_long_stage": _prompt_too_long_stage(probe),
        }
    )
    if _should_persist_feature_generation_failure(context_diagnostics, probe) and not metadata.get("diagnostics_path"):
        metadata.update(
            last_failure_diagnostics
            or _persist_feature_generation_failure(
                prompt=attempts[-1][0] if attempts else "",
                probe=probe,
                context_diagnostics=context_diagnostics,
                provider=provider,
                expected_keys=expected_keys or [],
            )
        )
    if metadata.get("phi_status") == "prompt_too_long":
        logger.warning(
            "project-intelligence phi prompt_too_long_stage=%s final_prompt_tokens=%s model_context_limit=%s fallback_reason=%s",
            metadata.get("prompt_too_long_stage"),
            metadata.get("final_prompt_tokens"),
            metadata.get("model_context_limit"),
            metadata.get("fallback_reason"),
        )
    return _fallback_or_block(metadata, force_provider, allow_fallback)


def _project_phi_enabled_by_default() -> bool:
    value = os.getenv("AI_GEN_PROJECT_INTELLIGENCE_USE_PHI")
    if value is None:
        return True
    return value.strip().lower() not in {"0", "false", "no", "off", "disabled"}


def _fallback_or_block(metadata: dict[str, Any], force_provider: str, allow_fallback: bool) -> dict[str, Any]:
    blocked = not allow_fallback or (force_provider == "azure_phi" and not allow_fallback)
    if blocked:
        metadata["fallback_used"] = False
        metadata["provider_used"] = "azure_phi"
        metadata["source"] = "azure_phi"
    return {"used": False, "blocked": blocked, "parsed": {}, "metadata": metadata}


def _project_phi_prompt(
    operation: str,
    profile: dict[str, Any],
    item: dict[str, Any],
    deterministic: dict[str, Any],
    expected_keys: list[str],
) -> str:
    prompt, _diagnostics = _project_phi_prompt_with_diagnostics(operation, profile, item, deterministic, expected_keys)
    return prompt


def _project_phi_prompt_attempts(
    operation: str,
    profile: dict[str, Any],
    item: dict[str, Any],
    deterministic: dict[str, Any],
    expected_keys: list[str],
) -> list[tuple[str, dict[str, Any]]]:
    attempts: list[tuple[str, dict[str, Any]]] = []
    for attempt_number, budget_profile in enumerate(_adaptive_budget_profiles(operation), start=1):
        budget_tokens = int(budget_profile["context_budget"])
        draft_budget_tokens = int(budget_profile.get("draft_budget") or _draft_budget_tokens())
        level = int(budget_profile.get("compression_level") or _compression_level_for_budget(budget_tokens))
        prompt, diagnostics = _build_project_phi_prompt(
            operation,
            profile,
            item,
            deterministic,
            expected_keys,
            compression_level=level,
            budget_tokens=budget_tokens,
            draft_budget_tokens=draft_budget_tokens,
            retry_attempt=attempt_number,
        )
        attempts.append((prompt, diagnostics))
    return attempts


def _project_phi_prompt_with_diagnostics(
    operation: str,
    profile: dict[str, Any],
    item: dict[str, Any],
    deterministic: dict[str, Any],
    expected_keys: list[str],
) -> tuple[str, dict[str, Any]]:
    attempts = _project_phi_prompt_attempts(operation, profile, item, deterministic, expected_keys)
    for prompt, diagnostics in attempts:
        if diagnostics["final_prompt_tokens"] <= diagnostics["model_context_limit"]:
            return prompt, diagnostics
    return attempts[-1]


def _apply_prompt_budget_manager(operation: str, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Optimize prompt sections with a provider-aware budget profile."""

    provider_name = os.getenv("AI_GEN_PROJECT_INTELLIGENCE_PROVIDER") or os.getenv("AI_GEN_REFINER_PROVIDER") or "azure_phi"
    provider_model = os.getenv("AI_GEN_REFINER_DEPLOYMENT") or os.getenv("AI_GEN_REFINER_MODEL") or ""
    profile = budgetProfileForProvider(
        provider_name,
        provider_model,
        operation=operation,
        max_prompt_chars=_provider_prompt_char_limit(),
        context_limit_override=_model_context_limit_tokens(),
    )
    sections = _prompt_budget_sections(payload)
    budget_result = buildPrompt(sections, profile)
    optimized_payload = _payload_from_prompt_budget_sections(payload, budget_result["sections"])
    diagnostics = dict(budget_result["diagnostics"])
    diagnostics.update(
        {
            "prompt_budget_manager_used": True,
            "prompt_budget_estimated_tokens": diagnostics.get("estimated_tokens"),
            "prompt_budget_remaining_tokens": diagnostics.get("remaining_budget"),
            "prompt_budget_overflow_tokens": diagnostics.get("overflow_tokens"),
            "prompt_budget_largest_section": diagnostics.get("largest_section"),
        }
    )
    return optimized_payload, diagnostics


def _prompt_budget_sections(payload: dict[str, Any]) -> list[PromptSection]:
    project_context = payload.get("project_context") if isinstance(payload.get("project_context"), dict) else {}
    knowledge_registry = project_context.get("knowledge_registry") if isinstance(project_context.get("knowledge_registry"), dict) else {}
    project_summary = project_context.get("project_summary") if isinstance(project_context.get("project_summary"), dict) else {}
    draft = payload.get("draft") if isinstance(payload.get("draft"), dict) else {}
    input_item = payload.get("input") if isinstance(payload.get("input"), dict) else {}
    repository_evidence = {
        "context_capsule": project_context.get("context_source") == "context_capsule",
        "capsule_id": project_context.get("capsule_id"),
        "capsule_type": project_context.get("capsule_type"),
        "knowledge_registry": knowledge_registry,
        "capsule_focus": project_context.get("capsule_focus"),
        "relevant_files": draft.get("relevant_files") or draft.get("recommended_files") or input_item.get("relevant_files"),
    }
    repository_evidence = {key: value for key, value in repository_evidence.items() if value not in (None, "", [], {})}
    knowledge_summary = {
        "project_name": project_context.get("project_name"),
        "domain": project_context.get("domain"),
        "project_type": project_context.get("project_type"),
        "description": project_context.get("description"),
        "project_summary": project_summary,
        "technology_stack": project_context.get("technology_stack"),
        "development_standards": project_context.get("development_standards"),
        "ui_guidelines": project_context.get("ui_guidelines"),
    }
    knowledge_summary = {key: value for key, value in knowledge_summary.items() if value not in (None, "", [], {})}
    sections = [
        _prompt_budget_section("current_intent", "Current Intent", 100, True, False, "intent", {"operation": payload.get("operation"), "input": input_item}),
        _prompt_budget_section("current_capability", "Current Capability", 100, True, False, "capability", _current_capability_section(project_context, input_item, draft)),
        _prompt_budget_section("dna", "DNA", 95, True, False, "dna", _dna_section(input_item, draft)),
        _prompt_budget_section(
            "planning_boundary",
            "Planning Boundary",
            90,
            True,
            False,
            "planning_boundary",
            {"expected_json_keys": payload.get("expected_json_keys"), "target_output": draft.get("target_output")},
        ),
        _prompt_budget_section("validation", "Validation", 85, True, False, "validation", _validation_section(draft)),
        _prompt_budget_section("repository_evidence", "Repository Evidence", 80, False, True, "repository", repository_evidence),
        _prompt_budget_section("knowledge_summary", "Knowledge Summary", 60, False, True, "knowledge", knowledge_summary),
        _prompt_budget_section("instructions", "Instructions", 100, True, False, "instructions", payload.get("instruction")),
        _prompt_budget_section("previous_draft_summary", "Previous Draft Summary", 50, False, True, "draft", draft),
    ]
    return sections


def _prompt_budget_section(
    section_id: str,
    name: str,
    priority: int,
    required: bool,
    compressible: bool,
    source: str,
    content: Any,
) -> PromptSection:
    return PromptSection(
        id=section_id,
        name=name,
        priority=priority,
        estimatedTokens=promptBudgetEstimateTokens(json.dumps(content, ensure_ascii=True, separators=(",", ":"), default=str)),
        required=required,
        compressible=compressible,
        source=source,
        content=content,
    )


def _current_capability_section(project_context: dict[str, Any], input_item: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    summary = project_context.get("project_summary") if isinstance(project_context.get("project_summary"), dict) else {}
    return {
        "title": input_item.get("title") or draft.get("title"),
        "domain": project_context.get("domain"),
        "capability": draft.get("capability") or draft.get("business_goal") or summary.get("architecture_summary"),
        "modules": summary.get("top_modules"),
        "flows": summary.get("top_flows"),
    }


def _dna_section(input_item: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    for key in ["work_item_dna", "dna", "engineering_dna"]:
        value = input_item.get(key) or draft.get(key)
        if isinstance(value, dict):
            return value
    return {"status": "not_available"}


def _validation_section(draft: dict[str, Any]) -> dict[str, Any]:
    for key in ["validation_report", "validation", "quality_gate", "warnings"]:
        value = draft.get(key)
        if value not in (None, "", [], {}):
            return {key: value}
    return {"status": "pending"}


def _payload_from_prompt_budget_sections(payload: dict[str, Any], sections: list[PromptSection]) -> dict[str, Any]:
    optimized = json.loads(json.dumps(payload, ensure_ascii=True, default=str))
    section_map = {section.id: section.content for section in sections}
    project_context = optimized.get("project_context") if isinstance(optimized.get("project_context"), dict) else {}
    if "knowledge_summary" in section_map:
        knowledge_summary = section_map["knowledge_summary"] if isinstance(section_map["knowledge_summary"], dict) else {}
        for key in ["project_name", "domain", "project_type", "description", "project_summary", "technology_stack", "development_standards", "ui_guidelines"]:
            if key in knowledge_summary:
                project_context[key] = knowledge_summary[key]
    else:
        for key in ["description", "project_summary", "technology_stack", "development_standards", "ui_guidelines"]:
            project_context.pop(key, None)
    if "repository_evidence" in section_map:
        repository_evidence = section_map["repository_evidence"] if isinstance(section_map["repository_evidence"], dict) else {}
        if isinstance(repository_evidence.get("knowledge_registry"), dict):
            project_context["knowledge_registry"] = repository_evidence["knowledge_registry"]
        elif repository_evidence:
            project_context["knowledge_registry"] = repository_evidence
        elif "knowledge_registry" in project_context:
            project_context["knowledge_registry"] = {}
        if repository_evidence.get("capsule_focus"):
            project_context["capsule_focus"] = repository_evidence["capsule_focus"]
    else:
        project_context["knowledge_registry"] = {}
        project_context.pop("capsule_focus", None)
    optimized["project_context"] = project_context
    if "previous_draft_summary" in section_map:
        optimized["draft"] = section_map["previous_draft_summary"]
    else:
        optimized["draft"] = {}
    if "instructions" in section_map:
        optimized["instruction"] = section_map["instructions"]
    return optimized


def _build_project_phi_prompt(
    operation: str,
    profile: dict[str, Any],
    item: dict[str, Any],
    deterministic: dict[str, Any],
    expected_keys: list[str],
    compression_level: int,
    budget_tokens: int,
    draft_budget_tokens: int,
    retry_attempt: int,
) -> tuple[str, dict[str, Any]]:
    raw_context = _project_summary_context(operation, profile, item, compression_level=0)
    raw_context_tokens = _estimate_tokens(json.dumps(raw_context, ensure_ascii=True, separators=(",", ":")))
    project_context = _project_summary_context(operation, profile, item, compression_level=compression_level)
    project_context = _fit_project_context_to_budget(operation, profile, item, project_context, compression_level, budget_tokens)
    payload, draft_diagnostics = _project_phi_payload(
        operation,
        expected_keys,
        project_context,
        item,
        deterministic,
        compression_level=compression_level,
        draft_budget_tokens=draft_budget_tokens,
    )
    payload, prompt_budget_diagnostics = _apply_prompt_budget_manager(operation, payload)
    prompt = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    project_context = payload.get("project_context") if isinstance(payload.get("project_context"), dict) else project_context
    context_tokens = _estimate_tokens(json.dumps(project_context, ensure_ascii=True, separators=(",", ":")))
    diagnostics = {
        "operation": operation,
        "original_context_tokens": raw_context_tokens,
        "compressed_context_tokens": context_tokens,
        "project_context_tokens": context_tokens,
        "context_size": raw_context_tokens,
        "context_after_compression": context_tokens,
        "tokens_sent": _estimate_tokens(prompt),
        "configured_budget_tokens": _context_budget_tokens(),
        "context_budget_tokens": budget_tokens,
        "context_budget_used": context_tokens,
        "draft_budget_tokens": draft_budget_tokens,
        "compression_applied": compression_level > 1 or context_tokens < raw_context_tokens,
        "compression_ratio": round(context_tokens / max(raw_context_tokens, 1), 3),
        "context_compression_level": compression_level,
        "compression_level": compression_level,
        "retry_attempt": retry_attempt,
        "project_summary_mode": compression_level >= 4 or budget_tokens < 450,
        "reserved_tokens": PROJECT_CONTEXT_RESERVED_TOKENS,
    }
    active_capsule = profile.get("_active_context_capsule") if isinstance(profile.get("_active_context_capsule"), dict) else {}
    if active_capsule:
        capsule_diagnostics = active_capsule.get("diagnostics") if isinstance(active_capsule.get("diagnostics"), dict) else {}
        diagnostics.update(
            {
                "context_capsule_used": True,
                "context_capsule_type": active_capsule.get("capsule_type"),
                "context_capsule_version": active_capsule.get("version"),
                "context_capsule_size_tokens": capsule_diagnostics.get("capsule_size_tokens", 0),
                "context_capsule_source_size_tokens": capsule_diagnostics.get("source_size_tokens", 0),
                "context_capsule_compression_ratio": capsule_diagnostics.get("compression_ratio", 0),
            }
        )
    diagnostics.update(draft_diagnostics)
    diagnostics.update(_section_diagnostics(payload))
    prompt_budget_removed_sections = _string_list(prompt_budget_diagnostics.get("removed_sections"))
    prompt_budget_diagnostics["prompt_budget_removed_sections"] = prompt_budget_removed_sections
    prompt_budget_diagnostics["removed_sections"] = _unique(
        [*_string_list(draft_diagnostics.get("removed_sections")), *prompt_budget_removed_sections]
    )
    diagnostics.update(prompt_budget_diagnostics)
    diagnostics = _with_final_prompt_diagnostics(PROJECT_PHI_SYSTEM_PROMPT, prompt, diagnostics)
    return prompt, diagnostics


def _project_phi_payload(
    operation: str,
    expected_keys: list[str],
    project_context: dict[str, Any],
    item: dict[str, Any],
    deterministic: dict[str, Any],
    compression_level: int = 0,
    draft_budget_tokens: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if _is_execution_operation(operation):
        draft, draft_diagnostics = _compact_execution_draft(operation, item, deterministic, draft_budget_tokens or _draft_budget_tokens())
    else:
        raw_draft = _compact_deterministic_draft(deterministic, compression_level)
        draft = raw_draft
        draft_tokens = _estimate_tokens(json.dumps(raw_draft, ensure_ascii=True, separators=(",", ":")))
        draft_diagnostics = {
            "draft_tokens_before": draft_tokens,
            "draft_tokens_after": draft_tokens,
            "draft_compression_applied": False,
            "draft_compression_ratio": 1,
            "removed_sections": [],
        }
    input_payload = _compact_execution_input_item(item) if _is_execution_operation(operation) else _compact_input_item(item)
    payload = {
        "operation": operation,
        "expected_json_keys": expected_keys,
        "project_context": project_context,
        "input": input_payload,
        "draft": draft,
        "instruction": PROJECT_PHI_INSTRUCTION,
    }
    return payload, draft_diagnostics


def _compact_input_item(item: dict[str, Any]) -> dict[str, Any]:
    compacted: dict[str, Any] = {}
    for key in ["id", "type", "title", "description", "acceptance_criteria", "state", "tags"]:
        value = item.get(key)
        if isinstance(value, str):
            compacted[key] = _truncate_text(value, 700 if key == "description" else 300)
        elif isinstance(value, list):
            compacted[key] = [_truncate_text(entry, 220) for entry in value[:8]]
        elif value not in (None, "", [], {}):
            compacted[key] = value
    return compacted


def _compact_execution_input_item(item: dict[str, Any]) -> dict[str, Any]:
    compacted: dict[str, Any] = {}
    for key in ["id", "type", "title", "state"]:
        value = item.get(key)
        if value not in (None, "", [], {}):
            compacted[key] = _truncate_text(value, 220) if isinstance(value, str) else value
    tags = _string_list(item.get("tags"))[:3]
    if tags:
        compacted["tags"] = tags
    return compacted


def _is_execution_operation(operation: str) -> bool:
    return operation in PROJECT_EXECUTION_OPERATIONS


def _compact_execution_draft(
    operation: str,
    item: dict[str, Any],
    deterministic: dict[str, Any],
    draft_budget_tokens: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    removed_sections: list[str] = []
    raw_tokens = _estimate_tokens(json.dumps(deterministic, ensure_ascii=True, separators=(",", ":")))
    title = _clean_text(item.get("title")) or _clean_text(deterministic.get("story_summary")) or "Untitled work item"
    description = _clean_text(item.get("description")) or _clean_text(deterministic.get("story_summary"))
    acceptance = _string_list(item.get("acceptance_criteria")) or _string_list(deterministic.get("acceptance_criteria"))
    dependencies = _string_list(deterministic.get("dependencies"))
    modules = _string_list(deterministic.get("affected_modules"))
    flows = _string_list(deterministic.get("affected_flows"))
    if not description and deterministic.get("prompt"):
        removed_sections.append("previous_generated_prompt")
    if deterministic.get("ui_prompt") or deterministic.get("dev_prompt") or deterministic.get("qa_prompt") or deterministic.get("context"):
        removed_sections.append("previous_generated_prompts")
    target_output = {
        "build_execution_context": "execution_context",
        "build_dev_prompt": "dev_prompt",
        "build_ui_prompt": "ui_prompt",
        "build_qa_prompt": "qa_prompt",
        "build_copilot_context": "copilot_context",
    }.get(operation, operation)
    compact: dict[str, Any] = {
        "work_item_type": _clean_text(item.get("type")) or "User Story",
        "title": title,
        "user_story": _summarize_story_description(title, description),
        "acceptance_criteria": acceptance[:5],
        "affected_modules": modules[:5],
        "affected_flows": flows[:5],
        "dependencies": dependencies[:3],
        "target_output": target_output,
    }
    compact = {key: value for key, value in compact.items() if value not in ("", [], {}, None)}
    compact = _fit_execution_draft_to_budget(compact, draft_budget_tokens, removed_sections)
    final_tokens = _estimate_tokens(json.dumps(compact, ensure_ascii=True, separators=(",", ":")))
    return compact, {
        "draft_tokens_before": raw_tokens,
        "draft_tokens_after": final_tokens,
        "draft_compression_applied": final_tokens < raw_tokens,
        "draft_compression_ratio": round(final_tokens / max(raw_tokens, 1), 3),
        "removed_sections": _unique(removed_sections),
    }


def _summarize_story_description(title: str, description: str) -> str:
    text = _clean_text(description)
    if not text:
        return _truncate_text(title, 180)
    blocked_phrases = ["dev_prompt", "ui_prompt", "qa_prompt", "copilot_context", "execution_context"]
    if any(phrase in text.lower() for phrase in blocked_phrases):
        return _truncate_text(title, 180)
    sentences = [segment.strip() for segment in text.replace("\n", " ").split(".") if segment.strip()]
    if not sentences:
        return _truncate_text(text, 220)
    return _truncate_text(". ".join(sentences[:2]), 220)


def _fit_execution_draft_to_budget(draft: dict[str, Any], budget_tokens: int, removed_sections: list[str]) -> dict[str, Any]:
    budget = min(PROJECT_EXECUTION_DRAFT_MAX_TOKENS, max(1, int(budget_tokens or PROJECT_EXECUTION_DRAFT_DEFAULT_TOKENS)))
    compact = json.loads(json.dumps(draft))
    if _draft_token_count(compact) <= budget:
        return compact
    compact["user_story"] = _truncate_text(compact.get("user_story"), 160)
    compact["acceptance_criteria"] = _string_list(compact.get("acceptance_criteria"))[:4]
    compact["affected_modules"] = _string_list(compact.get("affected_modules"))[:3]
    compact["affected_flows"] = _string_list(compact.get("affected_flows"))[:3]
    compact["dependencies"] = _string_list(compact.get("dependencies"))[:2]
    removed_sections.append("low_priority_draft_details")
    if _draft_token_count(compact) <= budget:
        return compact
    compact["acceptance_criteria"] = [_truncate_text(item, 120) for item in _string_list(compact.get("acceptance_criteria"))[:3]]
    compact["user_story"] = _truncate_text(compact.get("user_story"), 120)
    removed_sections.append("long_acceptance_criteria")
    if _draft_token_count(compact) <= budget:
        return compact
    compact["dependencies"] = _string_list(compact.get("dependencies"))[:1]
    compact["affected_modules"] = _string_list(compact.get("affected_modules"))[:2]
    compact["affected_flows"] = _string_list(compact.get("affected_flows"))[:2]
    removed_sections.append("extra_modules_flows_dependencies")
    if _draft_token_count(compact) <= budget:
        return compact
    compact.pop("dependencies", None)
    compact["acceptance_criteria"] = [_truncate_text(item, 90) for item in _string_list(compact.get("acceptance_criteria"))[:2]]
    compact["user_story"] = _truncate_text(compact.get("user_story"), 90)
    removed_sections.append("dependency_context")
    return compact


def _draft_token_count(draft: dict[str, Any]) -> int:
    return _estimate_tokens(json.dumps(draft, ensure_ascii=True, separators=(",", ":")))


def _compact_deterministic_draft(deterministic: dict[str, Any], compression_level: int = 0) -> dict[str, Any]:
    compacted: dict[str, Any] = {}
    for key, value in deterministic.items():
        compacted[key] = _compact_draft_value(value, compression_level)
    return compacted


def _compact_draft_value(value: Any, compression_level: int = 0) -> Any:
    string_limits = [900, 900, 650, 420, 260, 120, 80]
    list_limits = [8, 8, 6, 5, 3, 1, 1]
    dict_limits = [12, 12, 10, 8, 6, 3, 2]
    level = min(max(compression_level, 0), 6)
    if isinstance(value, str):
        return _truncate_text(value, string_limits[level])
    if isinstance(value, list):
        return [_compact_draft_value(item, compression_level) for item in value[: list_limits[level]]]
    if isinstance(value, dict):
        return {key: _compact_draft_value(item, compression_level) for key, item in list(value.items())[: dict_limits[level]]}
    return value


def _budgeted_project_context(operation: str, profile: dict[str, Any], item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    budget_tokens = _context_budget_tokens()
    raw_context = _project_summary_context(operation, profile, item, compression_level=0)
    raw_tokens = _estimate_tokens(json.dumps(raw_context, ensure_ascii=True))
    compressed_context = raw_context
    compression_level = 0
    compressed_tokens = raw_tokens
    for level in [0, 1, 2, 3, 4]:
        candidate = _project_summary_context(operation, profile, item, compression_level=level)
        candidate_tokens = _estimate_tokens(json.dumps(candidate, ensure_ascii=True))
        compressed_context = candidate
        compressed_tokens = candidate_tokens
        compression_level = level
        if candidate_tokens <= budget_tokens:
            break
    diagnostics = {
        "context_size": raw_tokens,
        "context_after_compression": compressed_tokens,
        "tokens_sent": compressed_tokens,
        "context_budget_tokens": budget_tokens,
        "compression_ratio": round(compressed_tokens / max(raw_tokens, 1), 3),
        "context_compression_level": compression_level,
    }
    return compressed_context, diagnostics


def _adaptive_context_budgets() -> list[int]:
    configured = _context_budget_tokens()
    budgets = [configured, *PROJECT_CONTEXT_RETRY_BUDGETS[1:]]
    normalized: list[int] = []
    for budget in budgets:
        budget = min(PROJECT_CONTEXT_MAX_TOKENS, max(PROJECT_CONTEXT_MIN_TOKENS, int(budget)))
        if budget not in normalized:
            normalized.append(budget)
    return normalized


def _adaptive_budget_profiles(operation: str) -> list[dict[str, int]]:
    if _is_execution_operation(operation):
        return [dict(profile) for profile in PROJECT_EXECUTION_BUDGET_ATTEMPTS]
    profiles = [{"context_budget": budget, "draft_budget": _draft_budget_tokens()} for budget in _adaptive_context_budgets()]
    if profiles:
        profiles.append({"context_budget": profiles[-1]["context_budget"], "draft_budget": _draft_budget_tokens(), "compression_level": 6})
    return profiles


def _draft_budget_tokens() -> int:
    try:
        configured = int(os.getenv("AI_GEN_PROJECT_DRAFT_BUDGET_TOKENS", str(PROJECT_EXECUTION_DRAFT_DEFAULT_TOKENS)))
    except ValueError:
        configured = PROJECT_EXECUTION_DRAFT_DEFAULT_TOKENS
    return min(PROJECT_EXECUTION_DRAFT_MAX_TOKENS, max(1, configured))


def _compression_level_for_budget(budget_tokens: int) -> int:
    if budget_tokens <= 300:
        return 5
    if budget_tokens <= 450:
        return 4
    if budget_tokens <= 600:
        return 3
    if budget_tokens <= 750:
        return 2
    return 1


def _fit_project_context_to_budget(
    operation: str,
    profile: dict[str, Any],
    item: dict[str, Any],
    project_context: dict[str, Any],
    compression_level: int,
    budget_tokens: int,
) -> dict[str, Any]:
    context = json.loads(json.dumps(project_context))
    if _project_context_token_count(context) <= budget_tokens:
        return context
    registry = context.get("knowledge_registry") if isinstance(context.get("knowledge_registry"), dict) else {}
    for key in ["source_files", "standards", "component_details", "components", "flow_details", "module_details"]:
        registry.pop(key, None)
        if _project_context_token_count(context) <= budget_tokens:
            return context
    registry["architecture_summary"] = _truncate_text(registry.get("architecture_summary"), 60 if compression_level >= 5 else 120)
    summary = context.get("project_summary") if isinstance(context.get("project_summary"), dict) else {}
    summary["architecture_summary"] = _truncate_text(summary.get("architecture_summary"), 60 if compression_level >= 5 else 120)
    if compression_level >= 4:
        context.pop("development_standards", None)
        context.pop("ui_guidelines", None)
        context["technology_stack"] = _compact_stack_for_summary(context.get("technology_stack", {}))
    if _project_context_token_count(context) <= budget_tokens:
        return context
    registry["modules"] = _string_list(registry.get("modules"))[:5]
    registry["flows"] = _string_list(registry.get("flows"))[:5]
    summary["top_modules"] = _string_list(summary.get("top_modules"))[:5]
    summary["top_flows"] = _string_list(summary.get("top_flows"))[:5]
    if _project_context_token_count(context) <= budget_tokens:
        return context
    context["description"] = _truncate_text(context.get("description"), 60)
    summary["applications"] = (summary.get("applications") or [])[:2] if isinstance(summary.get("applications"), list) else summary.get("applications")
    return context


def _project_context_token_count(project_context: dict[str, Any]) -> int:
    return _estimate_tokens(json.dumps(project_context, ensure_ascii=True, separators=(",", ":")))


def _compact_stack_for_summary(stack: Any) -> dict[str, list[str]]:
    if not isinstance(stack, dict):
        return {}
    return {key: _string_list(value)[:2] for key, value in stack.items() if _string_list(value)[:2]}


def _project_summary_context(operation: str, profile: dict[str, Any], item: dict[str, Any], compression_level: int) -> dict[str, Any]:
    capsule = profile.get("_active_context_capsule") if isinstance(profile.get("_active_context_capsule"), dict) else {}
    capsule_payload = capsule.get("payload") if isinstance(capsule.get("payload"), dict) else {}
    if capsule_payload:
        return _project_summary_context_from_capsule(capsule, operation, compression_level)
    registry = _normalize_knowledge_registry(profile.get("knowledge_registry", {}))
    selected = _select_semantic_registry_context(operation, item, profile, registry, compression_level)
    level = min(max(compression_level, 0), 5)
    description_limits = [900, 900, 650, 420, 220, 80]
    architecture_limits = [650, 650, 450, 260, 120, 45]
    standards_limits = [8, 8, 6, 3, 1, 0]
    source_limits = [8, 8, 5, 2, 0, 0]
    applications = profile.get("applications") or registry.get("applications")
    context = {
        "project_name": profile.get("project_name"),
        "domain": profile.get("domain"),
        "project_type": profile.get("project_type"),
        "description": _truncate_text(profile.get("project_description"), description_limits[level]),
        "project_summary": {
            "applications": applications[:3] if isinstance(applications, list) else applications,
            "top_modules": selected["modules"],
            "top_flows": selected["flows"],
            "architecture_summary": _truncate_text(_architecture_summary_text(profile, registry), architecture_limits[level]),
        },
        "technology_stack": _compact_stack(profile),
        "knowledge_registry": {
            "modules": selected["modules"],
            "module_details": selected["module_details"],
            "flows": selected["flows"],
            "flow_details": selected["flow_details"],
            "components": selected["components"],
            "component_details": selected["component_details"],
            "architecture_summary": _truncate_text(_architecture_summary_text(profile, registry), architecture_limits[level]),
            "standards": registry["standards"][: standards_limits[level]],
            "source_files": registry["source_files"][: source_limits[level]],
        },
    }
    if level < 4:
        context["development_standards"] = _compact_development_standards(profile.get("development_standards", {}), registry)
        context["ui_guidelines"] = _compact_ui_guidelines(profile.get("ui_guidelines", {}), registry)
    return context


def _project_summary_context_from_capsule(capsule: dict[str, Any], operation: str, compression_level: int) -> dict[str, Any]:
    payload = capsule.get("payload") if isinstance(capsule.get("payload"), dict) else {}
    level = min(max(compression_level, 0), 5)
    execution_mode = _is_execution_operation(operation)
    limits = {
        "modules": [6, 5, 4, 3, 3, 2] if execution_mode else [10, 8, 7, 6, 5, 3],
        "flows": [6, 5, 4, 3, 3, 2] if execution_mode else [10, 8, 7, 6, 5, 3],
        "standards": [5, 4, 3, 2, 1, 1] if execution_mode else [10, 8, 6, 4, 2, 1],
        "applications": [3, 3, 2, 2, 1, 1] if execution_mode else [6, 5, 4, 3, 2, 1],
        "architecture": [180, 150, 120, 90, 60, 40] if execution_mode else [700, 520, 360, 220, 120, 60],
    }
    context = {
        "context_source": "context_capsule",
        "capsule_type": capsule.get("capsule_type") or "project",
        "capsule_id": capsule.get("capsule_id"),
        "capsule_version": capsule.get("version"),
        "source_version": capsule.get("source_version"),
        "project_name": payload.get("project_name"),
        "domain": payload.get("domain"),
        "project_type": payload.get("project_type"),
        "description": _truncate_text(payload.get("project_summary"), 220 if level < 4 else 100),
        "project_summary": {
            "applications": _string_list(payload.get("applications"))[: limits["applications"][level]],
            "top_modules": _string_list(payload.get("modules"))[: limits["modules"][level]],
            "top_flows": _string_list(payload.get("flows"))[: limits["flows"][level]],
            "architecture_summary": _truncate_text(payload.get("architecture_summary"), limits["architecture"][level]),
        },
        "technology_stack": _compact_stack_for_summary(payload.get("technology_stack")) if execution_mode else (payload.get("technology_stack") if isinstance(payload.get("technology_stack"), dict) else {}),
        "knowledge_registry": {
            "modules": _string_list(payload.get("modules"))[: limits["modules"][level]],
            "flows": _string_list(payload.get("flows"))[: limits["flows"][level]],
            "architecture_summary": _truncate_text(payload.get("architecture_summary"), limits["architecture"][level]),
            "standards": _string_list(payload.get("standards"))[: limits["standards"][level]],
        },
        "capsule_focus": {
            key: value
            for key, value in payload.items()
            if key in {
                "feature_summary",
                "business_goal",
                "story_summary",
                "acceptance_criteria",
                "dev_context",
                "ui_context",
                "qa_context",
                "coverage_context",
                "regression_context",
                "risk_areas",
                "validation_areas",
                "impacted_files",
            }
            and value not in ("", [], {}, None)
        },
    }
    if level < 4 and not execution_mode:
        context["roles"] = _string_list(payload.get("roles"))[:4]
    return context


def _select_semantic_registry_context(
    operation: str,
    item: dict[str, Any],
    profile: dict[str, Any],
    registry: dict[str, Any],
    compression_level: int,
) -> dict[str, Any]:
    terms = _semantic_context_terms(operation, item, profile)
    limits = _semantic_limits(operation, compression_level)
    modules = _rank_by_semantic_match(registry["modules"], terms)[: limits["modules"]]
    flows = _rank_by_semantic_match(registry["flows"], terms)[: limits["flows"]]
    components = _rank_by_semantic_match(registry["components"], terms)[: limits["components"]]
    module_details = _matching_details(registry["module_details"], modules, terms, limits["module_details"], detail_keys=["responsibilities", "dependencies"])
    flow_details = _matching_details(registry["flow_details"], flows, terms, limits["flow_details"], detail_keys=["steps"])
    component_details = _matching_details(registry["component_details"], components, terms, limits["component_details"], detail_keys=[])
    return {
        "modules": modules,
        "module_details": module_details,
        "flows": flows,
        "flow_details": flow_details,
        "components": components,
        "component_details": component_details,
    }


def _semantic_limits(operation: str, compression_level: int) -> dict[str, int]:
    operation_key = _clean_text(operation).lower()
    if "epic" in operation_key:
        base = {"modules": 10, "module_details": 8, "flows": 10, "flow_details": 8, "components": 10, "component_details": 8}
    elif "feature" in operation_key:
        base = {"modules": 8, "module_details": 6, "flows": 8, "flow_details": 6, "components": 8, "component_details": 6}
    else:
        base = {"modules": 6, "module_details": 5, "flows": 6, "flow_details": 5, "components": 6, "component_details": 5}
    reductions = [1.0, 0.9, 0.65, 0.42, 0.28, 0.16]
    factor = reductions[min(max(compression_level, 0), 5)]
    limits = {key: max(1, int(value * factor)) for key, value in base.items()}
    if compression_level >= 4:
        limits.update({"module_details": 0, "flow_details": 0, "components": 0, "component_details": 0})
    if compression_level >= 5:
        limits["modules"] = min(limits["modules"], 5)
        limits["flows"] = min(limits["flows"], 5)
    return limits


def _semantic_context_terms(operation: str, item: dict[str, Any], profile: dict[str, Any]) -> set[str]:
    parts = [
        operation,
        item.get("title"),
        item.get("description"),
        item.get("acceptance_criteria"),
        profile.get("project_name"),
        profile.get("domain"),
        profile.get("project_type"),
        profile.get("project_description"),
    ]
    text = " ".join(_clean_text(part) for part in parts)
    words = []
    for raw in text.replace("_", " ").replace("-", " ").replace("/", " ").split():
        word = "".join(ch for ch in raw.lower() if ch.isalnum())
        if len(word) >= 3 and word not in {"the", "and", "for", "with", "from", "this", "that", "into", "user", "story", "feature", "epic", "task"}:
            words.append(word)
    return set(words)


def _rank_by_semantic_match(values: list[str], terms: set[str]) -> list[str]:
    ranked = []
    for index, value in enumerate(values):
        value_text = _clean_text(value)
        value_words = set("".join(ch for ch in raw.lower() if ch.isalnum()) for raw in value_text.replace("-", " ").split())
        score = len([term for term in terms if term in value_words or term in value_text.lower()])
        ranked.append((score, -index, value))
    ranked.sort(reverse=True)
    return [value for _score, _index, value in ranked]


def _matching_details(
    details: list[dict[str, Any]],
    selected_names: list[str],
    terms: set[str],
    limit: int,
    detail_keys: list[str],
) -> list[dict[str, Any]]:
    selected_lookup = {name.lower() for name in selected_names}
    ranked = []
    for index, detail in enumerate(details):
        name = _clean_text(detail.get("name"))
        combined = " ".join([name, *[" ".join(_string_list(detail.get(key))) for key in detail_keys]]).lower()
        score = len([term for term in terms if term in combined])
        if name.lower() in selected_lookup:
            score += 5
        ranked.append((score, -index, detail))
    ranked.sort(reverse=True)
    compacted = []
    for _score, _index, detail in ranked[:limit]:
        item = {"name": detail.get("name")}
        for key in detail_keys:
            item[key] = _string_list(detail.get(key))[:3]
        if "type" in detail:
            item["type"] = detail.get("type")
        compacted.append(item)
    return compacted


def _architecture_summary_text(profile: dict[str, Any], registry: dict[str, Any]) -> str:
    notes = [
        *_string_list(registry.get("architecture_notes")),
        *_string_list(profile.get("readme_analysis", {}).get("architecture_notes") if isinstance(profile.get("readme_analysis"), dict) else []),
    ]
    return " ".join(_truncate_text(note, 240) for note in _unique(notes)[:4])


def _context_budget_tokens() -> int:
    try:
        configured = int(os.getenv("AI_GEN_PROJECT_CONTEXT_BUDGET_TOKENS", str(PROJECT_CONTEXT_DEFAULT_TOKENS)))
    except ValueError:
        configured = PROJECT_CONTEXT_DEFAULT_TOKENS
    return min(PROJECT_CONTEXT_MAX_TOKENS, max(PROJECT_CONTEXT_MIN_TOKENS, configured))


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _with_final_prompt_diagnostics(system_prompt: str, user_prompt: str, diagnostics: dict[str, Any] | None) -> dict[str, Any]:
    updated = dict(diagnostics or {})
    system_tokens = _estimate_tokens(system_prompt)
    user_tokens = _estimate_tokens(user_prompt)
    output_schema_tokens = _estimate_tokens(_clean_text(updated.get("output_schema_preview")))
    reserved_tokens = int(updated.get("reserved_tokens") or PROJECT_CONTEXT_RESERVED_TOKENS)
    final_tokens = system_tokens + user_tokens + reserved_tokens
    model_context_limit = int(updated.get("model_context_limit") or _model_context_limit_tokens())
    updated.update(
        {
            "reserved_tokens": reserved_tokens,
            "system_prompt_tokens": system_tokens,
            "user_prompt_tokens": user_tokens,
            "output_schema_tokens": output_schema_tokens,
            "final_prompt_tokens": final_tokens,
            "model_context_limit": model_context_limit,
            "final_prompt_preview": user_prompt[:900],
        }
    )
    return updated


def _section_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    project_context = payload.get("project_context", {}) if isinstance(payload.get("project_context"), dict) else {}
    registry = project_context.get("knowledge_registry", {}) if isinstance(project_context.get("knowledge_registry"), dict) else {}
    summary = project_context.get("project_summary", {}) if isinstance(project_context.get("project_summary"), dict) else {}
    sections = {
        "project_context": project_context,
        "modules": {"modules": registry.get("modules"), "module_details": registry.get("module_details")},
        "flows": {"flows": registry.get("flows"), "flow_details": registry.get("flow_details")},
        "architecture": {"architecture": registry.get("architecture_summary") or summary.get("architecture_summary")},
        "applications": summary.get("applications"),
        "standards": {"standards": registry.get("standards"), "development_standards": project_context.get("development_standards")},
        "components": {"components": registry.get("components"), "component_details": registry.get("component_details")},
        "input": payload.get("input", {}),
        "draft": payload.get("draft", {}),
        "expected_json_keys": payload.get("expected_json_keys", []),
        "instruction": payload.get("instruction", ""),
    }
    section_tokens = {
        key: _estimate_tokens(json.dumps(value, ensure_ascii=True, separators=(",", ":")))
        for key, value in sections.items()
    }
    largest = sorted(section_tokens.items(), key=lambda item: item[1], reverse=True)[:5]
    return {
        "largest_context_sections": [{"section": key, "tokens": tokens} for key, tokens in largest],
        "context_section_tokens": section_tokens,
        "output_schema_preview": json.dumps(payload.get("expected_json_keys", []), ensure_ascii=True),
    }


def _model_context_limit_tokens() -> int:
    provider_char_limit = _provider_prompt_char_limit()
    env_limit = os.getenv("AI_GEN_PROJECT_MODEL_CONTEXT_TOKENS")
    try:
        configured = int(env_limit) if env_limit else 0
    except ValueError:
        configured = 0
    provider_token_limit = max(1, provider_char_limit // 4)
    return min(configured, provider_token_limit) if configured else provider_token_limit


def _provider_prompt_char_limit() -> int:
    try:
        return max(1, int(os.getenv("AI_GEN_REFINER_MAX_PROMPT_CHARS", str(PROJECT_PROVIDER_PROMPT_CHAR_LIMIT))))
    except ValueError:
        return PROJECT_PROVIDER_PROMPT_CHAR_LIMIT


def _budget_guard_reason(diagnostics: dict[str, Any]) -> str:
    largest = diagnostics.get("largest_context_sections") or []
    section = largest[0] if largest and isinstance(largest[0], dict) else {}
    section_label = section.get("section") or "unknown"
    return (
        "Project Intelligence Phi prompt blocked before provider call: "
        f"final_prompt_tokens={diagnostics.get('final_prompt_tokens')} exceeds "
        f"model_context_limit={diagnostics.get('model_context_limit')}. "
        f"Largest section: {section_label}."
    )


def _prompt_too_long_stage(probe: dict[str, Any]) -> str:
    status = probe.get("failure_reason") or probe.get("status")
    if status == "prompt_too_long":
        return "provider_request_validation"
    return ""


def _compact_stack(profile: dict[str, Any]) -> dict[str, list[str]]:
    registry = profile.get("knowledge_registry", {}) if isinstance(profile.get("knowledge_registry"), dict) else {}
    return _merge_stack(profile.get("technology_stack", {}), registry.get("technology_stack", {}))


def _compact_development_standards(standards: dict[str, Any], registry: dict[str, Any]) -> dict[str, list[str]]:
    normalized = {
        "architecture_patterns": _string_list(standards.get("architecture_patterns"))[:5],
        "coding_guidelines": _string_list(standards.get("coding_guidelines"))[:5],
        "security_requirements": _string_list(standards.get("security_requirements"))[:5],
        "testing_requirements": _string_list(standards.get("testing_requirements"))[:5],
    }
    registry_standards = _string_list(registry.get("standards"))
    if registry_standards:
        normalized["coding_guidelines"] = _unique([*normalized["coding_guidelines"], *registry_standards[:6]])[:8]
    return normalized


def _compact_ui_guidelines(ui: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    standards = _string_list(registry.get("standards"))
    accessibility = _unique([*_string_list(ui.get("accessibility_rules")), *[item for item in standards if any(token in item.lower() for token in ["access", "contrast", "touch", "offline"])]])
    return {
        "primary_color": _clean_text(ui.get("primary_color")),
        "secondary_color": _clean_text(ui.get("secondary_color")),
        "typography": _clean_text(ui.get("typography")),
        "component_library": _clean_text(ui.get("component_library")),
        "accessibility_rules": accessibility[:6],
    }


def _compact_knowledge_registry(registry: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_knowledge_registry(registry)
    module_details = []
    for module in normalized["module_details"][:8]:
        module_details.append(
            {
                "name": module["name"],
                "responsibilities": _string_list(module.get("responsibilities"))[:4],
                "dependencies": _string_list(module.get("dependencies"))[:4],
            }
        )
    flow_details = []
    for flow in normalized["flow_details"][:8]:
        flow_details.append({"name": flow["name"], "steps": _string_list(flow.get("steps"))[:5]})
    component_details = []
    for component in normalized["component_details"][:10]:
        component_details.append({"name": component["name"], "type": component.get("type")})
    return {
        "modules": normalized["modules"][:10],
        "module_details": module_details,
        "flows": normalized["flows"][:10],
        "flow_details": flow_details,
        "components": normalized["components"][:12],
        "component_details": component_details,
        "architecture_summary": " ".join(_truncate_text(note, 220) for note in normalized["architecture_notes"][:3]),
        "standards": normalized["standards"][:10],
        "source_files": normalized["source_files"][:8],
    }


def _truncate_text(value: Any, max_chars: int) -> str:
    text = _clean_text(value)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _provider_status_metadata(provider: Any, probe: dict[str, Any], health: dict[str, Any] | None = None) -> dict[str, Any]:
    health = health or (provider.health_snapshot() if hasattr(provider, "health_snapshot") else {})
    config = provider.safe_config() if hasattr(provider, "safe_config") else {}
    parsed = probe.get("parsed_json") if isinstance(probe.get("parsed_json"), dict) else {}
    raw_preview = str(probe.get("raw_content") or probe.get("raw_response_preview") or "")[:1500]
    return {
        "provider_used": "azure_phi",
        "source": "azure_phi",
        "phi_status": probe.get("failure_reason") or probe.get("status") or "unknown",
        "fallback_used": False,
        "fallback_reason": "",
        "phi_latency_ms": int(probe.get("elapsed_ms") or 0),
        "phi_raw_response_preview": raw_preview,
        "phi_parsed_response_preview": json.dumps(parsed, ensure_ascii=True)[:1500] if parsed else "",
        "phi_prompt_tokens": int(probe.get("prompt_tokens") or 0),
        "phi_completion_tokens": int(probe.get("completion_tokens") or 0),
        "phi_finish_reason": probe.get("finish_reason") or "",
        "phi_response_length": int(probe.get("response_length") or len(raw_preview)),
        "provider_configured": bool(config.get("configured", provider.is_enabled() if hasattr(provider, "is_enabled") else False)),
        "provider_deployment": health.get("deployment") or config.get("deployment"),
        "provider_health": health.get("health") or config.get("deployment_health") or "unknown",
        "provider_last_success": health.get("last_success"),
        "provider_last_failure": health.get("last_failure"),
    }


def _should_persist_feature_generation_failure(context_diagnostics: dict[str, Any], probe: dict[str, Any]) -> bool:
    operation = _clean_text(context_diagnostics.get("operation")).lower()
    is_feature_path = operation in {"refine_feature", "generate_features", "generate_stories", "feature_generation"} or "feature" in operation
    failure = _clean_text(probe.get("failure_reason") or probe.get("status") or probe.get("parse_error")).lower()
    finish_reason = _clean_text(probe.get("finish_reason")).lower()
    return is_feature_path and (
        failure in {"parse_error", "unusable_response", "jsondecodeerror", "nojsonobjectfound", "nondictparsedjson", "truncated_response"}
        or finish_reason == "length"
    )


def _persist_feature_generation_failure(
    *,
    prompt: str,
    probe: dict[str, Any],
    context_diagnostics: dict[str, Any],
    provider: Any,
    expected_keys: list[str],
) -> dict[str, Any]:
    data_dir = Path(os.getenv("AI_GEN_DATA_DIR", str(Path(__file__).parent.parent / "data")))
    root = data_dir / "diagnostics" / "failed-feature-generation"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    operation = _clean_text(context_diagnostics.get("operation")) or "feature_generation"
    incident_dir = root / f"{timestamp}-{_safe_profile_id(operation)}"
    response_text = str(probe.get("raw_provider_response") or probe.get("raw_content") or probe.get("raw_response_preview") or "")
    metadata = {
        "provider": "azure_phi",
        "model": "",
        "operation": operation,
        "expected_keys": expected_keys,
        "prompt_tokens": int(probe.get("prompt_tokens") or context_diagnostics.get("final_prompt_tokens") or 0),
        "completion_tokens": int(probe.get("completion_tokens") or 0),
        "finish_reason": probe.get("finish_reason") or "",
        "latency": int(probe.get("elapsed_ms") or 0),
        "temperature": 0,
        "prompt_budget": probe.get("prompt_budget") or context_diagnostics,
        "response_length": int(probe.get("response_length") or len(response_text)),
        "http_status": probe.get("http_status"),
        "failure_reason": probe.get("failure_reason") or probe.get("status") or "parse_error",
        "failure_message": probe.get("failure_message") or probe.get("parse_error") or "Model response could not be normalized into a JSON object.",
        "parse_error": probe.get("parse_error") or "",
        "raw_response_preview": response_text[:4000],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        config = provider.safe_config() if hasattr(provider, "safe_config") else {}
        health = provider.health_snapshot() if hasattr(provider, "health_snapshot") else {}
        metadata["provider"] = str(config.get("provider") or "azure_phi")
        metadata["model"] = str(config.get("deployment") or health.get("deployment") or config.get("model") or "")
    except Exception:
        pass
    try:
        incident_dir.mkdir(parents=True, exist_ok=True)
        (incident_dir / "prompt.txt").write_text(prompt or "", encoding="utf-8")
        (incident_dir / "response.txt").write_text(response_text, encoding="utf-8")
        (incident_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.warning(
            "project-intelligence feature_generation_parse_failure provider=%s model=%s prompt_tokens=%s completion_tokens=%s finish_reason=%s response_length=%s diagnostics=%s",
            metadata.get("provider"),
            metadata.get("model"),
            metadata.get("prompt_tokens"),
            metadata.get("completion_tokens"),
            metadata.get("finish_reason"),
            metadata.get("response_length"),
            incident_dir,
        )
    except OSError as error:
        logger.warning("project-intelligence failed_to_persist_feature_generation_diagnostics error=%s", error)
        return {
            "diagnostics_error": str(error),
            "diagnostics_available": False,
            "raw_response_available": bool(response_text),
            "raw_response_preview": response_text[:1500],
        }
    return {
        "diagnostics_available": True,
        "diagnostics_path": str(incident_dir),
        "diagnostics_files": ["prompt.txt", "response.txt", "metadata.json"],
        "raw_response_available": bool(response_text),
        "raw_response_preview": response_text[:1500],
    }


def _fallback_metadata(provider_used: str, reason: str) -> dict[str, Any]:
    status = get_refiner_status()
    return {
        "provider_used": provider_used,
        "source": provider_used,
        "phi_status": "skipped",
        "fallback_used": provider_used != "azure_phi",
        "fallback_reason": reason,
        "phi_latency_ms": 0,
        "phi_raw_response_preview": "",
        "phi_parsed_response_preview": "",
        "provider_configured": bool(status.get("configured")),
        "provider_deployment": status.get("model"),
        "provider_health": "unknown",
        "provider_last_success": None,
        "provider_last_failure": None,
    }


def _knowledge_registry_metadata(reason: str) -> dict[str, Any]:
    metadata = _fallback_metadata("knowledge_registry", reason)
    metadata.update(
        {
            "provider_used": "knowledge_registry",
            "source": "knowledge_registry",
            "phi_status": "not_required",
            "fallback_used": False,
            "fallback_reason": "",
        }
    )
    return metadata


def _intelligence_pipeline_metadata(pipeline: dict[str, Any]) -> dict[str, Any]:
    policy = pipeline.get("previewPolicy") if isinstance(pipeline.get("previewPolicy"), dict) else {}
    diagnostics = pipeline.get("reasoning", {}).get("diagnostics", {}) if isinstance(pipeline.get("reasoning"), dict) else {}
    provider_metadata = pipeline.get("providerMetadata") if isinstance(pipeline.get("providerMetadata"), dict) else {}
    metadata = dict(provider_metadata) if provider_metadata else _fallback_metadata("intelligence_pipeline", "Generation is routed through the HEI intelligence pipeline.")
    if not provider_metadata:
        metadata.update(
            {
                "provider_used": "intelligence_pipeline",
                "source": "intelligence_pipeline",
                "phi_status": "not_required",
                "fallback_used": False,
                "fallback_reason": "",
            }
        )
    metadata.update(
        {
            "validation_status": _clean_text(policy.get("status")) or "NeedsReview",
            "creation_allowed": bool(policy.get("allow_create")),
            "save_allowed": bool(policy.get("allow_save")),
            "manual_edit_allowed": bool(policy.get("allow_manual_edit")),
            "creation_blocked": bool(policy.get("block_creation")),
            "reasoning_provider_used": diagnostics.get("providerUsed"),
            "reasoning_prompt_tokens": diagnostics.get("promptTokensEstimate"),
        }
    )
    if "context_size" not in metadata:
        metadata["context_size"] = metadata.get("user_prompt_tokens") or metadata.get("final_prompt_tokens") or diagnostics.get("promptTokensEstimate") or 0
    if "context_after_compression" not in metadata:
        metadata["context_after_compression"] = metadata.get("compressed_context_tokens") or metadata.get("context_size") or 0
    if "tokens_sent" not in metadata:
        metadata["tokens_sent"] = metadata.get("final_prompt_tokens") or diagnostics.get("promptTokensEstimate") or 0
    if "compression_ratio" not in metadata:
        before = int(metadata.get("context_size") or 0)
        after = int(metadata.get("context_after_compression") or 0)
        metadata["compression_ratio"] = round(after / before, 2) if before else 1
    if "largest_context_sections" not in metadata:
        metadata["largest_context_sections"] = [
            {"section": "planning_context", "tokens": metadata.get("user_prompt_tokens") or diagnostics.get("promptTokensEstimate") or 0}
        ]
    phi_status = _clean_text(metadata.get("phi_status"))
    if provider_metadata and phi_status != "success" and not bool(metadata.get("fallback_used")):
        metadata["error"] = metadata.get("fallback_reason") or "Azure Phi did not return usable output."
        metadata["message"] = "Phi output is required for this provider path. Review diagnostics or retry."
    return metadata


def _execution_ai_enrichment_enabled(options: dict[str, Any] | None) -> bool:
    options = options or {}
    mode = _clean_text(options.get("mode")).lower()
    return mode in {"enhance_with_ai", "ai_enrichment"} or bool(options.get("enhance_with_ai")) or _clean_text(options.get("force_provider")) == "azure_phi"


def _execution_ai_options(options: dict[str, Any] | None) -> dict[str, Any]:
    next_options = dict(options or {})
    next_options["allow_fallback"] = True
    next_options["timeout_seconds"] = int(next_options.get("timeout_seconds") or 20)
    next_options["max_tokens"] = int(next_options.get("max_tokens") or 450)
    if not _clean_text(next_options.get("force_provider")):
        next_options["force_provider"] = "azure_phi"
    return next_options


def _execution_primary_metadata(started_at: float, operation: str) -> dict[str, Any]:
    elapsed_ms = max(0, int((time.monotonic() - started_at) * 1000))
    metadata = _fallback_metadata("deterministic_execution", "Execution generation is deterministic-first. Phi enrichment is optional.")
    metadata.update(
        {
            "provider_used": "deterministic_execution",
            "source": "deterministic_execution",
            "phi_status": "skipped",
            "fallback_used": False,
            "fallback_reason": "",
            "deterministic_generation_ms": elapsed_ms,
            "phi_enrichment_ms": 0,
            "timeout_used": False,
            "operation": operation,
        }
    )
    return metadata


def _execution_timeout_metadata(base_metadata: dict[str, Any], phi_metadata: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(base_metadata)
    metadata.update({key: value for key, value in phi_metadata.items() if value not in (None, "", [], {})})
    phi_status = _clean_text(phi_metadata.get("phi_status")) or _clean_text(phi_metadata.get("failure_reason")) or "unusable_response"
    phi_latency = int(phi_metadata.get("phi_latency_ms") or phi_metadata.get("elapsed_ms") or 0)
    timed_out = phi_status in {"provider_timeout", "timeout"} or phi_latency >= 20000
    metadata.update(
        {
            "provider_used": "deterministic_execution",
            "source": "deterministic_execution",
            "phi_status": "partial_ai_enrichment_timeout" if timed_out else phi_status,
            "fallback_used": True,
            "fallback_reason": "Optional Phi enrichment timed out; deterministic execution package returned." if timed_out else (phi_metadata.get("fallback_reason") or "Optional Phi enrichment did not return usable output."),
            "phi_enrichment_ms": phi_latency,
            "timeout_used": timed_out,
        }
    )
    return metadata


def _execution_enrichment_keys(operation: str, deterministic: dict[str, Any]) -> list[str]:
    if operation == "build_execution_context":
        return ["implementation_notes", "risks", "recommended_files", "testing_tasks"]
    if operation == "build_copilot_context":
        return ["context"]
    if "prompt" in deterministic:
        return ["prompt"]
    return list(deterministic.keys())


def _with_context_diagnostics(metadata: dict[str, Any], diagnostics: dict[str, Any] | None) -> dict[str, Any]:
    if diagnostics:
        metadata.update(diagnostics)
    return metadata


def _with_provider_metadata(payload: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    return {**payload, **metadata}


def _with_implementation_package_aliases(payload: dict[str, Any]) -> dict[str, Any]:
    implementation_package = payload.get("execution_package_v2") if isinstance(payload.get("execution_package_v2"), dict) else {}
    if not implementation_package and isinstance(payload.get("implementation_package_v2"), dict):
        implementation_package = payload.get("implementation_package_v2") or {}
    if not implementation_package:
        return payload
    merged = dict(payload)
    merged["implementation_package_v2"] = implementation_package
    merged["implementationPackageV2"] = implementation_package
    merged["implementation_package"] = implementation_package
    merged["implementationPackage"] = implementation_package
    if payload.get("execution_package_source") and not merged.get("implementation_package_source"):
        merged["implementation_package_source"] = payload.get("execution_package_source")
    return merged


def _with_implementation_plan_aliases(payload: dict[str, Any]) -> dict[str, Any]:
    plan = payload.get("execution_plan") if isinstance(payload.get("execution_plan"), dict) else {}
    if not plan:
        plan = {
            "planId": payload.get("planId"),
            "packageId": payload.get("packageId"),
            "executionMode": payload.get("executionMode"),
            "executionModeLabel": payload.get("executionModeLabel"),
            "finalPlan": payload.get("finalPlan") or payload.get("plan") or payload.get("prompt") or "",
            "estimatedTokens": payload.get("estimatedTokens"),
            "warnings": payload.get("warnings"),
            "diagnostics": payload.get("diagnostics"),
            "generatedAt": payload.get("generatedAt"),
        }
    merged = dict(payload)
    merged["implementation_plan"] = plan
    merged["implementationPlan"] = plan
    return merged


def _with_ai_prompt_aliases(payload: dict[str, Any], prompt_type: str = "implementation") -> dict[str, Any]:
    prompt_text = _clean_text(payload.get("prompt"))
    if not prompt_text:
        return payload
    merged = dict(payload)
    merged["ai_prompt"] = prompt_text
    merged["aiPrompt"] = {
        "type": prompt_type,
        "prompt": prompt_text,
        "provider": payload.get("provider_used"),
        "generatedAt": payload.get("generatedAt"),
    }
    return merged


def _phi_error_response(phi: dict[str, Any]) -> dict[str, Any]:
    metadata = phi.get("metadata", {})
    return _with_provider_metadata(
        {
            "error": metadata.get("fallback_reason") or "Azure Phi did not return usable output.",
            "message": "Phi output is required. Fallback generation is disabled for Project Intelligence.",
        },
        metadata,
    )


def _merge_known_fields(base: dict[str, Any], incoming: dict[str, Any], keys: Any) -> dict[str, Any]:
    merged = dict(base)
    for key in keys:
        value = incoming.get(key)
        if value not in (None, "", [], {}):
            merged[key] = value
    return merged


def _pick_string_fields(incoming: dict[str, Any], keys: list[str]) -> dict[str, str]:
    return {key: _clean_text(incoming.get(key)) for key in keys if _clean_text(incoming.get(key))}


def _normalize_story_impact(value: dict[str, Any]) -> dict[str, list[str]]:
    impact = value if isinstance(value, dict) else {}
    return {
        "affected_applications": _string_list(impact.get("affected_applications")),
        "affected_modules": _string_list(impact.get("affected_modules")),
        "affected_flows": _string_list(impact.get("affected_flows")),
        "affected_components": _string_list(impact.get("affected_components")),
        "dependencies": _string_list(impact.get("dependencies")),
        "risks": _string_list(impact.get("risks")),
        "integration_points": _string_list(impact.get("integration_points")),
        "recommended_reviewers": _string_list(impact.get("recommended_reviewers")),
    }


def _recommended_files(profile: dict[str, Any], impact: dict[str, list[str]], story_title: str = "") -> list[str]:
    registry = profile.get("knowledge_registry") if isinstance(profile.get("knowledge_registry"), dict) else {}
    ranked = registry.get("ranked_files") or registry.get("repository_file_ranking") or profile.get("repository_file_ranking") or []
    files: list[str] = []
    for item in ranked if isinstance(ranked, list) else []:
        if isinstance(item, str):
            path = _clean_text(item)
        elif isinstance(item, dict):
            path = _clean_text(item.get("path") or item.get("file") or item.get("name"))
        else:
            path = ""
        if path:
            files.append(path)
    return _unique(files)[:8]


def _file_guess(area: str, values: list[str]) -> list[str]:
    guesses: list[str] = []
    for value in values[:3]:
        slug = _file_slug(value)
        if not slug:
            continue
        if area == "mobile":
            guesses.extend([f"Mobile/{slug}Page.xaml", f"Mobile/{slug}ViewModel.cs"])
        elif area == "backend":
            guesses.extend([f"Backend/{slug}Controller.cs", f"Backend/{slug}Repository.cs"])
        else:
            guesses.extend([f"Web/{slug}.tsx", f"Web/{slug}.css"])
    return guesses


def _file_slug(value: str) -> str:
    words = [word for word in _clean_text(value).replace("-", " ").split() if word.lower() not in {"display", "view", "details", "detail", "the", "a", "an"}]
    return "".join(word[:1].upper() + word[1:] for word in words)


TASK_WORK_AREAS = ["UI Work", "Frontend Work", "Backend Work", "Data Work", "Analytics Work", "QA Work"]
REJECTED_TASK_PATTERNS = ("implement", "design", "test")


def _planning_task_category(task: dict[str, Any]) -> str:
    work_area = _clean_text(task.get("work_area") or task.get("workArea")).casefold()
    title = _clean_text(task.get("title")).casefold()
    if "api" in title or "controller" in title or "endpoint" in title:
        return "API"
    return {
        "ui work": "Frontend", "frontend work": "Frontend", "backend work": "Backend",
        "data work": "Database", "analytics work": "Backend", "qa work": "Testing",
    }.get(work_area, "Backend")


def _task_intelligence(
    title: str,
    description: str,
    acceptance: list[str],
    impact: dict[str, list[str]],
    profile: dict[str, Any],
    recommended_files: list[str] | None = None,
) -> dict[str, Any]:
    story_title = _clean_text(title) or "approved story"
    lowered_context = " ".join(
        [
            story_title,
            description,
            " ".join(acceptance),
            " ".join(impact.get("affected_modules", [])),
            " ".join(impact.get("affected_flows", [])),
        ]
    ).lower()
    apps = profile.get("applications") or []
    app_types = {str(app.get("type") or "") for app in apps if isinstance(app, dict)}
    modules = impact.get("affected_modules", [])
    flows = impact.get("affected_flows", [])
    files = recommended_files or _recommended_files(profile, impact, story_title)
    subject = _task_subject(story_title)
    tasks: list[dict[str, Any]] = []

    if app_types.intersection({"Mobile", "Web Portal", "Desktop"}) or profile.get("ui_guidelines"):
        tasks.append(
            _task_candidate(
                "UI Work",
                f"Design {subject} Screen",
                "Define the product screen structure, interaction states, validation copy, and accessibility expectations for the approved story.",
                [
                    "Loading state, populated state, empty state, and error state are defined.",
                    "Required fields and user actions are identified for the screen.",
                    "Accessibility labels, keyboard behavior, and readable error copy are documented.",
                    "Screen handoff identifies affected components and navigation entry points.",
                ],
            )
        )
        tasks.append(
            _task_candidate(
                "Frontend Work",
                f"Implement {subject} View",
                "Build the user-facing view behavior, state binding, and navigation behavior for the approved story.",
                [
                    "View renders the required fields from the approved acceptance criteria.",
                    "Loading, empty, unavailable-data, and error states are handled in the view.",
                    "User can navigate back without losing search or filter context.",
                    "Frontend behavior follows configured UI guidelines and accessibility requirements.",
                ],
            )
        )
    if app_types.intersection({"Backend", "API"}) or modules or flows:
        tasks.append(
            _task_candidate(
                "Backend Work",
                f"Add {subject} API",
                f"Add the backend API behavior across {', '.join(modules[:3]) or 'the affected modules'} for the approved user outcome.",
                [
                    "API returns the approved detail fields for the selected record.",
                    "API returns related device information when available.",
                    "Invalid or missing record identifiers return an appropriate error response.",
                    "Authorization is enforced before returning protected data.",
                    "API response meets the agreed performance expectation for normal data volume.",
                ],
            )
        )
    tasks.append(
        _task_candidate(
            "Data Work",
            f"Map {subject} Data Fields",
            "Identify the data fields, persistence behavior, and state transitions needed by the story.",
            [
                "Device ID, Fault Type, Severity, Event Timestamp, Current Status, and Device Health are mapped from source to output.",
                "Missing, stale, duplicate, and unavailable data cases have defined handling.",
                "State changes are persisted or rejected according to the approved acceptance criteria.",
                "Data behavior is traceable to the affected modules or flows.",
            ],
        )
    )
    if "analytics" in lowered_context or "telemetry" in lowered_context or app_types.intersection({"Analytics"}):
        tasks.append(
            _task_candidate(
                "Analytics Work",
                f"Track {subject} Access Events",
                "Capture the telemetry, reporting, or measurement signals needed to observe the story outcome.",
                [
                    "Relevant user actions, status changes, and failure outcomes are captured as events or metrics.",
                    "Event names and payload fields are documented for analytics or operations review.",
                    "Analytics behavior avoids collecting sensitive data beyond the approved need.",
                    "Signal quality can be verified during QA without production-only access.",
                ],
            )
        )
    tasks.append(
        _task_candidate(
            "QA Work",
            f"Validate {subject} Scenarios",
            f"Prepare validation for {', '.join(flows[:3]) or 'the approved story flow'} and adjacent regression risks.",
            [
                "Manual checks cover happy path, empty state, error state, permission behavior, and regression risk.",
                "Each acceptance criterion has at least one linked validation step.",
                "Test data covers normal, boundary, and unavailable-data scenarios.",
                "Regression scope includes affected flows and modules before release approval.",
            ],
        )
    )

    if len(tasks) < 3:
        tasks.append(
            _task_candidate(
                "Backend Work",
                f"Coordinate {story_title} cross-system behavior",
                "Clarify cross-system responsibilities and contracts for the approved story.",
                [
                    "Owned behavior is separated from dependent system behavior.",
                    "Integration assumptions are listed with verification steps.",
                    "Failure behavior is defined for unavailable dependencies.",
                    "Implementation scope remains limited to the approved story.",
                ],
            )
        )
    cleaned = [_normalize_task_candidate(task, story_title) for task in tasks]
    cleaned = [task for task in cleaned if not _task_is_rejected(task, story_title)]
    if len(cleaned) < 3:
        cleaned.extend(_fallback_task_candidates(story_title, modules, flows))
    cleaned = _dedupe_tasks(cleaned)[:8]
    work_areas = _unique([task["work_area"] for task in cleaned])
    task_quality_scores = [int(task.get("task_quality_score") or 0) for task in cleaned]
    return {
        "tasks": cleaned,
        "diagnostics": {
            "work_areas": work_areas,
            "generated_task_count": len(cleaned),
            "acceptance_criteria_count": sum(len(task.get("acceptance_criteria") or []) for task in cleaned),
            "rejected_task_patterns": [f"{word.title()} <story>" for word in REJECTED_TASK_PATTERNS],
            "recommended_file_count": len(files),
            "task_quality_score": round(sum(task_quality_scores) / len(task_quality_scores), 1) if task_quality_scores else 0,
        },
    }


def _task_candidate(work_area: str, title: str, description: str, acceptance_criteria: list[str]) -> dict[str, Any]:
    return {
        "work_area": work_area,
        "title": title,
        "description": description,
        "acceptance_criteria": acceptance_criteria,
    }


def _normalize_task_candidate(task: dict[str, Any], story_title: str) -> dict[str, Any]:
    work_area = _clean_text(task.get("work_area")) or "Backend Work"
    if work_area not in TASK_WORK_AREAS:
        work_area = "Backend Work"
    title = _clean_text(task.get("title")) or f"Coordinate {story_title} delivery behavior"
    description = _clean_text(task.get("description")) or f"Complete the {work_area.lower()} needed for {story_title}."
    criteria = _string_list(task.get("acceptance_criteria"))
    if len(criteria) < 3:
        criteria.extend(
            [
                f"{work_area} scope is traceable to the approved story.",
                "Expected success and failure behavior is documented.",
                "Validation evidence can be reviewed before the task is closed.",
            ]
        )
    normalized = {
        "work_area": work_area,
        "title": title,
        "description": description,
        "acceptance_criteria": criteria[:6],
    }
    normalized["acceptance_criteria_count"] = len(normalized["acceptance_criteria"])
    normalized["task_quality_score"] = _task_quality_score(normalized)
    return normalized


def _task_is_rejected(task: dict[str, Any], story_title: str) -> bool:
    title = _clean_text(task.get("title")).lower()
    normalized_story = _clean_text(story_title).lower()
    action_verbs = ("shape", "connect", "map", "instrument", "validate", "coordinate", "prepare", "wire", "define", "capture", "verify", "design", "implement", "add", "track")
    if not title or not any(title.startswith(verb) for verb in action_verbs):
        return True
    return any(title == f"{verb} {normalized_story}" for verb in REJECTED_TASK_PATTERNS)


def _task_subject(story_title: str) -> str:
    return _clean_story_title(story_title)


def _task_quality_score(task: dict[str, Any]) -> int:
    score = 0
    title = _clean_text(task.get("title"))
    description = _clean_text(task.get("description"))
    criteria = _string_list(task.get("acceptance_criteria"))
    if any(title.lower().startswith(verb) for verb in ["design", "implement", "add", "map", "track", "validate", "connect", "shape"]):
        score += 30
    if task.get("work_area") in TASK_WORK_AREAS and any(token in title.lower() for token in ["screen", "view", "api", "data", "event", "scenario", "field"]):
        score += 30
    if description and len(description) >= 30:
        score += 15
    if len(criteria) >= 3:
        score += 15
    if _criteria_are_testable(criteria):
        score += 10
    return min(score, 100)


def _fallback_task_candidates(story_title: str, modules: list[str], flows: list[str]) -> list[dict[str, Any]]:
    return [
        _normalize_task_candidate(
            _task_candidate(
                "UI Work",
                f"Shape {story_title} interaction states",
                "Define the user interaction states needed for the approved story.",
                [
                    "Primary interaction states are listed with expected user-visible behavior.",
                    "Validation and error messages are defined before development starts.",
                    "UI behavior maps to the approved acceptance criteria.",
                ],
            ),
            story_title,
        ),
        _normalize_task_candidate(
            _task_candidate(
                "Backend Work",
                f"Connect {story_title} module behavior",
                f"Clarify backend responsibilities for {', '.join(modules[:2]) or 'the affected modules'}.",
                [
                    "Backend responsibilities are mapped to affected modules.",
                    "Authorization, validation, and failure handling are defined.",
                    "No unrelated backend behavior is changed.",
                ],
            ),
            story_title,
        ),
        _normalize_task_candidate(
            _task_candidate(
                "QA Work",
                f"Validate {story_title} flow coverage",
                f"Prepare validation for {', '.join(flows[:2]) or 'the approved flow'}.",
                [
                    "Acceptance criteria are covered by explicit validation steps.",
                    "Happy path, empty state, error state, and permission behavior are checked.",
                    "Regression coverage is identified for affected flows.",
                ],
            ),
            story_title,
        ),
    ]


def _dedupe_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for task in tasks:
        key = _clean_text(task.get("title")).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(task)
    return deduped


def _tasks_for_areas(tasks: list[dict[str, Any]], areas: list[str]) -> list[str]:
    selected = [task["title"] for task in tasks if task.get("work_area") in areas]
    return _unique(selected)


def _selected_execution_task(story: dict[str, Any], generated_tasks: list[dict[str, Any]], *, require_explicit: bool = False) -> dict[str, Any]:
    raw = story.get("selected_task") or story.get("task") or story.get("current_task")
    if isinstance(raw, dict):
        title = _clean_text(raw.get("title"))
        if title:
            for task in generated_tasks:
                if _clean_text(task.get("title")).lower() == title.lower():
                    return task
            return {
                "id": _item_id(raw),
                "title": title,
                "description": _clean_text(raw.get("description")),
                "acceptance_criteria": _string_list(raw.get("acceptance_criteria")),
                "work_area": _clean_text(raw.get("work_area")) or "Backend Work",
                "status": _clean_text(raw.get("status")) or "selected",
            }
    raw_title = _clean_text(raw) if isinstance(raw, str) else ""
    if raw_title:
        for task in generated_tasks:
            if raw_title.lower() in _clean_text(task.get("title")).lower():
                return task
    if require_explicit:
        return {}
    return generated_tasks[0] if generated_tasks else {}


def _execution_artifact_type(item: dict[str, Any] | None) -> str:
    if not isinstance(item, dict):
        return "Story"
    explicit = _clean_text(item.get("artifactType") or item.get("artifact_type") or item.get("type") or item.get("work_item_type"))
    return "Task" if explicit.casefold() == "task" else "Story"


def _execution_executable_artifact(story: dict[str, Any], options: dict[str, Any] | None) -> dict[str, Any]:
    options = options or {}
    candidate = options.get("executable_artifact") if isinstance(options.get("executable_artifact"), dict) else None
    if candidate is None and isinstance(story.get("executable_artifact"), dict):
        candidate = story.get("executable_artifact")
    if candidate is None:
        candidate = story
    artifact = dict(candidate or {})
    artifact_type = _execution_artifact_type(artifact)
    artifact["artifactType"] = artifact_type
    artifact.setdefault("type", artifact_type)
    artifact.setdefault("work_item_type", artifact_type)
    artifact.setdefault("title", story.get("title"))
    artifact.setdefault("description", story.get("description"))
    if not _string_list(artifact.get("acceptance_criteria")):
        artifact["acceptance_criteria"] = _string_list(story.get("acceptance_criteria"))
    return artifact


def _execution_parent_story(story: dict[str, Any], executable: dict[str, Any]) -> dict[str, Any]:
    if _execution_artifact_type(executable) != "Task":
        parent = dict(story or {})
        parent["artifactType"] = "Story"
        parent.setdefault("type", "Story")
        parent.setdefault("work_item_type", "Story")
        return parent
    for key in ("parent_story", "story", "parentStory"):
        parent = executable.get(key)
        if isinstance(parent, dict):
            normalized = dict(parent)
            normalized["artifactType"] = "Story"
            normalized.setdefault("type", "Story")
            normalized.setdefault("work_item_type", "Story")
            return normalized
    parent = dict(story or {})
    parent["artifactType"] = "Story"
    parent["type"] = "Story"
    parent["work_item_type"] = "Story"
    parent.setdefault("title", _clean_text(executable.get("parent_story_title")) or _clean_text(executable.get("story_title")) or _clean_text(executable.get("title")))
    parent.setdefault("description", _clean_text(executable.get("parent_story_description")) or _clean_text(executable.get("description")))
    if not _string_list(parent.get("acceptance_criteria")):
        parent["acceptance_criteria"] = _string_list(executable.get("parent_acceptance_criteria")) or _string_list(executable.get("acceptance_criteria"))
    return parent


def _acceptance_criteria_mapping(acceptance: list[str], implementation_tasks: list[str]) -> list[dict[str, str]]:
    if not acceptance:
        return []
    fallback_task = implementation_tasks[0] if implementation_tasks else "Coordinate approved behavior"
    return [
        {
            "acceptance_criterion": criterion,
            "implementation_task": implementation_tasks[index % len(implementation_tasks)] if implementation_tasks else fallback_task,
        }
        for index, criterion in enumerate(acceptance)
    ]


def _implementation_tasks(title: str, acceptance: list[str], impact: dict[str, list[str]], recommended_files: list[str]) -> list[str]:
    tasks = [
        f"Implement {title} behavior in affected modules",
        "Wire data retrieval and error handling for the approved flow",
    ]
    if impact["affected_modules"]:
        tasks.append(f"Update module integration: {', '.join(impact['affected_modules'][:3])}")
    if recommended_files:
        tasks.append(f"Update recommended files: {', '.join(recommended_files[:4])}")
    tasks.extend(f"Implement acceptance criterion: {criterion}" for criterion in acceptance[:3])
    return _unique(tasks)


def _testing_tasks(title: str, acceptance: list[str], impact: dict[str, list[str]]) -> list[str]:
    tasks = [
        f"Validate {title} happy path",
        "Validate empty, error, and permission states",
    ]
    tasks.extend(f"Test acceptance criterion: {criterion}" for criterion in acceptance[:3])
    if impact["risks"]:
        tasks.append(f"Regression check risks: {', '.join(impact['risks'][:3])}")
    if impact["affected_flows"]:
        tasks.append(f"Run flow regression: {', '.join(impact['affected_flows'][:3])}")
    return _unique(tasks)


def _documentation_tasks(title: str, profile: dict[str, Any], impact: dict[str, list[str]]) -> list[str]:
    tasks = [f"Document implementation notes for {title}"]
    if profile["knowledge_registry"]["source_files"]:
        tasks.append(f"Update relevant project docs if behavior changes: {', '.join(profile['knowledge_registry']['source_files'][:3])}")
    if impact["dependencies"]:
        tasks.append("Record dependency assumptions and validation evidence")
    return _unique(tasks)


def _implementation_notes(profile: dict[str, Any], impact: dict[str, list[str]]) -> list[str]:
    notes = [
        "Keep implementation scoped to the approved story and impacted modules.",
        "Preserve existing behavior outside affected flows.",
    ]
    if profile["readme_analysis"]["architecture_notes"]:
        notes.append("Respect README architecture notes before changing module boundaries.")
    if impact["dependencies"]:
        notes.append("Coordinate dependency behavior before final validation.")
    if impact["risks"]:
        notes.append("Cover listed risks with targeted tests or explicit verification notes.")
    return _unique(notes)


def _execution_prompt(title: str, context: dict[str, Any], instructions: list[str]) -> str:
    selected_task = context.get("selected_task") if isinstance(context.get("selected_task"), dict) else {}
    parent_story = context.get("parent_story") if isinstance(context.get("parent_story"), dict) else {}
    sections = [
        f"# {title}",
        "",
        "# Selected Task",
        f"- Title: {_clean_text(selected_task.get('title')) or 'Use the selected execution task'}",
        f"- Work Area: {_clean_text(selected_task.get('work_area')) or 'Not specified'}",
        f"- Description: {_clean_text(selected_task.get('description')) or 'Not specified'}",
        "",
        "# Story",
        _clean_text(parent_story.get("title")) or context["story_summary"],
        _clean_text(parent_story.get("description")) or context["story_summary"],
        "",
        "# Engineering DNA",
        f"- Business Outcome: {_clean_text(context.get('business_outcome')) or 'Not captured'}",
        f"- Capability: {_clean_text(context.get('capability')) or 'Not captured'}",
        f"- Responsibilities: {', '.join(_string_list(context.get('responsibilities'))) or 'Not captured'}",
        f"- In Scope: {', '.join(_string_list(context.get('in_scope'))) or 'Not captured'}",
        f"- Out Of Scope: {', '.join(_string_list(context.get('out_of_scope'))) or 'Not captured'}",
        f"- DNA Validation: {(context.get('dna_validation') or {}).get('status') if isinstance(context.get('dna_validation'), dict) else 'Not assessed'}",
        "",
        "# Acceptance Criteria",
        *_bullet_lines(context["acceptance_criteria"]),
        "",
        "# Selected Context Capsule",
        f"- Modules: {', '.join(context['affected_modules']) or 'Not identified'}",
        f"- Flows: {', '.join(context['affected_flows']) or 'Not identified'}",
        f"- Dependencies: {', '.join(context['dependencies']) or 'Not identified'}",
        f"- Repository Files: {', '.join(context['recommended_files']) or context.get('file_ranking_status') or 'Repository file ranking not available'}",
        f"- Development Standards: {_format_standards(context['development_standards']) or 'Not specified'}",
        f"- Execution Readiness: {context['execution_readiness']}",
        "",
        "# Instructions",
        *_bullet_lines(instructions),
    ]
    return "\n".join(sections).strip()


def _bullet_lines(values: list[str]) -> list[str]:
    return [f"- {value}" for value in values] if values else ["- Not identified"]


def _prompt(title: str, story_title: str, story_description: str, context_lines: list[str], instructions: list[str]) -> str:
    sections = [f"# {title}", story_title, "", "# Story", story_description, "", "# Project Context"]
    sections.extend(f"- {line}" for line in context_lines)
    sections.extend(["", "# Instructions"])
    sections.extend(f"- {line}" for line in instructions)
    return "\n".join(sections).strip()


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [_clean_text(item) for item in value.replace("\n", ",").split(",") if _clean_text(item)]
    if isinstance(value, list):
        return [_clean_text(item) for item in value if _clean_text(item)]
    return []


def _registry_names(value: Any) -> list[str]:
    if isinstance(value, list):
        names = []
        for item in value:
            if isinstance(item, dict):
                names.append(_clean_registry_name(item.get("name")))
            else:
                names.append(_clean_registry_name(item))
        return _unique([name for name in names if name])
    return _string_list(value)


def _lineage_parent_id(payload: dict[str, Any]) -> str:
    lineage = payload.get("lineage") if isinstance(payload.get("lineage"), dict) else {}
    for key in ("parentId", "parent_id", "storyId", "featureId", "epicId"):
        value = payload.get(key) or lineage.get(key)
        if value:
            return _clean_text(value)
    return ""


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


project_intelligence_service = ProjectIntelligenceService()
