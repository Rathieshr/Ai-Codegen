"""Phase 2 Project Intelligence preview profile service."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.refinement.provider import get_refiner_status, get_refinement_provider


PROJECT_CONTEXT_MIN_TOKENS = 1500
PROJECT_CONTEXT_MAX_TOKENS = 2500
PROJECT_CONTEXT_DEFAULT_TOKENS = 2200


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
    "project_name": "",
    "domain": "",
    "project_type": "",
    "project_description": "",
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
        self._profile_path = data_dir / "project_intelligence" / "profile.json"
        self._profile_path.parent.mkdir(parents=True, exist_ok=True)

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
        return normalized

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
            return _with_provider_metadata({"error": phi["metadata"]["fallback_reason"], **deterministic}, phi["metadata"])
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
            return _with_provider_metadata({"error": phi["metadata"]["fallback_reason"], **deterministic}, phi["metadata"])
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
    ) -> dict[str, Any]:
        active_profile = _normalize_profile(profile or self.get_profile())
        repository = repository or {}
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
            "repository_id": _clean_text(repository.get("repository_id")) or _clean_text(repository.get("id")) or active_profile["repository_connection"]["repository_id"],
            "repository_name": _clean_text(repository.get("repository_name")) or _clean_text(repository.get("name")) or active_profile["repository_connection"]["repository_name"],
            "branch": _clean_text(repository.get("branch")) or active_profile["repository_connection"]["branch"],
            "status": "Repository documents analyzed" if documents else active_profile["repository_connection"]["status"],
            "readme_path": active_profile["repository_connection"]["readme_path"] or "/README.md",
        }
        next_profile = {
            **active_profile,
            "repository_connection": repository_connection,
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
        keywords = _context_keywords(title, description, active_profile)
        features = _recommended_features(keywords, active_profile)
        deterministic = {
            "business_goal": _sentence(f"Improve {title}", description or active_profile["project_description"]),
            "business_outcomes": _business_outcomes(keywords, active_profile),
            "users": _users_for_profile(active_profile),
            "applications": _application_names(active_profile),
            "constraints": _constraints_for_profile(active_profile),
            "risks": _risks_for_profile(active_profile, keywords),
            "dependencies": _dependencies_for_profile(active_profile),
            "recommended_features": features,
        }
        phi = _project_phi_json("refine_epic", active_profile, epic, deterministic, options, list(deterministic.keys()))
        if phi["used"]:
            return _with_provider_metadata(_merge_known_fields(deterministic, phi["parsed"], deterministic.keys()), phi["metadata"])
        if phi["blocked"]:
            return _with_provider_metadata({"error": phi["metadata"]["fallback_reason"], **deterministic}, phi["metadata"])
        return _with_provider_metadata(deterministic, phi["metadata"])

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
        modules = _select_relevant_items(active_profile["knowledge_registry"]["modules"], title, description, fallback_count=3)
        flows = _select_relevant_items(active_profile["knowledge_registry"]["flows"], title, description, fallback_count=3)
        deterministic = {
            "feature_summary": _sentence(title, description or f"Deliver {title} using project-aware modules and flows."),
            "affected_modules": modules,
            "affected_flows": flows,
            "dependencies": _dependencies_for_profile(active_profile),
            "risks": _risks_for_profile(active_profile, _context_keywords(title, description, active_profile)),
            "recommended_stories": _recommended_stories(title, modules, flows, active_profile),
        }
        phi = _project_phi_json("refine_feature", active_profile, feature, deterministic, options, list(deterministic.keys()))
        if phi["used"]:
            return _with_provider_metadata(_merge_known_fields(deterministic, phi["parsed"], deterministic.keys()), phi["metadata"])
        if phi["blocked"]:
            return _with_provider_metadata({"error": phi["metadata"]["fallback_reason"], **deterministic}, phi["metadata"])
        return _with_provider_metadata(deterministic, phi["metadata"])

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
        modules = _select_relevant_items(active_profile["knowledge_registry"]["modules"], title, description, fallback_count=3)
        flows = _select_relevant_items(active_profile["knowledge_registry"]["flows"], title, description, fallback_count=3)
        applications = _application_names(active_profile)
        deterministic = {
            "story_summary": _sentence(title, description or f"Implement {title} within the approved project context."),
            "acceptance_criteria": _acceptance_criteria(title, flows, modules),
            "affected_applications": applications,
            "affected_modules": modules,
            "affected_flows": flows,
            "dependencies": _dependencies_for_profile(active_profile),
            "risks": _risks_for_profile(active_profile, _context_keywords(title, description, active_profile)),
            "ui_considerations": _ui_considerations(active_profile, flows),
            "technical_considerations": _technical_considerations(active_profile, modules),
            "qa_considerations": _qa_considerations(active_profile, flows),
        }
        phi = _project_phi_json("refine_story", active_profile, story, deterministic, options, list(deterministic.keys()))
        if phi["used"]:
            return _with_provider_metadata(_merge_known_fields(deterministic, phi["parsed"], deterministic.keys()), phi["metadata"])
        if phi["blocked"]:
            return _with_provider_metadata({"error": phi["metadata"]["fallback_reason"], **deterministic}, phi["metadata"])
        return _with_provider_metadata(deterministic, phi["metadata"])

    def analyze_story_impact(
        self,
        story: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        active_profile = _merge_external_knowledge(_normalize_profile(profile or self.get_profile()), knowledge_profile or {})
        title = _clean_text(story.get("title")) or "Untitled story"
        description = _clean_text(story.get("description"))
        keywords = _context_keywords(title, description, active_profile)
        modules = _impact_modules(active_profile, title, description, keywords)
        flows = _impact_flows(active_profile, title, description, keywords)
        return {
            "affected_applications": _impact_applications(active_profile, keywords),
            "affected_modules": modules,
            "affected_flows": flows,
            "affected_components": _impact_components(active_profile, modules, flows),
            "dependencies": _impact_dependencies(active_profile, keywords, modules, flows),
            "risks": _impact_risks(active_profile, keywords, modules, flows),
            "integration_points": _integration_points(active_profile, modules, flows),
            "recommended_reviewers": _recommended_reviewers(active_profile, modules, flows),
            **_fallback_metadata("deterministic_fallback", "impact analysis is deterministic in this preview."),
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
        keywords = _context_keywords(title, description, active_profile)
        modules = _impact_modules(active_profile, title, description, keywords, fallback_count=4)
        flows = _impact_flows(active_profile, title, description, keywords, fallback_count=4)
        return {
            "affected_applications": _impact_applications(active_profile, keywords),
            "affected_modules": modules,
            "affected_flows": flows,
            "cross_team_dependencies": _cross_team_dependencies(active_profile, modules),
            "integration_points": _integration_points(active_profile, modules, flows),
            "risks": _impact_risks(active_profile, keywords, modules, flows),
            **_fallback_metadata("deterministic_fallback", "impact analysis is deterministic in this preview."),
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
        keywords = _context_keywords(title, description, active_profile)
        modules = _impact_modules(active_profile, title, description, keywords, fallback_count=6)
        flows = _impact_flows(active_profile, title, description, keywords, fallback_count=6)
        return {
            "affected_applications": _impact_applications(active_profile, keywords),
            "affected_modules": modules,
            "affected_flows": flows,
            "program_dependencies": _program_dependencies(active_profile, modules, flows),
            "risks": _impact_risks(active_profile, keywords, modules, flows),
            "recommended_rollout_strategy": _rollout_strategy(active_profile, keywords),
            **_fallback_metadata("deterministic_fallback", "impact analysis is deterministic in this preview."),
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
        refined_story = self.refine_story(story, active_profile, active_profile["knowledge_registry"], {"force_provider": "deterministic_fallback"})
        impact = _normalize_story_impact(
            impact_analysis or self.analyze_story_impact(story, active_profile, active_profile["knowledge_registry"])
        )
        acceptance = _string_list(story.get("acceptance_criteria")) or refined_story["acceptance_criteria"]
        has_impact = any(impact[key] for key in ["affected_applications", "affected_modules", "affected_flows", "dependencies", "risks"])
        readiness = _execution_readiness_score(active_profile, has_impact)
        recommended_files = _recommended_files(active_profile, impact, title)
        implementation_tasks = _implementation_tasks(title, acceptance, impact, recommended_files)
        testing_tasks = _testing_tasks(title, acceptance, impact)
        documentation_tasks = _documentation_tasks(title, active_profile, impact)
        deterministic = {
            "story_summary": _sentence(title, description or refined_story["story_summary"]),
            "acceptance_criteria": acceptance,
            "affected_applications": impact["affected_applications"] or refined_story["affected_applications"],
            "affected_modules": impact["affected_modules"] or refined_story["affected_modules"],
            "affected_flows": impact["affected_flows"] or refined_story["affected_flows"],
            "dependencies": impact["dependencies"] or refined_story["dependencies"],
            "risks": impact["risks"] or refined_story["risks"],
            "technology_stack": active_profile["technology_stack"],
            "ui_guidelines": active_profile["ui_guidelines"],
            "development_standards": active_profile["development_standards"],
            "recommended_files": recommended_files,
            "acceptance_criteria_mapping": _acceptance_criteria_mapping(acceptance, implementation_tasks),
            "implementation_tasks": implementation_tasks,
            "testing_tasks": testing_tasks,
            "documentation_tasks": documentation_tasks,
            "implementation_notes": _implementation_notes(active_profile, impact),
            "execution_readiness": readiness["label"],
            "execution_readiness_score": readiness["score"],
            "execution_readiness_breakdown": readiness["breakdown"],
            "execution_readiness_result": readiness["result"],
        }
        phi = _project_phi_json("build_execution_context", active_profile, story, deterministic, options, list(deterministic.keys()))
        if phi["used"]:
            return _with_provider_metadata(_merge_known_fields(deterministic, phi["parsed"], deterministic.keys()), phi["metadata"])
        if phi["blocked"]:
            return _with_provider_metadata({"error": phi["metadata"]["fallback_reason"], **deterministic}, phi["metadata"])
        return _with_provider_metadata(deterministic, phi["metadata"])

    def build_dev_prompt(
        self,
        story: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
        impact_analysis: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        context = self.build_execution_context(story, profile, knowledge_profile, impact_analysis, options)
        active_profile = _merge_external_knowledge(_normalize_profile(profile or self.get_profile()), knowledge_profile or {})
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
        phi = _project_phi_json("build_dev_prompt", active_profile, story, deterministic, options, ["prompt"])
        if phi["used"]:
            return _with_provider_metadata({**deterministic, **_pick_string_fields(phi["parsed"], ["prompt"])}, phi["metadata"])
        if phi["blocked"]:
            return _with_provider_metadata({"error": phi["metadata"]["fallback_reason"], **deterministic}, phi["metadata"])
        return _with_provider_metadata(deterministic, phi["metadata"])

    def build_ui_prompt(
        self,
        story: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
        impact_analysis: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        context = self.build_execution_context(story, profile, knowledge_profile, impact_analysis, options)
        active_profile = _merge_external_knowledge(_normalize_profile(profile or self.get_profile()), knowledge_profile or {})
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
        phi = _project_phi_json("build_ui_prompt", active_profile, story, deterministic, options, ["prompt"])
        if phi["used"]:
            return _with_provider_metadata({**deterministic, **_pick_string_fields(phi["parsed"], ["prompt"])}, phi["metadata"])
        if phi["blocked"]:
            return _with_provider_metadata({"error": phi["metadata"]["fallback_reason"], **deterministic}, phi["metadata"])
        return _with_provider_metadata(deterministic, phi["metadata"])

    def build_qa_prompt(
        self,
        story: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
        impact_analysis: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        context = self.build_execution_context(story, profile, knowledge_profile, impact_analysis, options)
        active_profile = _merge_external_knowledge(_normalize_profile(profile or self.get_profile()), knowledge_profile or {})
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
        phi = _project_phi_json("build_qa_prompt", active_profile, story, deterministic, options, ["prompt"])
        if phi["used"]:
            return _with_provider_metadata({**deterministic, **_pick_string_fields(phi["parsed"], ["prompt"])}, phi["metadata"])
        if phi["blocked"]:
            return _with_provider_metadata({"error": phi["metadata"]["fallback_reason"], **deterministic}, phi["metadata"])
        return _with_provider_metadata(deterministic, phi["metadata"])

    def build_copilot_context(
        self,
        story: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
        impact_analysis: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        context = self.build_execution_context(story, profile, knowledge_profile, impact_analysis, options)
        active_profile = _merge_external_knowledge(_normalize_profile(profile or self.get_profile()), knowledge_profile or {})
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
        phi = _project_phi_json("build_copilot_context", active_profile, story, deterministic, options, ["context"])
        if phi["used"]:
            return _with_provider_metadata({**deterministic, **_pick_string_fields(phi["parsed"], ["context"])}, phi["metadata"])
        if phi["blocked"]:
            return _with_provider_metadata({"error": phi["metadata"]["fallback_reason"], **deterministic}, phi["metadata"])
        return _with_provider_metadata(deterministic, phi["metadata"])

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
    normalized = {
        "onboarding_completed": bool(profile.get("onboarding_completed")),
        "project_name": _clean_text(profile.get("project_name")),
        "domain": _clean_text(profile.get("domain")),
        "project_type": _clean_text(profile.get("project_type")),
        "project_description": _clean_text(profile.get("project_description")),
        "repository_connection": _normalize_repository_connection(profile.get("repository_connection")),
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
    has_description = bool(_clean_text(profile.get("project_description")) or _clean_text(profile.get("project_name")))
    has_apps = bool(_normalize_applications(profile.get("applications")))
    stack = _normalize_stack(profile.get("technology_stack"))
    has_stack = any(stack.values())
    registry = _normalize_knowledge_registry(profile.get("knowledge_registry"))
    has_repository_docs = bool(_string_list(profile.get("repository_sources")) or registry["source_files"])
    has_registry = bool(registry["modules"] and registry["flows"])
    standards = profile.get("development_standards") if isinstance(profile.get("development_standards"), dict) else {}
    has_standards = bool(_flatten_standards(standards) or registry["standards"])
    if has_description and has_apps and has_stack and has_repository_docs and has_registry and has_standards:
        return "Execution Ready"
    if has_description and has_apps and has_stack and has_repository_docs and has_registry:
        return "Advanced"
    if has_description and has_apps and has_stack and has_standards:
        return "Advanced"
    if has_description and has_apps and has_stack:
        return "Intermediate"
    return "Basic"


def _flatten_standards(standards: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ["architecture_patterns", "coding_guidelines", "security_requirements", "testing_requirements"]:
        values.extend(_string_list(standards.get(key)))
    return values


def _format_applications(applications: list[dict[str, str]]) -> str:
    return ", ".join(f"{app['name']} ({app['type']})" for app in applications)


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
    detected_stack = _normalize_stack({})
    warnings: list[str] = []
    source_files: list[str] = []

    for path, content in documents.items():
        lowered_path = path.lower()
        source_files.append(path)
        parsed = _analyze_readme_content(content)
        detected_stack = _merge_stack(detected_stack, parsed.get("technology_stack", {}), _infer_stack(content))
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
    module_details = _unique_details(module_details, "name")
    flow_details = _unique_details(flow_details, "name")
    component_details = _unique_details(component_details, "name")
    detected_modules = _clean_registry_names(_unique([*detected_modules, *[item["name"] for item in module_details]]), kind="module")
    detected_flows = _clean_registry_names(_unique([*detected_flows, *[item["name"] for item in flow_details]]), kind="flow")
    detected_components = _clean_registry_names(_unique([*detected_components, *[item["name"] for item in component_details]]), kind="component")
    standards = _unique([*ui_standards, *development_standards])
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
        parts = ["The LineDefender platform is a multi-system architecture with mobile, backend, dashboard, analytics, and device telemetry integration layers"]
        technologies = []
        if "maui" in lowered or ".net maui" in lowered:
            technologies.append(".NET MAUI for field mobile workflows")
        if "asp.net" in lowered or "rest api" in lowered or "rest APIs".lower() in lowered:
            technologies.append("ASP.NET Core REST APIs for device and telemetry services")
        if "react" in lowered or "typescript" in lowered:
            technologies.append("React/TypeScript for operator dashboards")
        if "databricks" in lowered or "azure" in lowered:
            technologies.append("Azure/Databricks for analytics")
        if technologies:
            parts.append("It uses " + ", ".join(technologies))
        return ". ".join(parts).rstrip(".") + "."
    if notes:
        return " ".join(notes[:3])[:600]
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
    blocked = ["token management", "identity provider", "device id", "serial number", "timestamp", "responsibilities", "dependencies", "unit tests", "input validation", "audit logging"]
    if any(block in lowered for block in blocked):
        return False
    return any(word in lowered for word in ["auth", "device", "telemetry", "fault", "firmware", "asset", "report", "meter", "inventory", "billing", "outage", "monitoring", "repository"])


def _is_flow_name(name: str) -> bool:
    cleaned = _clean_registry_name(name)
    lowered = cleaned.lower()
    if not cleaned or len(cleaned.split()) > 7:
        return False
    if any(block in lowered for block in ["field", "timestamp", "serial number", "device id", "rules", "standards"]):
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
    for item in detected:
        lowered = item.lower()
        if any(word in lowered for word in ["security", "oauth", "jwt", "secret", "permission"]):
            normalized["security_requirements"].append(item)
        elif any(word in lowered for word in ["test", "coverage", "qa"]):
            normalized["testing_requirements"].append(item)
        elif any(word in lowered for word in ["mvvm", "repository", "architecture", "pattern"]):
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


def _recommended_features(keywords: list[str], profile: dict[str, Any]) -> list[dict[str, str]]:
    names: list[str] = []
    if {"fault", "event"} & set(keywords):
        names.append("Fault Event Monitoring")
    if {"telemetry", "health", "device", "monitoring"} & set(keywords):
        names.append("Telemetry Health Dashboard")
        names.append("Device Health Monitoring")
    if {"firmware", "upgrade"} & set(keywords):
        names.append("Firmware Upgrade Visibility")
    if "analytics" in keywords:
        names.append("Fault Event Analytics" if "fault" in keywords else "Operational Analytics")
    for module in profile["knowledge_registry"]["modules"]:
        if len(names) >= 6:
            break
        candidate = _feature_name_from_item(module)
        if candidate:
            names.append(candidate)
    for flow in profile["knowledge_registry"]["flows"]:
        if len(names) >= 6:
            break
        candidate = _feature_name_from_item(flow)
        if candidate:
            names.append(candidate)
    if not names:
        domain = profile.get("domain") or profile["knowledge_profile_preview"].get("domain") or "Project"
        names = [f"{domain} Workflow Visibility", f"{domain} Operational Controls", f"{domain} Readiness Dashboard"]
    return [{"title": name, "description": _feature_description(name, profile)} for name in _remove_generic_names(_unique(names))[:6]]


def _feature_name_from_item(item: str) -> str:
    cleaned = _clean_title(item)
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    if "auth" in lowered:
        return "Authentication Access Control"
    if "telemetry" in lowered:
        return "Telemetry Health Dashboard"
    if "firmware" in lowered:
        return "Firmware Upgrade Visibility"
    if "fault" in lowered or "outage" in lowered:
        return "Fault Event Monitoring"
    if "analytics" in lowered:
        return "Operational Analytics"
    if any(word in lowered for word in ["monitor", "health"]):
        return f"{cleaned} Visibility"
    return cleaned if any(word in lowered for word in ["dashboard", "monitoring", "visibility", "analytics"]) else f"{cleaned} Management"


def _feature_description(name: str, profile: dict[str, Any]) -> str:
    apps = _format_applications(profile["applications"]) or "the affected applications"
    return f"Deliver {name.lower()} across {apps} with traceable outcomes, dependencies, and validation coverage."


def _recommended_stories(feature_title: str, modules: list[str], flows: list[str], profile: dict[str, Any]) -> list[dict[str, str]]:
    stories: list[dict[str, str]] = []
    for flow in flows[:3]:
        title = f"{_clean_title(flow)} workflow for {feature_title}"
        stories.append(
            {
                "title": title,
                "description": f"As an operational user, I want {_clean_title(flow).lower()} support in {feature_title} so I can complete the workflow with confidence.",
            }
        )
    for module in modules[:3]:
        title = f"{feature_title} integration with {_clean_title(module)}"
        stories.append(
            {
                "title": title,
                "description": f"As a delivery team, I want {feature_title} connected to {_clean_title(module)} so the capability follows the project architecture.",
            }
        )
    if not stories:
        stories = [
            {
                "title": f"Configure {feature_title} operating rules",
                "description": f"As an administrator, I want configurable rules for {feature_title} so rollout can be governed safely.",
            },
            {
                "title": f"Validate {feature_title} user outcomes",
                "description": f"As a product owner, I want measurable outcomes for {feature_title} so release readiness is clear.",
            },
        ]
    return stories[:6]


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
    names = [app["name"] for app in profile["applications"]]
    return names or [app["name"] for app in profile["knowledge_registry"]["applications"]]


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
    criteria = [
        f"{title} behavior is visible and testable for the intended user.",
        "Errors, empty states, and permission boundaries are handled clearly.",
    ]
    criteria.extend(f"{flow} flow is covered end to end." for flow in flows[:3])
    criteria.extend(f"{module} integration is validated." for module in modules[:2])
    return _unique(criteria)


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


def _sentence(title: str, detail: str) -> str:
    detail = _clean_text(detail)
    if detail:
        return detail if detail.endswith(".") else f"{detail}."
    return f"{title}."


def _clean_title(value: str) -> str:
    return " ".join(word.capitalize() for word in _clean_text(value).replace("_", " ").replace("-", " ").split())


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
    project_profile = 25 if profile.get("project_description") else 0
    repository = 25 if profile["repository_connection"]["status"] == "README analyzed" else 0
    registry = 20 if (profile["knowledge_registry"]["modules"] or profile["knowledge_registry"]["flows"]) else 0
    impact = 15 if has_impact else 0
    standards = 15 if _flatten_standards(profile["development_standards"]) else 0
    score = project_profile + repository + registry + impact + standards
    if score >= 85:
        label = "Ready"
    elif score >= 65:
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
    prompt, context_diagnostics = _project_phi_prompt_with_diagnostics(operation, profile, item, deterministic, expected_keys)
    return _project_phi_probe(prompt, options, expected_keys=expected_keys, context_diagnostics=context_diagnostics)


def _project_phi_probe(
    prompt: str,
    options: dict[str, Any] | None,
    expected_keys: list[str] | None = None,
    context_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    options = options or {}
    force_provider = _clean_text(options.get("force_provider"))
    allow_fallback = bool(options.get("allow_fallback", True))
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
        return {
            "used": False,
            "blocked": False,
            "parsed": {},
            "metadata": _with_context_diagnostics(
                _fallback_metadata("domain_fallback", "AI_GEN_PROJECT_INTELLIGENCE_USE_PHI disabled Project Intelligence Phi calls."),
                context_diagnostics,
            ),
        }
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
    probe = provider.probe_json(
        "Return strict JSON only. Do not include markdown or explanations.",
        prompt,
        max_tokens=900,
        response_format_enabled=False,
        allow_retry_without_response_format=True,
    )
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
    metadata.update(
        {
            "provider_used": "domain_fallback" if allow_fallback else "azure_phi",
            "source": "domain_fallback" if allow_fallback else "azure_phi",
            "phi_status": probe.get("failure_reason") or probe.get("status") or "unusable_response",
            "fallback_used": allow_fallback,
            "fallback_reason": probe.get("failure_message") or probe.get("parse_error") or "Azure Phi returned unusable structured output.",
        }
    )
    return _fallback_or_block(metadata, force_provider, allow_fallback)


def _project_phi_enabled_by_default() -> bool:
    value = os.getenv("AI_GEN_PROJECT_INTELLIGENCE_USE_PHI")
    if value is None:
        return True
    return value.strip().lower() not in {"0", "false", "no", "off", "disabled"}


def _fallback_or_block(metadata: dict[str, Any], force_provider: str, allow_fallback: bool) -> dict[str, Any]:
    blocked = force_provider == "azure_phi" and not allow_fallback
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


def _project_phi_prompt_with_diagnostics(
    operation: str,
    profile: dict[str, Any],
    item: dict[str, Any],
    deterministic: dict[str, Any],
    expected_keys: list[str],
) -> tuple[str, dict[str, Any]]:
    project_context, diagnostics = _budgeted_project_context(operation, profile, item)
    return json.dumps(
        {
            "operation": operation,
            "expected_json_keys": expected_keys,
            "project_context": project_context,
            "input": item,
            "deterministic_draft": deterministic,
            "instruction": "Return only strict JSON. Improve specificity using the project context. Keep exactly the expected keys where possible.",
        },
        ensure_ascii=True,
    ), diagnostics


def _budgeted_project_context(operation: str, profile: dict[str, Any], item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    budget_tokens = _context_budget_tokens()
    raw_context = _project_summary_context(operation, profile, item, compression_level=0)
    raw_tokens = _estimate_tokens(json.dumps(raw_context, ensure_ascii=True))
    compressed_context = raw_context
    compression_level = 0
    compressed_tokens = raw_tokens
    for level in [0, 1, 2, 3]:
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


def _project_summary_context(operation: str, profile: dict[str, Any], item: dict[str, Any], compression_level: int) -> dict[str, Any]:
    registry = _normalize_knowledge_registry(profile.get("knowledge_registry", {}))
    selected = _select_semantic_registry_context(operation, item, profile, registry, compression_level)
    description_limits = [900, 650, 420, 260]
    architecture_limits = [650, 450, 280, 180]
    standards_limits = [8, 6, 4, 3]
    source_limits = [8, 5, 3, 0]
    return {
        "project_name": profile.get("project_name"),
        "domain": profile.get("domain"),
        "project_type": profile.get("project_type"),
        "description": _truncate_text(profile.get("project_description"), description_limits[min(compression_level, 3)]),
        "project_summary": {
            "applications": profile.get("applications") or registry.get("applications"),
            "top_modules": selected["modules"],
            "top_flows": selected["flows"],
            "architecture_summary": _truncate_text(_architecture_summary_text(profile, registry), architecture_limits[min(compression_level, 3)]),
        },
        "technology_stack": _compact_stack(profile),
        "development_standards": _compact_development_standards(profile.get("development_standards", {}), registry),
        "ui_guidelines": _compact_ui_guidelines(profile.get("ui_guidelines", {}), registry),
        "knowledge_registry": {
            "modules": selected["modules"],
            "module_details": selected["module_details"],
            "flows": selected["flows"],
            "flow_details": selected["flow_details"],
            "components": selected["components"],
            "component_details": selected["component_details"],
            "architecture_summary": _truncate_text(_architecture_summary_text(profile, registry), architecture_limits[min(compression_level, 3)]),
            "standards": registry["standards"][: standards_limits[min(compression_level, 3)]],
            "source_files": registry["source_files"][: source_limits[min(compression_level, 3)]],
        },
    }


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
    reductions = [1.0, 0.7, 0.45, 0.28]
    factor = reductions[min(compression_level, 3)]
    return {key: max(1, int(value * factor)) for key, value in base.items()}


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
        "phi_status": probe.get("status") or probe.get("failure_reason") or "unknown",
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


def _with_context_diagnostics(metadata: dict[str, Any], diagnostics: dict[str, Any] | None) -> dict[str, Any]:
    if diagnostics:
        metadata.update(diagnostics)
    return metadata


def _with_provider_metadata(payload: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    return {**payload, **metadata}


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
    files: list[str] = []
    modules = impact["affected_modules"]
    flows = impact["affected_flows"]
    components = impact["affected_components"]
    story_slug = _file_slug(story_title)
    lowered_story = story_title.lower()
    if any(app["type"] == "Mobile" for app in profile["applications"]):
        if "fault" in lowered_story and "detail" in lowered_story:
            files.extend(["Mobile/FaultEventViewModel.cs", "Mobile/FaultEventDetailsPage.xaml"])
        files.extend(_file_guess("mobile", components or flows or modules or [story_slug]))
    if any(app["type"] in ["Backend", "API"] for app in profile["applications"]):
        if "fault" in lowered_story:
            files.extend(["Backend/FaultEventController.cs", "Backend/FaultEventRepository.cs"])
        files.extend(_file_guess("backend", modules or flows or [story_slug]))
    if any(app["type"] == "Web Portal" for app in profile["applications"]):
        files.extend(_file_guess("web", components or flows))
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


def _acceptance_criteria_mapping(acceptance: list[str], implementation_tasks: list[str]) -> list[dict[str, str]]:
    if not acceptance:
        return []
    fallback_task = implementation_tasks[0] if implementation_tasks else "Implement approved behavior"
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
