"""Read-only adapter for the legacy Project Intelligence fact stores."""

from __future__ import annotations

import json
import re
from typing import Any


class ProjectIntelligenceProvider:
    """Projects approved project knowledge into a bounded evidence payload.

    Project Intelligence contains both fact stores and legacy orchestration.
    This adapter intentionally calls only its read APIs.
    """

    def __init__(self, service: Any) -> None:
        self._service = service

    def build_context(self, requirement: dict[str, Any]) -> dict[str, Any]:
        profile = self._service.get_profile() or {}
        cache_result = self._service.get_knowledge_cache() or {}
        cache = cache_result.get("cache") if isinstance(cache_result.get("cache"), dict) else {}
        required_project = _text(requirement.get("projectId"))
        known_project = _text(cache.get("project_id") or profile.get("project_id"))
        if required_project and known_project and required_project != known_project:
            return _empty_context(
                f"Project Intelligence belongs to project {known_project}, not {required_project}."
            )

        registry = (
            cache.get("knowledge_registry")
            if isinstance(cache.get("knowledge_registry"), dict)
            else profile.get("knowledge_registry")
            if isinstance(profile.get("knowledge_registry"), dict)
            else {}
        )
        query = _requirement_text(requirement)
        selected = {
            "modules": _select(registry.get("module_details"), registry.get("modules"), query),
            "flows": _select(registry.get("flow_details"), registry.get("flows"), query),
            "applications": _select(None, registry.get("applications"), query),
            "components": _select(registry.get("component_details"), registry.get("components"), query),
            "standards": _select(None, registry.get("standards"), query),
        }
        selected_names = {
            category: [_item_name(item) for item in items]
            for category, items in selected.items()
        }
        source_files = _select_paths(cache.get("source_files") or registry.get("source_files"), query)
        approved_artifacts, rejected_artifacts = self._approved_artifacts(query)
        rejected_context = [
            {
                "name": _item_name(item),
                "type": category[:-1].title(),
                "reason": "No intent overlap with the current requirement.",
                "source": "Project Intelligence Knowledge Registry",
            }
            for category, values in {
                "modules": registry.get("modules"),
                "flows": registry.get("flows"),
                "applications": registry.get("applications"),
                "components": registry.get("components"),
            }.items()
            for item in _items(values)
            if _item_name(item) and _item_name(item) not in selected_names[category]
        ][:30]
        rejected_context.extend(rejected_artifacts[:20])

        return {
            "available": bool(cache_result.get("exists") or profile.get("onboarding_completed")),
            "project": {
                "projectId": known_project,
                "projectName": _text(cache.get("project_name") or profile.get("project_name")),
                "domain": _text(profile.get("domain")),
                "projectType": _text(profile.get("project_type")),
                "description": _text(profile.get("project_description")),
                "role": "Background",
            },
            "knowledge": {
                "version": _text(cache.get("knowledge_version")),
                "schemaVersion": _text(cache.get("schema_version")),
                "status": _text(cache_result.get("status")) or (
                    "available" if cache_result.get("exists") else "missing"
                ),
                "lastAnalyzedAt": _text(cache.get("last_analyzed_at")),
                **selected_names,
                "architectureNotes": _select_strings(
                    registry.get("architecture_notes"), query
                ),
                "sourceFiles": source_files,
                "source": "Project Intelligence Knowledge Registry",
            },
            "approvedArtifacts": approved_artifacts,
            "rejectedContext": rejected_context,
            "diagnostics": {
                "selectionRule": "intent_keyword_overlap",
                "broadProjectContextIncluded": False,
                "legacyGenerationUsed": False,
            },
        }

    def _approved_artifacts(
        self, query: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        result = self._service.list_artifacts() or {}
        approved: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for artifact in result.get("artifacts") or []:
            state = _text(artifact.get("state")).casefold()
            title = _text(artifact.get("title"))
            if state not in {"approved", "locked"}:
                rejected.append({
                    "name": title or _text(artifact.get("artifact_id")),
                    "type": _text(artifact.get("artifact_type")) or "Artifact",
                    "reason": f"Artifact state {state or 'unknown'} is not approved.",
                    "source": "Project Intelligence Artifact Store",
                })
                continue
            score = _overlap(query, " ".join([
                title,
                _text(artifact.get("artifact_type")),
                json.dumps(artifact.get("payload") or {}, default=str),
            ]))
            if score <= 0:
                rejected.append({
                    "name": title or _text(artifact.get("artifact_id")),
                    "type": _text(artifact.get("artifact_type")) or "Artifact",
                    "reason": "Approved artifact is unrelated to the current requirement.",
                    "source": "Project Intelligence Artifact Store",
                })
                continue
            approved.append({
                "id": _text(artifact.get("artifact_id")),
                "title": title,
                "artifactType": _text(artifact.get("artifact_type")),
                "state": state,
                "version": artifact.get("version"),
                "confidence": min(95, 65 + score * 10),
                "reason": "Approved historical artifact matches the current requirement intent.",
                "evidence": [_text(artifact.get("fingerprint"))],
                "source": "Project Intelligence Artifact Store",
            })
        return approved[:20], rejected


def _empty_context(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "project": {"role": "Background"},
        "knowledge": {
            "version": "",
            "modules": [],
            "flows": [],
            "applications": [],
            "components": [],
            "standards": [],
            "architectureNotes": [],
            "sourceFiles": [],
            "source": "Project Intelligence Knowledge Registry",
        },
        "approvedArtifacts": [],
        "rejectedContext": [{
            "name": "Project Intelligence",
            "type": "ProjectContext",
            "reason": reason,
            "source": "Project Intelligence",
        }],
        "diagnostics": {
            "selectionRule": "project_scope_guard",
            "broadProjectContextIncluded": False,
            "legacyGenerationUsed": False,
        },
    }


def _select(details: Any, names: Any, query: str) -> list[Any]:
    candidates = _items(details) or _items(names)
    ranked = [
        (_overlap(query, _search_text(item)), _item_name(item), item)
        for item in candidates
        if _item_name(item)
    ]
    ranked = [item for item in ranked if item[0] > 0]
    ranked.sort(key=lambda item: (-item[0], item[1].casefold()))
    return [item[2] for item in ranked[:12]]


def _select_strings(values: Any, query: str) -> list[str]:
    ranked = [
        (_overlap(query, _text(value)), _text(value))
        for value in values or []
        if _text(value)
    ]
    ranked = [item for item in ranked if item[0] > 0]
    ranked.sort(key=lambda item: (-item[0], item[1].casefold()))
    return [item[1] for item in ranked[:12]]


def _select_paths(values: Any, query: str) -> list[dict[str, Any]]:
    ranked = [
        (_overlap(query, _text(path)), _text(path))
        for path in values or []
        if _text(path)
    ]
    ranked = [item for item in ranked if item[0] > 0]
    ranked.sort(key=lambda item: (-item[0], item[1].casefold()))
    return [{
        "path": path,
        "confidence": min(90, 60 + score * 10),
        "reason": "Document path matches the current requirement intent.",
        "evidence": [path],
        "source": "Project Intelligence Knowledge Cache",
    } for score, path in ranked[:8]]


def _items(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _item_name(value: Any) -> str:
    if isinstance(value, dict):
        return _text(value.get("name") or value.get("title") or value.get("id"))
    return _text(value)


def _search_text(value: Any) -> str:
    return json.dumps(value, default=str) if isinstance(value, dict) else _text(value)


def _requirement_text(requirement: dict[str, Any]) -> str:
    return " ".join([
        _text(requirement.get("title")),
        _text(requirement.get("planningRequirement")),
        *[_text(item) for key in (
            "businessGoals", "functionalRequirements", "acceptanceCriteria",
            "businessRules", "dependencies", "risks", "constraints",
        ) for item in requirement.get(key) or []],
    ])


def _overlap(left: str, right: str) -> int:
    return len(_tokens(left) & _tokens(right))


def _tokens(value: str) -> set[str]:
    ignored = {
        "about", "after", "before", "build", "create", "current", "from",
        "into", "project", "requirement", "should", "that", "their", "this",
        "through", "user", "users", "with",
    }
    return {
        token for token in re.findall(r"[a-z0-9]+", value.casefold())
        if len(token) > 2 and token not in ignored
    }


def _text(value: Any) -> str:
    return str(value or "").strip()
