from __future__ import annotations

from typing import Any

from .story_analysis import RepositoryEvidence


def collectStoryRepositoryEvidence(feature_dna: dict[str, Any], profile: dict[str, Any] | None = None) -> list[RepositoryEvidence]:
    profile = profile or {}
    evidence = feature_dna.get("repositoryEvidence") if isinstance(feature_dna.get("repositoryEvidence"), dict) else {}
    items: list[RepositoryEvidence] = []
    for key, item_type in (
        ("modules", "Module"),
        ("flows", "Flow"),
        ("services", "Service"),
        ("files", "File"),
        ("applications", "Application"),
    ):
        for value in _string_list(evidence.get(key)):
            items.append(
                RepositoryEvidence(
                    name=value,
                    type=item_type,
                    confidence=0.86 if key in {"modules", "flows"} else 0.74,
                    reason=f"Selected by Feature DNA {key}.",
                    source="feature_dna",
                )
            )
    registry = profile.get("knowledge_registry") if isinstance(profile.get("knowledge_registry"), dict) else {}
    if not items:
        for value in _string_list(registry.get("modules"))[:3]:
            items.append(RepositoryEvidence(name=value, type="Module", confidence=0.62, reason="Fallback from Knowledge Registry.", source="knowledge_registry"))
        for value in _string_list(registry.get("flows"))[:3]:
            items.append(RepositoryEvidence(name=value, type="Flow", confidence=0.62, reason="Fallback from Knowledge Registry.", source="knowledge_registry"))
    return _dedupe_evidence(items)


def _dedupe_evidence(items: list[RepositoryEvidence]) -> list[RepositoryEvidence]:
    seen: set[tuple[str, str]] = set()
    result: list[RepositoryEvidence] = []
    for item in items:
        key = (item.type.lower(), item.name.lower())
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [" ".join(str(item).split()) for item in value if " ".join(str(item).split())]
    text = " ".join(str(value).split())
    return [text] if text else []

