"""Build searchable Engineering Memory indexes."""

from __future__ import annotations

import re
from typing import Any

from .types import clean, string_list, unique


class MemoryIndexer:
    def index(self, memory: dict[str, Any]) -> dict[str, Any]:
        text = " ".join(
            [
                clean(memory.get("title")),
                clean(memory.get("summary")),
                clean(memory.get("content")),
                " ".join(string_list(memory.get("tags"))),
                " ".join(string_list(memory.get("knowledgeReferences"))),
                " ".join(string_list(memory.get("graphReferences"))),
            ]
        )
        tokens = unique([token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9_/-]{2,}", text)])
        modules = _evidence_names(memory.get("repositoryEvidence"), {"module", "service", "component"})
        flows = [token for token in tokens if "flow" in token]
        memory["index"] = {
            "tokens": tokens,
            "tags": string_list(memory.get("tags")),
            "modules": modules,
            "flows": unique(flows),
            "artifact": [clean(memory.get("artifactType")), clean(memory.get("artifactId"))],
            "repository": _evidence_names(memory.get("repositoryEvidence"), {"file", "repository", "api", "service"}),
            "decision": "decision" in clean(memory.get("category")).lower() or "decision" in text.lower(),
            "architecture": "architecture" in clean(memory.get("category")).lower() or "architecture" in text.lower(),
        }
        return memory


def _evidence_names(values: Any, allowed_types: set[str]) -> list[str]:
    output: list[str] = []
    if not isinstance(values, list):
        return output
    for item in values:
        if isinstance(item, dict):
            item_type = clean(item.get("type")).lower()
            if not item_type or item_type in allowed_types:
                output.append(clean(item.get("name") or item.get("path") or item.get("id")))
        else:
            output.append(clean(item))
    return unique(output)
