"""Phase 2 Project Intelligence preview profile service."""

from __future__ import annotations

import json
import logging
import os
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.refinement.provider import get_refiner_status, get_refinement_provider


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
PROJECT_PHI_SYSTEM_PROMPT = "Return strict JSON only."
PROJECT_PHI_INSTRUCTION = "Use the compact project context. Return only the requested JSON keys."
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
        business_goal = _sentence(f"Improve {title}", description or active_profile["project_description"])
        capability_plan = _capability_decomposition(title, business_goal, keywords, relevant_profile)
        features = capability_plan["recommended_features"]
        deterministic = {
            "business_goal": business_goal,
            "business_outcomes": _business_outcomes(keywords, relevant_profile),
            "users": _users_for_profile(relevant_profile),
            "user_problems": capability_plan["user_problems"],
            "capability_categories": capability_plan["capability_categories"],
            "applications": _application_names(relevant_profile),
            "constraints": _constraints_for_profile(relevant_profile),
            "risks": _risks_for_profile(relevant_profile, keywords),
            "dependencies": _selection_names(selection, "relevant_dependencies") or _dependencies_for_profile(relevant_profile),
            "recommended_features": features,
            "capability_diagnostics": capability_plan["diagnostics"],
            "generation_review": _generation_review(relevant_profile, features, _selection_names(selection, "relevant_modules"), keywords),
            **_relevance_metadata(selection),
        }
        active_profile = self._profile_with_capsule("project", relevant_profile, epic)
        phi = _project_phi_json("refine_epic", active_profile, epic, deterministic, options, list(deterministic.keys()))
        if phi["used"]:
            merged = _merge_known_fields(deterministic, phi["parsed"], deterministic.keys())
            merged["recommended_features"] = _validate_capability_features(
                merged.get("recommended_features"),
                title,
                merged.get("business_goal") or business_goal,
                keywords,
                active_profile,
                fallback_features=features,
                diagnostics=merged.get("capability_diagnostics"),
            )
            merged["generation_review"] = _generation_review(active_profile, merged["recommended_features"], [], keywords)
            return _with_provider_metadata(merged, {**phi["metadata"], **_relevance_metadata(selection)})
        if phi["blocked"]:
            return _phi_error_response(phi)
        return _with_provider_metadata(deterministic, {**phi["metadata"], **_relevance_metadata(selection)})

    def refine_feature(
        self,
        feature: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        active_profile = _merge_external_knowledge(_normalize_profile(profile or self.get_profile()), knowledge_profile or {})
        title = _clean_text(feature.get("title")) or "Untitled feature"
        description = _clean_text(feature.get("description"))
        selection = _select_knowledge_context(active_profile, feature, "Feature")
        relevant_profile = _profile_with_relevance(active_profile, selection)
        modules = _selection_names(selection, "relevant_modules")
        flows = _selection_names(selection, "relevant_flows")
        story_plan = _story_decomposition(title, modules, flows, relevant_profile, feature)
        deterministic = {
            "feature_summary": _sentence(title, description or f"Deliver {title} using project-aware modules and flows."),
            "affected_modules": modules,
            "affected_flows": flows,
            "dependencies": _selection_names(selection, "relevant_dependencies") or _dependencies_for_profile(relevant_profile),
            "risks": _risks_for_profile(relevant_profile, _string_list(selection.get("intent", {}).get("keywords")) or _context_keywords(title, description, relevant_profile)),
            "recommended_stories": story_plan["recommended_stories"],
            "story_generation_diagnostics": story_plan["diagnostics"],
            "generation_review": _generation_review(relevant_profile, story_plan["recommended_stories"], modules, _context_keywords(title, description, relevant_profile)),
            **_relevance_metadata(selection),
        }
        active_profile = self._profile_with_capsule("feature", relevant_profile, feature)
        phi = _project_phi_json("refine_feature", active_profile, feature, deterministic, options, list(deterministic.keys()))
        if phi["used"]:
            merged = _merge_known_fields(deterministic, phi["parsed"], deterministic.keys())
            merged["recommended_stories"] = story_plan["recommended_stories"]
            merged["story_generation_diagnostics"] = story_plan["diagnostics"]
            merged["generation_review"] = deterministic["generation_review"]
            return _with_provider_metadata(merged, {**phi["metadata"], **_relevance_metadata(selection)})
        if phi["blocked"]:
            return _phi_error_response(phi)
        return _with_provider_metadata(deterministic, {**phi["metadata"], **_relevance_metadata(selection)})

    def refine_story(
        self,
        story: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        active_profile = _merge_external_knowledge(_normalize_profile(profile or self.get_profile()), knowledge_profile or {})
        title = _clean_text(story.get("title")) or "Untitled story"
        description = _clean_text(story.get("description"))
        selection = _select_knowledge_context(active_profile, story, "Story")
        relevant_profile = _profile_with_relevance(active_profile, selection)
        modules = _selection_names(selection, "relevant_modules")
        flows = _selection_names(selection, "relevant_flows")
        applications = _application_names(relevant_profile)
        impact = _normalize_story_impact(self.analyze_story_impact(story, relevant_profile, relevant_profile["knowledge_registry"]))
        acceptance = _acceptance_criteria(title, flows, modules)
        acceptance_categories = _acceptance_criteria_categories(acceptance)
        acceptance_quality_score = _acceptance_criteria_quality_score(acceptance)
        task_plan = _task_intelligence(title, description, acceptance, impact, relevant_profile)
        deterministic = {
            "story_summary": _sentence(title, description or f"Implement {title} within the approved project context."),
            "acceptance_criteria": acceptance,
            "acceptance_criteria_categories": acceptance_categories,
            "acceptance_criteria_quality_score": acceptance_quality_score,
            "affected_applications": applications,
            "affected_modules": modules,
            "affected_flows": flows,
            "dependencies": _selection_names(selection, "relevant_dependencies") or _dependencies_for_profile(relevant_profile),
            "risks": _risks_for_profile(relevant_profile, _string_list(selection.get("intent", {}).get("keywords")) or _context_keywords(title, description, relevant_profile)),
            "ui_considerations": _ui_considerations(relevant_profile, flows),
            "technical_considerations": _technical_considerations(relevant_profile, modules),
            "qa_considerations": _qa_considerations(relevant_profile, flows),
            "proposed_tasks": task_plan["tasks"],
            "task_intelligence_diagnostics": task_plan["diagnostics"],
            "generation_review": _generation_review(relevant_profile, task_plan["tasks"], modules, _context_keywords(title, description, relevant_profile)),
            **_relevance_metadata(selection),
        }
        active_profile = self._profile_with_capsule("story", relevant_profile, story)
        phi = _project_phi_json("refine_story", active_profile, story, deterministic, options, list(deterministic.keys()))
        if phi["used"]:
            merged = _merge_known_fields(deterministic, phi["parsed"], deterministic.keys())
            merged["acceptance_criteria"] = acceptance
            merged["acceptance_criteria_categories"] = acceptance_categories
            merged["acceptance_criteria_quality_score"] = acceptance_quality_score
            merged["proposed_tasks"] = task_plan["tasks"]
            merged["task_intelligence_diagnostics"] = task_plan["diagnostics"]
            merged["generation_review"] = deterministic["generation_review"]
            return _with_provider_metadata(merged, {**phi["metadata"], **_relevance_metadata(selection)})
        if phi["blocked"]:
            return _phi_error_response(phi)
        return _with_provider_metadata(deterministic, {**phi["metadata"], **_relevance_metadata(selection)})

    def generate_qa_test_cases(
        self,
        story: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
        impact_analysis: dict[str, Any] | None = None,
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
        suite = _qa_test_suite(title, description, acceptance, modules, flows, dependencies, active_profile, keywords)
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
            return _with_provider_metadata(merged, phi["metadata"])
        if phi["blocked"]:
            return _phi_error_response(phi)
        return _with_provider_metadata(suite, phi["metadata"])

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
        title = _clean_text(story.get("title")) or "Untitled story"
        description = _clean_text(story.get("description"))
        selection = _select_knowledge_context(active_profile, story, "Story")
        relevant_profile = _profile_with_relevance(active_profile, selection)
        refined_story = self.refine_story(story, relevant_profile, relevant_profile["knowledge_registry"], {"force_provider": "deterministic_fallback"})
        impact = _normalize_story_impact(
            impact_analysis or self.analyze_story_impact(story, relevant_profile, relevant_profile["knowledge_registry"])
        )
        acceptance = _string_list(story.get("acceptance_criteria")) or refined_story["acceptance_criteria"]
        has_impact = any(impact[key] for key in ["affected_applications", "affected_modules", "affected_flows", "dependencies", "risks"])
        readiness = _execution_readiness_score(relevant_profile, has_impact)
        recommended_files = _recommended_files(relevant_profile, impact, title)
        file_ranking_status = "Repository file ranking available" if recommended_files else "Repository file ranking not available"
        task_plan = _task_intelligence(title, description, acceptance, impact, relevant_profile, recommended_files)
        generated_tasks = task_plan["tasks"]
        implementation_tasks = _tasks_for_areas(generated_tasks, ["UI Work", "Backend Work", "Data Work", "Analytics Work"])
        testing_tasks = _tasks_for_areas(generated_tasks, ["QA Work"])
        documentation_tasks = _documentation_tasks(title, relevant_profile, impact)
        deterministic = {
            "story_summary": _sentence(title, description or refined_story["story_summary"]),
            "acceptance_criteria": acceptance,
            "affected_applications": impact["affected_applications"] or refined_story["affected_applications"],
            "affected_modules": impact["affected_modules"] or refined_story["affected_modules"],
            "affected_flows": impact["affected_flows"] or refined_story["affected_flows"],
            "dependencies": impact["dependencies"] or refined_story["dependencies"],
            "risks": impact["risks"] or refined_story["risks"],
            "technology_stack": relevant_profile["technology_stack"],
            "ui_guidelines": relevant_profile["ui_guidelines"],
            "development_standards": relevant_profile["development_standards"],
            "recommended_files": recommended_files,
            "file_ranking_status": file_ranking_status,
            "acceptance_criteria_mapping": _acceptance_criteria_mapping(acceptance, implementation_tasks),
            "proposed_tasks": generated_tasks,
            "task_intelligence_diagnostics": task_plan["diagnostics"],
            "implementation_tasks": implementation_tasks,
            "testing_tasks": testing_tasks,
            "documentation_tasks": documentation_tasks,
            "implementation_notes": _implementation_notes(relevant_profile, impact),
            "execution_readiness": readiness["label"],
            "execution_readiness_score": readiness["score"],
            "execution_readiness_breakdown": readiness["breakdown"],
            "execution_readiness_result": readiness["result"],
            **_relevance_metadata(selection),
        }
        active_profile = self._profile_with_capsule("execution", relevant_profile, {**story, "tasks": generated_tasks, "acceptance_criteria": acceptance})
        metadata = _execution_primary_metadata(time.monotonic(), "build_execution_context")
        if not _execution_ai_enrichment_enabled(options):
            return _with_provider_metadata(deterministic, metadata)
        phi = _project_phi_json("build_execution_context", active_profile, story, deterministic, _execution_ai_options(options), _execution_enrichment_keys("build_execution_context", deterministic))
        if phi["used"]:
            merged = _merge_known_fields(deterministic, phi["parsed"], _execution_enrichment_keys("build_execution_context", deterministic))
            merged["proposed_tasks"] = generated_tasks
            merged["task_intelligence_diagnostics"] = task_plan["diagnostics"]
            merged["implementation_tasks"] = implementation_tasks
            merged["testing_tasks"] = testing_tasks
            return _with_provider_metadata(merged, phi["metadata"])
        return _with_provider_metadata(deterministic, _execution_timeout_metadata(metadata, phi["metadata"]))

    def build_dev_prompt(
        self,
        story: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
        impact_analysis: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        context = self.build_execution_context(story, profile, knowledge_profile, impact_analysis, {"force_provider": "deterministic_fallback"})
        active_profile = _merge_external_knowledge(_normalize_profile(profile or self.get_profile()), knowledge_profile or {})
        active_profile = self._profile_with_capsule("execution", active_profile, {**(story or {}), "execution_context": context})
        deterministic = {
            "prompt": _execution_prompt(
                "Dev Prompt",
                context,
                [
                    "Implement the approved story without changing unrelated behavior.",
                    "Use the affected modules and flows as the primary implementation boundary.",
                    f"Technology Stack: {_format_stack(context['technology_stack']) or 'Confirm stack before implementation.'}",
                    f"Coding Standards: {_format_standards(context['development_standards']) or 'Follow existing project standards.'}",
                    f"Architecture Rules: {', '.join(active_profile['readme_analysis']['architecture_notes']) or 'Preserve current architecture boundaries.'}",
                    f"Recommended Files: {', '.join(context['recommended_files']) or 'Inspect the affected modules before editing.'}",
                    f"Implementation Tasks: {', '.join(context['implementation_tasks']) or 'Break down implementation before coding.'}",
                ],
            )
        }
        metadata = _execution_primary_metadata(time.monotonic(), "build_dev_prompt")
        if not _execution_ai_enrichment_enabled(options):
            return _with_provider_metadata(deterministic, metadata)
        phi = _project_phi_json("build_dev_prompt", active_profile, story, deterministic, _execution_ai_options(options), ["prompt"])
        if phi["used"]:
            return _with_provider_metadata({**deterministic, **_pick_string_fields(phi["parsed"], ["prompt"])}, phi["metadata"])
        return _with_provider_metadata(deterministic, _execution_timeout_metadata(metadata, phi["metadata"]))

    def build_ui_prompt(
        self,
        story: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
        impact_analysis: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        context = self.build_execution_context(story, profile, knowledge_profile, impact_analysis, {"force_provider": "deterministic_fallback"})
        active_profile = _merge_external_knowledge(_normalize_profile(profile or self.get_profile()), knowledge_profile or {})
        active_profile = self._profile_with_capsule("execution", active_profile, {**(story or {}), "execution_context": context})
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
        metadata = _execution_primary_metadata(time.monotonic(), "build_ui_prompt")
        if not _execution_ai_enrichment_enabled(options):
            return _with_provider_metadata(deterministic, metadata)
        phi = _project_phi_json("build_ui_prompt", active_profile, story, deterministic, _execution_ai_options(options), ["prompt"])
        if phi["used"]:
            return _with_provider_metadata({**deterministic, **_pick_string_fields(phi["parsed"], ["prompt"])}, phi["metadata"])
        return _with_provider_metadata(deterministic, _execution_timeout_metadata(metadata, phi["metadata"]))

    def build_qa_prompt(
        self,
        story: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
        impact_analysis: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        context = self.build_execution_context(story, profile, knowledge_profile, impact_analysis, {"force_provider": "deterministic_fallback"})
        active_profile = _merge_external_knowledge(_normalize_profile(profile or self.get_profile()), knowledge_profile or {})
        active_profile = self._profile_with_capsule("qa", active_profile, {**(story or {}), "execution_context": context})
        impact = _normalize_story_impact(impact_analysis or self.analyze_story_impact(story, active_profile, active_profile["knowledge_registry"]))
        deterministic = {
            "prompt": _execution_prompt(
                "QA Prompt",
                context,
                [
                    "Create manual and automation-ready coverage for the approved story.",
                    f"Risks: {', '.join(context['risks']) or 'Confirm risks before testing.'}",
                    f"Dependencies: {', '.join(context['dependencies']) or 'Confirm dependencies before testing.'}",
                    f"Integration Points: {', '.join(impact['integration_points']) or 'Confirm integration points.'}",
                    f"Regression Areas: {', '.join(_unique(context['affected_flows'] + context['affected_modules'])) or 'Confirm regression scope.'}",
                    f"Testing Tasks: {', '.join(context['testing_tasks']) or 'Define test cases before validation.'}",
                ],
            )
        }
        metadata = _execution_primary_metadata(time.monotonic(), "build_qa_prompt")
        if not _execution_ai_enrichment_enabled(options):
            return _with_provider_metadata(deterministic, metadata)
        phi = _project_phi_json("build_qa_prompt", active_profile, story, deterministic, _execution_ai_options(options), ["prompt"])
        if phi["used"]:
            return _with_provider_metadata({**deterministic, **_pick_string_fields(phi["parsed"], ["prompt"])}, phi["metadata"])
        return _with_provider_metadata(deterministic, _execution_timeout_metadata(metadata, phi["metadata"]))

    def build_copilot_context(
        self,
        story: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
        impact_analysis: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        context = self.build_execution_context(story, profile, knowledge_profile, impact_analysis, {"force_provider": "deterministic_fallback"})
        active_profile = _merge_external_knowledge(_normalize_profile(profile or self.get_profile()), knowledge_profile or {})
        active_profile = self._profile_with_capsule("execution", active_profile, {**(story or {}), "execution_context": context})
        lines = [
            "Project Awareness Context",
            "",
            f"Project: {active_profile['project_name'] or 'Not specified'}",
            f"Domain: {active_profile['domain'] or active_profile['knowledge_profile_preview']['domain'] or 'Not specified'}",
            f"Project Type: {active_profile['project_type'] or 'Not specified'}",
            "",
            f"Story: {_clean_text(story.get('title')) or 'Untitled story'}",
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
            "Architecture:",
            *_bullet_lines(active_profile["readme_analysis"]["architecture_notes"] or _flatten_standards(active_profile["development_standards"])),
            "",
            "Dependencies:",
            *_bullet_lines(context["dependencies"]),
            "",
            "Standards:",
            *_bullet_lines(_flatten_standards(context["development_standards"])),
        ]
        deterministic = {"context": "\n".join(lines).strip()}
        metadata = _execution_primary_metadata(time.monotonic(), "build_copilot_context")
        if not _execution_ai_enrichment_enabled(options):
            return _with_provider_metadata(deterministic, metadata)
        phi = _project_phi_json("build_copilot_context", active_profile, story, deterministic, _execution_ai_options(options), ["context"])
        if phi["used"]:
            return _with_provider_metadata({**deterministic, **_pick_string_fields(phi["parsed"], ["context"])}, phi["metadata"])
        return _with_provider_metadata(deterministic, _execution_timeout_metadata(metadata, phi["metadata"]))

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
    if state in {"draft", "approved", "locked", "archived"}:
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
        "approved_by": _clean_text(value.get("approved_by")),
        "approved_on": _clean_text(value.get("approved_on")),
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
    "Monitoring",
    "Alerting",
    "Investigation",
    "Analytics",
    "Reporting",
    "Maintenance",
    "Configuration",
    "Commissioning",
    "Notifications",
    "Asset Health",
    "Compliance",
    "Telemetry",
    "Device Management",
    "Firmware Management",
    "Diagnostics",
    "Operational Awareness",
    "Outage Response",
    "Field Operations",
]


def _capability_decomposition(epic_title: str, business_goal: str, keywords: list[str], profile: dict[str, Any]) -> dict[str, Any]:
    users = _users_for_profile(profile)
    problems = _user_problems_for_epic(keywords, profile)
    capabilities = _capabilities_for_epic(keywords, profile)
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
        supplement = [_feature_from_capability(capability, keywords, users, profile) for capability in CAPABILITY_TAXONOMY if capability not in capabilities]
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


def _capabilities_for_epic(keywords: list[str], profile: dict[str, Any]) -> list[str]:
    selected: list[str] = []
    keyword_set = set(keywords)
    modules_text = " ".join(profile["knowledge_registry"]["modules"]).lower()
    flows_text = " ".join(profile["knowledge_registry"]["flows"]).lower()
    corpus = " ".join([*keywords, modules_text, flows_text])
    if {"fault", "event", "monitoring"} & keyword_set or "fault" in corpus:
        selected.extend(["Monitoring", "Alerting", "Investigation", "Analytics", "Operational Awareness"])
    if "outage" in corpus:
        selected.extend(["Outage Response", "Field Operations", "Investigation"])
    if {"telemetry", "device"} & keyword_set or "telemetry" in corpus:
        selected.extend(["Telemetry", "Asset Health", "Diagnostics"])
    if {"firmware", "upgrade"} & keyword_set or "firmware" in corpus:
        selected.extend(["Firmware Management", "Maintenance", "Compliance"])
    if "report" in corpus or "analytics" in corpus:
        selected.extend(["Reporting", "Analytics"])
    if "configuration" in corpus or "settings" in corpus:
        selected.extend(["Configuration"])
    if "commission" in corpus or "onboard" in corpus:
        selected.extend(["Commissioning"])
    if not selected:
        selected.extend(["Operational Awareness", "Configuration", "Reporting", "Notifications", "Analytics"])
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
    outcome = _business_outcome_for_capability(capability, keywords)
    user_problem = _user_problem_for_capability(capability, keywords)
    primary_users = _users_for_capability(capability, users)
    return {
        "title": title,
        "description": _feature_description(title, capability, outcome, primary_users, modules, flows, profile),
        "capability": capability,
        "business_outcome": outcome,
        "user_problem": user_problem,
        "primary_users": primary_users,
        "impacted_modules": modules,
        "impacted_flows": flows,
        "reasoning": f"{title} is a separate {capability.lower()} capability because it solves '{user_problem}' and can be delivered independently against {', '.join(modules) or 'the affected modules'}.",
    }


def _capability_feature_title(capability: str, keywords: list[str], profile: dict[str, Any]) -> str:
    corpus = " ".join([*keywords, *profile["knowledge_registry"]["modules"], *profile["knowledge_registry"]["flows"]]).lower()
    fault_context = "fault" in corpus or "outage" in corpus
    titles = {
        "Monitoring": "Critical Fault Detection" if fault_context else "Operational Signal Detection",
        "Alerting": "Operator Alerting" if fault_context else "Operational Alerting",
        "Investigation": "Outage Investigation Workspace" if "outage" in corpus or fault_context else "Issue Investigation Workspace",
        "Analytics": "Reliability Trend Analytics" if fault_context or "asset" in corpus else "Operational Trend Analytics",
        "Reporting": "Reliability Reporting" if fault_context else "Operational Reporting",
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
        "Monitoring": ["fault", "telemetry"],
        "Alerting": ["fault", "telemetry", "notification"],
        "Investigation": ["fault", "report", "event"],
        "Analytics": ["report", "asset", "telemetry"],
        "Reporting": ["report", "analytics"],
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
        "Monitoring": ["fault", "review", "event"],
        "Alerting": ["fault", "outage"],
        "Investigation": ["investigation", "fault", "review"],
        "Analytics": ["health", "review", "analytics"],
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
        "Monitoring": "Faster detection of critical operating conditions.",
        "Alerting": "Reduced response time through actionable operator notifications.",
        "Investigation": "Faster root-cause analysis and outage triage.",
        "Analytics": "Better prioritization through reliability trends and operational insight.",
        "Reporting": "Clearer stakeholder visibility into reliability and service outcomes.",
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
        "Monitoring": "critical events are not visible early enough",
        "Alerting": "operators do not know which events require immediate action",
        "Investigation": "teams lose time correlating event context during outages",
        "Analytics": "leaders lack trend evidence for prioritization",
        "Reporting": "stakeholders lack clear operational evidence",
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
        "Alerting": ["Operations User", "Field Technician"],
        "Investigation": ["Operations User", "Field Technician"],
        "Analytics": ["Operations Manager"],
        "Reporting": ["Operations Manager"],
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
        "Monitoring": {"dashboard": 100, "mobile": 85, "backend": 90, "analytics": 55, "firmware": 20, "other": 45},
        "Alerting": {"dashboard": 100, "mobile": 95, "backend": 90, "analytics": 40, "firmware": 10, "other": 40},
        "Investigation": {"dashboard": 100, "mobile": 75, "backend": 90, "analytics": 70, "firmware": 10, "other": 40},
        "Analytics": {"analytics": 100, "dashboard": 90, "backend": 80, "mobile": 40, "firmware": 10, "other": 35},
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
        "Monitoring": ["fault", "event", "telemetry", "health", "review"],
        "Alerting": ["alert", "notification", "fault", "outage", "event"],
        "Investigation": ["investigation", "outage", "fault", "event", "review"],
        "Analytics": ["analytics", "trend", "report", "health", "telemetry"],
        "Operational Awareness": ["live", "status", "operation", "event", "device"],
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


def _feature_description(name: str, capability: str, outcome: str, users: list[str], modules: list[str], flows: list[str], profile: dict[str, Any]) -> str:
    user_text = ", ".join(users[:3]) or "operations users"
    module_text = ", ".join(modules[:3]) or "the selected project modules"
    flow_text = ", ".join(flows[:3]) or "the selected delivery flows"
    application_text = ", ".join(_application_names(profile)[:4]) or "the configured applications"
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
        "Monitoring": "Allow operators to identify critical LineDefender fault events immediately after occurrence.",
        "Alerting": "Ensure operators and field technicians receive actionable notifications for events requiring response.",
        "Investigation": "Help operations teams investigate outages with correlated event, device, and status context.",
        "Analytics": "Give operations managers reliability trends that support prioritization and planning.",
        "Reporting": "Provide clear operational evidence for reliability and service reporting.",
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
        "Monitoring": [
            "Operator can view all active critical fault events in a single list.",
            "Event list displays Device ID, Fault Type, Severity, Event Time, and Current Status.",
            "Critical events are visually differentiated from warning and informational events.",
            "Newly ingested critical events appear in the event list within 60 seconds.",
            "Operator can open detailed event information from the event list.",
            "System displays a clear unavailable-data message when event data cannot be loaded.",
            "All event list and event detail access actions are audit logged.",
        ],
        "Alerting": [
            "Operator receives an alert when a critical fault event is created.",
            "Alert displays Device ID, Fault Type, Severity, Event Time, and Recommended Action.",
            "Operator can acknowledge an alert and the acknowledgement is timestamped.",
            "Escalation status changes are visible within 60 seconds of update.",
            "Field technician can identify alerts assigned for field response.",
            "Duplicate alerts for the same active event are suppressed or grouped.",
        ],
        "Investigation": [
            "Operator can open an outage investigation workspace from a fault event.",
            "Workspace shows related device, telemetry, event timeline, and current status.",
            "Operator can filter investigation events by severity, device, and time range.",
            "Workspace highlights missing telemetry or stale device status data.",
            "Investigation notes are saved with user and timestamp.",
            "Workspace preserves the investigation trail for audit review.",
        ],
        "Analytics": [
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
        "Monitoring": ["Telemetry Service", "Event Repository", "Severity Classification Rules", "Audit Logging Service"],
        "Alerting": ["Notification Service", "Event Repository", "User Assignment Service", "Audit Logging Service"],
        "Investigation": ["Event Timeline Service", "Telemetry Service", "Device State Service", "Investigation Notes Store"],
        "Analytics": ["Analytics Data Mart", "Reporting Pipeline", "Telemetry Aggregation Service"],
        "Operational Awareness": ["Live Status Service", "Event Repository", "Device State Service"],
        "Outage Response": ["Outage Coordination Service", "Field Assignment Service", "Device Communication Layer"],
        "Asset Health": ["Asset Health Service", "Telemetry Service", "Device Registry"],
        "Telemetry": ["Telemetry Ingestion Service", "Telemetry Quality Rules", "Device Communication Layer"],
        "Firmware Management": ["Firmware Registry", "Device Communication Layer", "Rollout Tracking Service"],
    }
    return dependencies.get(capability, ["Authentication Service", "Audit Logging Service", "Project Data Service"])


def _feature_risks(capability: str) -> list[str]:
    risks = {
        "Monitoring": ["Delayed telemetry ingestion", "Duplicate fault events", "Incorrect severity classification", "Event processing latency"],
        "Alerting": ["Alert fatigue from noisy rules", "Duplicate notifications", "Delayed escalation delivery", "Incorrect owner assignment"],
        "Investigation": ["Missing event correlation", "Stale device status", "Incomplete outage timeline", "Manual notes becoming inconsistent"],
        "Analytics": ["Incomplete historical data", "Delayed aggregation jobs", "Misleading trend interpretation", "Unclear metric definitions"],
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
    for raw in features if isinstance(features, list) else []:
        feature = _normalize_capability_feature(raw, keywords, profile)
        title = feature.get("title", "")
        reason = _feature_rejection_reason(feature, epic_title, business_goal)
        if reason:
            rejected.append({"title": title, "reason": reason, "similarity": round(_max_feature_similarity(title, epic_title, business_goal), 3)})
            continue
        if title and title not in [item["title"] for item in normalized]:
            normalized.append(feature)
        if len(normalized) >= 10:
            break
    if len(normalized) < 5 and fallback_features:
        for feature in fallback_features:
            enriched = _normalize_capability_feature(feature, keywords, profile)
            if not _feature_rejection_reason(enriched, epic_title, business_goal) and enriched["title"] not in [item["title"] for item in normalized]:
                normalized.append(enriched)
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
        "description": _feature_description(title, capability, outcome, users, modules, flows, profile),
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
        return "Alerting"
    if "investigation" in lowered or "workspace" in lowered:
        return "Investigation"
    if "analytics" in lowered or "trend" in lowered or "classification" in lowered or "prioritization" in lowered:
        return "Analytics"
    if "health" in lowered:
        return "Asset Health"
    if "telemetry" in lowered:
        return "Telemetry"
    if "firmware" in lowered:
        return "Firmware Management"
    if "field" in lowered or "response" in lowered:
        return "Field Operations"
    if "report" in lowered:
        return "Reporting"
    return "Monitoring" if "fault" in " ".join(keywords).lower() else "Operational Awareness"


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
        "Monitoring": [
            {"title": "View Active Critical Fault Events", "want": "to view active critical fault events", "benefit": "I can identify issues that need immediate attention", "goal": "Detect critical events", "coverage_area": "View"},
            {"title": "Open Critical Fault Event Details", "want": "to open detailed information for a critical fault event", "benefit": "I can understand the device, severity, timing, and current status", "goal": "Review event details", "coverage_area": "Details"},
            {"title": "Search Critical Events by Device", "want": "to search critical events by device or event identifier", "benefit": "I can quickly find the event I need to review", "goal": "Find event", "coverage_area": "Search"},
            {"title": "Filter Critical Events by Severity and Status", "want": "to filter critical events by severity and status", "benefit": "I can focus on the highest priority events first", "goal": "Prioritize event review", "coverage_area": "Filter"},
            {"title": "See Newly Arrived Critical Events Quickly", "want": "new critical events to appear quickly", "benefit": "I can respond without waiting for manual refresh or delayed reports", "goal": "Maintain live awareness", "coverage_area": "Notifications"},
            {"title": "Recognize Unavailable Event Data", "want": "to see a clear message when event data is unavailable", "benefit": "I know when the system cannot provide complete information", "goal": "Handle data gaps", "coverage_area": "Empty states"},
            {"title": "Review Critical Event Access History", "want": "to know when critical event details were accessed", "benefit": "I can support audit and operational traceability", "goal": "Audit event access", "coverage_area": "Audit requirements"},
        ],
        "Alerting": [
            {"title": "Receive Critical Fault Alerts", "want": "to receive alerts for critical fault events", "benefit": "I can respond before an issue escalates", "goal": "Get notified", "coverage_area": "Notifications"},
            {"title": "Review Alert Details Before Acting", "want": "to review alert details before taking action", "benefit": "I can decide the right response with enough context", "goal": "Understand alert context", "coverage_area": "Details"},
            {"title": "Search Assigned Alerts", "want": "to search alerts assigned to me", "benefit": "I can find a specific alert quickly", "goal": "Find alert", "coverage_area": "Search"},
            {"title": "Filter Alerts by Severity and Owner", "want": "to filter alerts by severity and owner", "benefit": "I can focus on alerts that need my response", "goal": "Prioritize alerts", "coverage_area": "Filter"},
            {"title": "Acknowledge Assigned Alerts", "want": "to acknowledge alerts assigned to me", "benefit": "the team can see that response is underway", "goal": "Confirm ownership", "coverage_area": "Audit requirements"},
            {"title": "Avoid Duplicate Alert Noise", "want": "related duplicate alerts to be grouped", "benefit": "I can focus on the actual event instead of repeated notifications", "goal": "Reduce alert noise", "coverage_area": "Error handling"},
        ],
        "Investigation": [
            {"title": "Start an Outage Investigation", "want": "to start an outage investigation from a fault event", "benefit": "I can begin triage from the event that triggered concern", "goal": "Begin investigation", "coverage_area": "View"},
            {"title": "Review Event Timeline", "want": "to review the timeline of related events", "benefit": "I can understand what happened before and after the outage", "goal": "Understand sequence", "coverage_area": "Details"},
            {"title": "Search Investigation Evidence", "want": "to search investigation evidence by device or event", "benefit": "I can locate the information needed for triage", "goal": "Find evidence", "coverage_area": "Search"},
            {"title": "Filter Investigation Evidence", "want": "to filter investigation evidence by severity, device, and time", "benefit": "I can find relevant evidence quickly", "goal": "Narrow evidence", "coverage_area": "Filter"},
            {"title": "Add Investigation Notes", "want": "to add notes during the investigation", "benefit": "the team has a shared record of findings", "goal": "Capture findings", "coverage_area": "Audit requirements"},
            {"title": "Review Missing or Stale Data", "want": "to see when investigation data is missing or stale", "benefit": "I can avoid drawing conclusions from incomplete information", "goal": "Assess data quality", "coverage_area": "Empty states"},
        ],
        "Analytics": [
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
    return {**profile, "knowledge_registry": registry, "_knowledge_relevance": selection}


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
        _qa_positive_test(title, acceptance, flows, modules),
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


def _qa_positive_test(title: str, acceptance: list[str], flows: list[str], modules: list[str]) -> dict[str, Any]:
    expected = acceptance[0] if acceptance else f"{title} completes successfully."
    flow = flows[0] if flows else "approved user flow"
    module = modules[0] if modules else "affected module"
    return _qa_case(
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
    )


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
    if force_provider != "azure_phi" and health.get("health") != "healthy":
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
    for prompt, attempt_diagnostics in attempts:
        context_diagnostics = attempt_diagnostics
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
        probe = provider.probe_json(
            PROJECT_PHI_SYSTEM_PROMPT,
            prompt,
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
    prompt = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
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
    updated.update(
        {
            "reserved_tokens": reserved_tokens,
            "system_prompt_tokens": system_tokens,
            "user_prompt_tokens": user_tokens,
            "output_schema_tokens": output_schema_tokens,
            "final_prompt_tokens": final_tokens,
            "model_context_limit": _model_context_limit_tokens(),
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
        "provider_configured": bool(config.get("configured", provider.is_enabled() if hasattr(provider, "is_enabled") else False)),
        "provider_deployment": health.get("deployment") or config.get("deployment"),
        "provider_health": health.get("health") or config.get("deployment_health") or "unknown",
        "provider_last_success": health.get("last_success"),
        "provider_last_failure": health.get("last_failure"),
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
    cleaned = _clean_story_title(story_title)
    lowered = cleaned.lower()
    if "critical fault event details" in lowered or ("fault" in lowered and "detail" in lowered):
        return "Critical Fault Event Detail"
    if "critical fault" in lowered:
        return "Critical Fault Event"
    if "device health" in lowered:
        return "Device Health"
    if "telemetry" in lowered:
        return "Telemetry"
    return cleaned


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
    sections = [
        f"# {title}",
        "",
        "# Story",
        context["story_summary"],
        "",
        "# Acceptance Criteria",
        *_bullet_lines(context["acceptance_criteria"]),
        "",
        "# Impact Analysis",
        f"- Applications: {', '.join(context['affected_applications']) or 'Not identified'}",
        f"- Modules: {', '.join(context['affected_modules']) or 'Not identified'}",
        f"- Flows: {', '.join(context['affected_flows']) or 'Not identified'}",
        f"- Dependencies: {', '.join(context['dependencies']) or 'Not identified'}",
        f"- Risks: {', '.join(context['risks']) or 'Not identified'}",
        "",
        "# Project Context",
        f"- Technology Stack: {_format_stack(context['technology_stack']) or 'Not specified'}",
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


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


project_intelligence_service = ProjectIntelligenceService()
