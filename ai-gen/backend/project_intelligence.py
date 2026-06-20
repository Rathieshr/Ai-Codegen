"""Phase 2 Project Intelligence preview profile service."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.refinement.provider import get_refiner_status, get_refinement_provider


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
        "flows": [],
        "components": [],
        "architecture_notes": [],
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
        return _with_provider_metadata(_normalize_profile(profile), _fallback_metadata("domain_fallback", "description analysis uses deterministic project-domain inference."))

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
            "development_standards": _merge_development_standards(active_profile["development_standards"], analysis["development_standards"]),
            "ui_guidelines": {
                **active_profile["ui_guidelines"],
                "accessibility_rules": _unique([*active_profile["ui_guidelines"]["accessibility_rules"], *analysis["ui_standards"]]),
            },
            "repository_sources": _unique([*active_profile["repository_sources"], *analysis["source_files"]]),
            "knowledge_profile_preview": {
                **active_profile["knowledge_profile_preview"],
                "systems": [app["name"] for app in _merge_applications(active_profile["applications"], analysis["detected_applications"])],
                "standards": _unique([*active_profile["knowledge_profile_preview"]["standards"], *analysis["ui_standards"], *analysis["development_standards"]]),
                "repository_status": "Repository documents analyzed" if documents else "Repository documents not found",
                "readiness": _readiness({**active_profile, "knowledge_registry": registry}),
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
        return _with_provider_metadata({
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
        }, _fallback_metadata("domain_fallback", "execution context combines deterministic impact and project profile context."))

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
        return _with_provider_metadata(deterministic, _fallback_metadata("domain_fallback", "UI prompt uses deterministic project UI context."))

    def build_qa_prompt(
        self,
        story: dict[str, Any],
        profile: dict[str, Any] | None = None,
        knowledge_profile: dict[str, Any] | None = None,
        impact_analysis: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        context = self.build_execution_context(story, profile, knowledge_profile, impact_analysis, options)
        impact = _normalize_story_impact(impact_analysis or self.analyze_story_impact(story, _normalize_profile(profile or self.get_profile()), knowledge_profile or {}))
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
        return _with_provider_metadata(deterministic, _fallback_metadata("domain_fallback", "QA prompt uses deterministic risk and dependency context."))

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
    return {
        "applications": _normalize_applications(registry.get("applications")),
        "modules": _string_list(registry.get("modules")),
        "flows": _string_list(registry.get("flows")),
        "components": _string_list(registry.get("components")),
        "architecture_notes": _string_list(registry.get("architecture_notes")),
        "standards": _string_list(registry.get("standards")),
        "source_files": _string_list(registry.get("source_files")),
    }


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
    if any(word in lowered for word in ["ios", "android", "mobile"]):
        apps.append({"name": "Mobile App", "type": "Mobile"})
    if any(word in lowered for word in ["backend", "api", "service"]):
        apps.append({"name": "Backend", "type": "Backend"})
    if "firmware" in lowered:
        apps.append({"name": "Firmware", "type": "Firmware"})
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
        "Swift": ["swift", "ios"],
        "Kotlin": ["kotlin", "android"],
        ".NET": [".net", "dotnet"],
        "MAUI": ["maui"],
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
    if any(word in lowered for word in ["meter", "energy", "utility"]):
        return "Utilities"
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
    has_description = bool(_clean_text(profile.get("project_description")))
    has_apps = bool(_normalize_applications(profile.get("applications")))
    stack = _normalize_stack(profile.get("technology_stack"))
    has_stack = any(stack.values())
    registry = _normalize_knowledge_registry(profile.get("knowledge_registry"))
    standards = profile.get("development_standards") if isinstance(profile.get("development_standards"), dict) else {}
    has_standards = bool(_flatten_standards(standards))
    if has_description and has_apps and has_stack and (has_standards or registry["modules"] or registry["flows"]):
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
    if any(word in lowered for word in ["fastapi", "python", "node", ".net", "dotnet"]):
        return "backend"
    if any(word in lowered for word in ["c++", "firmware"]):
        return "firmware"
    if any(word in lowered for word in ["analytics", "spark", "power bi", "dashboard"]):
        return "analytics"
    return "frontend"


def _analyze_readme_content(readme_content: str) -> dict[str, Any]:
    text = readme_content.strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    summary = _extract_summary(lines)
    modules = _extract_section_items(lines, ["modules", "packages", "services", "components"])
    flows = _extract_section_items(lines, ["flows", "features", "workflows", "user journeys"])
    architecture_notes = _extract_architecture_notes(lines)
    applications = _extract_applications_from_readme(text)
    components = _extract_section_items(lines, ["components", "screens", "pages"])
    return {
        "summary": summary,
        "applications": applications,
        "modules": modules,
        "flows": flows,
        "architecture_notes": architecture_notes,
        "components": components,
        "standards": [],
        "source_files": [],
    }


def _analyze_repository_documents(documents: dict[str, str]) -> dict[str, Any]:
    readme_summary = ""
    architecture_notes: list[str] = []
    detected_applications: list[dict[str, str]] = []
    detected_modules: list[str] = []
    detected_flows: list[str] = []
    detected_components: list[str] = []
    ui_standards: list[str] = []
    development_standards: list[str] = []
    warnings: list[str] = []
    source_files: list[str] = []

    for path, content in documents.items():
        lowered_path = path.lower()
        source_files.append(path)
        parsed = _analyze_readme_content(content)
        if "readme" in lowered_path and not readme_summary:
            readme_summary = parsed["summary"]
        if "architecture" in lowered_path:
            architecture_notes.extend(_extract_document_items(content, ["architecture", "notes", "decisions", "patterns"]) or parsed["architecture_notes"])
            detected_components.extend(_extract_document_items(content, ["components", "services", "systems"]))
            detected_applications = _merge_applications(detected_applications, _extract_applications_from_readme(content))
        elif "modules" in lowered_path:
            detected_modules.extend(_extract_document_items(content, ["modules", "services", "packages", "domains"]) or parsed["modules"])
            detected_components.extend(_extract_document_items(content, ["components", "classes", "screens"]))
        elif "flows" in lowered_path:
            detected_flows.extend(_extract_document_items(content, ["flows", "workflows", "journeys", "scenarios"]) or parsed["flows"])
        elif "ui-guidelines" in lowered_path:
            ui_standards.extend(_extract_document_items(content, ["ui guidelines", "accessibility", "components", "design rules"]) or _extract_bullets(content))
        elif "coding-standards" in lowered_path:
            development_standards.extend(_extract_document_items(content, ["coding standards", "security", "testing", "architecture"]) or _extract_bullets(content))
        else:
            detected_applications = _merge_applications(detected_applications, parsed["applications"])
            detected_modules.extend(parsed["modules"])
            detected_flows.extend(parsed["flows"])
            detected_components.extend(parsed["components"])
            architecture_notes.extend(parsed["architecture_notes"])

    if not documents:
        warnings.append("No repository documents were available for analysis.")

    architecture_summary = ". ".join(_unique(architecture_notes)[:3])
    return {
        "readme_summary": readme_summary,
        "architecture_summary": architecture_summary,
        "architecture_notes": _unique(architecture_notes),
        "detected_applications": detected_applications,
        "detected_modules": _unique(detected_modules),
        "detected_flows": _unique(detected_flows),
        "detected_components": _unique(detected_components),
        "ui_standards": _unique(ui_standards),
        "development_standards": _unique(development_standards),
        "source_files": _unique(source_files),
        "warnings": warnings,
        "applications": detected_applications,
        "modules": _unique(detected_modules),
        "flows": _unique(detected_flows),
        "components": _unique(detected_components),
        "standards": _unique([*ui_standards, *development_standards]),
    }


def _extract_document_items(content: str, sections: list[str]) -> list[str]:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    section_items = _extract_section_items(lines, sections)
    labelled_items = _extract_labelled_items(lines, sections)
    return _unique([*section_items, *labelled_items]) or _extract_bullets(content)


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


def _extract_bullets(content: str) -> list[str]:
    items: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(("-", "*")):
            items.append(stripped.lstrip("-* ").split(":", 1)[0].strip())
    return _unique(items)


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


def _extract_applications_from_readme(text: str) -> list[dict[str, str]]:
    inferred = _infer_applications(text)
    return [] if inferred == [{"name": "Application", "type": "API"}] else inferred


def _merge_knowledge_registry(existing: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_knowledge_registry(existing)
    return {
        "applications": _merge_applications(normalized["applications"], analysis.get("applications", [])),
        "modules": _unique([*normalized["modules"], *_string_list(analysis.get("modules"))]),
        "flows": _unique([*normalized["flows"], *_string_list(analysis.get("flows"))]),
        "components": _unique([*normalized["components"], *_string_list(analysis.get("components"))]),
        "architecture_notes": _unique([*normalized["architecture_notes"], *_string_list(analysis.get("architecture_notes"))]),
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
    prompt = _project_phi_prompt(operation, profile, item, deterministic, expected_keys)
    return _project_phi_probe(prompt, options, expected_keys=expected_keys)


def _project_phi_probe(prompt: str, options: dict[str, Any] | None, expected_keys: list[str] | None = None) -> dict[str, Any]:
    options = options or {}
    force_provider = _clean_text(options.get("force_provider"))
    allow_fallback = bool(options.get("allow_fallback", True))
    deterministic_only = _clean_text(options.get("mode")) == "deterministic_only" or force_provider == "deterministic_fallback"
    if deterministic_only:
        return {
            "used": False,
            "blocked": False,
            "parsed": {},
            "metadata": _fallback_metadata("deterministic_fallback", "deterministic_only mode selected."),
        }
    if force_provider == "domain_fallback":
        return {
            "used": False,
            "blocked": False,
            "parsed": {},
            "metadata": _fallback_metadata("domain_fallback", "domain_fallback provider was forced."),
        }
    use_phi = force_provider == "azure_phi" or os.getenv("AI_GEN_PROJECT_INTELLIGENCE_USE_PHI") == "1"
    if not use_phi:
        return {
            "used": False,
            "blocked": False,
            "parsed": {},
            "metadata": _fallback_metadata("domain_fallback", "AI_GEN_PROJECT_INTELLIGENCE_USE_PHI is not enabled."),
        }
    provider = get_refinement_provider()
    if provider is None or not provider.is_enabled():
        metadata = _fallback_metadata("deterministic_fallback", "Azure Phi provider is not configured.")
        metadata["phi_status"] = "not_configured"
        return _fallback_or_block(metadata, force_provider, allow_fallback)
    health = provider.health_snapshot() if hasattr(provider, "health_snapshot") else {}
    if force_provider != "azure_phi" and health.get("health") != "healthy":
        metadata = _fallback_metadata("domain_fallback", f"Azure Phi health is {health.get('health') or 'unknown'}.")
        metadata.update(_provider_status_metadata(provider, {}, health))
        metadata["provider_used"] = "domain_fallback"
        metadata["source"] = "domain_fallback"
        metadata["fallback_used"] = True
        metadata["fallback_reason"] = f"Azure Phi health is {health.get('health') or 'unknown'}."
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
    metadata = _provider_status_metadata(provider, probe, health)
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
    return json.dumps(
        {
            "operation": operation,
            "expected_json_keys": expected_keys,
            "project_context": {
                "project_name": profile.get("project_name"),
                "domain": profile.get("domain"),
                "project_type": profile.get("project_type"),
                "description": profile.get("project_description"),
                "applications": profile.get("applications"),
                "technology_stack": profile.get("technology_stack"),
                "development_standards": profile.get("development_standards"),
                "ui_guidelines": profile.get("ui_guidelines"),
                "knowledge_registry": profile.get("knowledge_registry"),
                "architecture_notes": profile.get("readme_analysis", {}).get("architecture_notes", []),
            },
            "input": item,
            "deterministic_draft": deterministic,
            "instruction": "Return only strict JSON. Improve specificity using the project context. Keep exactly the expected keys where possible.",
        },
        ensure_ascii=True,
    )


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


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


project_intelligence_service = ProjectIntelligenceService()
