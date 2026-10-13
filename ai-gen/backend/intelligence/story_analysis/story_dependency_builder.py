from __future__ import annotations

from typing import Any

from .story_analysis import Dependency


def buildStoryDependencies(feature_dna: dict[str, Any], evidence_names: list[str]) -> list[Dependency]:
    dependencies = [
        Dependency(name=value, reason="Inherited from approved Feature DNA.", confidence=0.84)
        for value in _string_list(feature_dna.get("dependencies"))
    ]
    if not dependencies and evidence_names:
        dependencies = [
            Dependency(name=value, reason="Required repository capability for the journey.", confidence=0.68)
            for value in evidence_names[:3]
        ]
    return dependencies[:6]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [" ".join(str(item).split()) for item in value if " ".join(str(item).split())]
    text = " ".join(str(value).split())
    return [text] if text else []

