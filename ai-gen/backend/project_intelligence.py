"""Phase 2 Project Intelligence preview profile service."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_PROFILE: dict[str, Any] = {
    "onboarding_completed": False,
    "project_name": "",
    "domain": "",
    "project_type": "",
    "project_description": "",
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

    def analyze_description(self, description: str) -> dict[str, Any]:
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
        return _normalize_profile(profile)

    def generate_story_prompts(self, story: dict[str, Any] | None = None, profile: dict[str, Any] | None = None) -> dict[str, str]:
        active_profile = _normalize_profile(profile or self.get_profile())
        story = story or {}
        title = _clean_text(story.get("title")) or "Approved story"
        description = _clean_text(story.get("description")) or "Implement the approved behavior."
        acceptance = _string_list(story.get("acceptance_criteria"))
        context_lines = _profile_context_lines(active_profile)
        acceptance_lines = acceptance or ["Confirm the implementation satisfies the approved story scope."]
        return {
            "ui_prompt": _prompt(
                "UI Prompt",
                title,
                description,
                context_lines,
                [
                    "Design the screen, states, validations, and accessibility behavior.",
                    "Apply the configured UI guidelines and component library where available.",
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
                    *[f"Acceptance: {item}" for item in acceptance_lines],
                ],
            ),
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
        f"Repository Sources: {', '.join(profile['repository_sources']) or 'Repository README scan coming next.'}",
    ]
    return lines


def _readiness(profile: dict[str, Any]) -> str:
    has_description = bool(_clean_text(profile.get("project_description")))
    has_apps = bool(_normalize_applications(profile.get("applications")))
    stack = _normalize_stack(profile.get("technology_stack"))
    has_stack = any(stack.values())
    standards = profile.get("development_standards") if isinstance(profile.get("development_standards"), dict) else {}
    has_standards = bool(_flatten_standards(standards))
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
    if any(word in lowered for word in ["fastapi", "python", "node", ".net", "dotnet"]):
        return "backend"
    if any(word in lowered for word in ["c++", "firmware"]):
        return "firmware"
    if any(word in lowered for word in ["analytics", "spark", "power bi", "dashboard"]):
        return "analytics"
    return "frontend"


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
