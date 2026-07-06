from __future__ import annotations

from typing import Any

from .capability_rules import CAPABILITY_RULES


def apply_repository_scores(candidates: list[dict[str, Any]], repository_snapshot: dict[str, Any], knowledge_registry: dict[str, Any]) -> None:
    repository_text = _repository_text(repository_snapshot, knowledge_registry)
    repository_modules = _registry_items(repository_snapshot, knowledge_registry, "modules")
    repository_flows = _registry_items(repository_snapshot, knowledge_registry, "flows")
    for candidate in candidates:
        rules = CAPABILITY_RULES.get(str(candidate.get("name") or ""), {})
        module_hits = [module for module in _list(rules.get("modules")) if _contains(module, repository_modules, repository_text)]
        flow_hits = [flow for flow in _list(rules.get("flows")) if _contains(flow, repository_flows, repository_text)]
        keyword_hits = [keyword for keyword in _list(rules.get("keywords")) if keyword.lower() in repository_text]
        candidate["repository_score"] = min(100, 25 + len(module_hits) * 20 + len(flow_hits) * 18 + len(keyword_hits) * 8) if repository_text else 0
        candidate["repository_evidence"] = _unique([*module_hits, *flow_hits, *keyword_hits])[:6]


def _repository_text(repository_snapshot: dict[str, Any], knowledge_registry: dict[str, Any]) -> str:
    parts: list[str] = []
    if isinstance(repository_snapshot, dict):
        for key in ["summary", "architecture_summary", "readme_summary", "architectureNotes", "architecture_notes"]:
            value = repository_snapshot.get(key)
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts.extend(str(item) for item in value if item)
        for key in ["applications", "modules", "flows", "components"]:
            value = repository_snapshot.get(key)
            if isinstance(value, list):
                parts.extend(str(item) for item in value if item)
        if isinstance(repository_snapshot.get("knowledge_registry"), dict):
            registry = repository_snapshot["knowledge_registry"]
            for key in ["modules", "flows", "components", "applications"]:
                if isinstance(registry.get(key), list):
                    parts.extend(str(item) for item in registry.get(key, []) if item)
    if isinstance(knowledge_registry, dict):
        for key in ["modules", "flows", "components", "applications"]:
            if isinstance(knowledge_registry.get(key), list):
                parts.extend(str(item) for item in knowledge_registry.get(key, []) if item)
    return " ".join(" ".join(str(item).strip().split()) for item in parts if str(item).strip()).lower()


def _registry_items(repository_snapshot: dict[str, Any], knowledge_registry: dict[str, Any], key: str) -> list[str]:
    values: list[str] = []
    if isinstance(repository_snapshot.get(key), list):
        values.extend(str(item) for item in repository_snapshot.get(key, []) if item)
    if isinstance(repository_snapshot.get("knowledge_registry"), dict) and isinstance(repository_snapshot["knowledge_registry"].get(key), list):
        values.extend(str(item) for item in repository_snapshot["knowledge_registry"].get(key, []) if item)
    if isinstance(knowledge_registry.get(key), list):
        values.extend(str(item) for item in knowledge_registry.get(key, []) if item)
    return _unique(values)


def _contains(value: str, items: list[str], repository_text: str) -> bool:
    lowered = value.lower()
    return lowered in repository_text or any(lowered in item.lower() or item.lower() in lowered for item in items)


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = " ".join(str(value).strip().split())
        key = cleaned.lower()
        if cleaned and key not in seen:
            output.append(cleaned)
            seen.add(key)
    return output
