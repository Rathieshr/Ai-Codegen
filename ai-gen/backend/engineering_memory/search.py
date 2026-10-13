"""Engineering Memory search."""

from __future__ import annotations

from typing import Any

from .types import clean, string_list


class MemorySearch:
    def search(self, memories: list[dict[str, Any]], query: dict[str, Any]) -> dict[str, Any]:
        terms = {item.lower() for item in string_list(query.get("query"))}
        expanded_terms: set[str] = set()
        for term in terms:
            expanded_terms.update(term.split())
        terms.update(expanded_terms)
        terms.update(str(query.get("text") or "").lower().split())
        tags = {item.lower() for item in string_list(query.get("tags"))}
        category = clean(query.get("category"))
        artifact_type = clean(query.get("artifactType") or query.get("artifact_type"))
        artifact_id = clean(query.get("artifactId") or query.get("artifact_id"))
        module = {item.lower() for item in string_list(query.get("module") or query.get("modules"))}
        flow = {item.lower() for item in string_list(query.get("flow") or query.get("flows"))}
        repository = {item.lower() for item in string_list(query.get("repository"))}
        decision = bool(query.get("decision"))
        architecture = bool(query.get("architecture"))
        results = []
        for memory in memories:
            if memory.get("approvalStatus") not in {"Indexed", "Available", "Approved"} and not query.get("includeDrafts"):
                continue
            score, reasons = self._score(memory, terms, tags, category, artifact_type, artifact_id, module, flow, repository, decision, architecture)
            if score > 0 or not any([terms, tags, category, artifact_type, artifact_id, module, flow, repository, decision, architecture]):
                results.append({**memory, "searchScore": score, "matchReasons": reasons})
        results.sort(key=lambda item: (item.get("searchScore", 0), item.get("confidence", 0)), reverse=True)
        limit = int(query.get("limit") or 20)
        return {"results": results[:limit], "count": len(results)}

    def _score(
        self,
        memory: dict[str, Any],
        terms: set[str],
        tags: set[str],
        category: str,
        artifact_type: str,
        artifact_id: str,
        module: set[str],
        flow: set[str],
        repository: set[str],
        decision: bool,
        architecture: bool,
    ) -> tuple[int, list[str]]:
        index = memory.get("index") if isinstance(memory.get("index"), dict) else {}
        tokens = {str(item).lower() for item in index.get("tokens", [])}
        memory_tags = {str(item).lower() for item in index.get("tags", [])}
        score = 0
        reasons: list[str] = []
        if category and clean(memory.get("category")).lower() == category.lower():
            score += 8
            reasons.append("category")
        if artifact_type and clean(memory.get("artifactType")).lower() == artifact_type.lower():
            score += 6
            reasons.append("artifact_type")
        if artifact_id and clean(memory.get("artifactId")) == artifact_id:
            score += 10
            reasons.append("artifact_id")
        overlap = terms & tokens
        if overlap:
            score += len(overlap) * 2
            reasons.append("keyword")
        tag_overlap = tags & memory_tags
        if tag_overlap:
            score += len(tag_overlap) * 3
            reasons.append("tag")
        if module & {str(item).lower() for item in index.get("modules", [])}:
            score += 6
            reasons.append("module")
        if flow & {str(item).lower() for item in index.get("flows", [])}:
            score += 6
            reasons.append("flow")
        if repository & {str(item).lower() for item in index.get("repository", [])}:
            score += 5
            reasons.append("repository")
        if decision and index.get("decision"):
            score += 6
            reasons.append("decision")
        if architecture and index.get("architecture"):
            score += 6
            reasons.append("architecture")
        return score, reasons
