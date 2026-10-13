"""Trace search."""

from __future__ import annotations

from typing import Any

from .types import clean, string_list


class TraceSearch:
    def search(self, traces: list[dict[str, Any]], query: dict[str, Any]) -> dict[str, Any]:
        terms = {term.lower() for term in string_list(query.get("query") or query.get("text"))}
        expanded: set[str] = set()
        for term in terms:
            expanded.update(term.split())
        terms.update(expanded)
        artifact_id = clean(query.get("artifactId") or query.get("artifact_id"))
        artifact_type = clean(query.get("artifactType") or query.get("artifact_type"))
        project_id = clean(query.get("projectId") or query.get("project_id"))
        module_terms = {term.lower() for term in string_list(query.get("module") or query.get("modules"))}
        repository_terms = {term.lower() for term in string_list(query.get("repository"))}
        decision = clean(query.get("decision")).lower()
        stage = clean(query.get("stage")).lower()
        results: list[dict[str, Any]] = []
        for trace in traces:
            if project_id and clean(trace.get("projectId")) != project_id:
                continue
            if artifact_id and clean(trace.get("artifactId")) != artifact_id:
                continue
            if artifact_type and clean(trace.get("artifactType")).lower() != artifact_type.lower():
                continue
            if stage and clean(trace.get("stage")).lower() != stage:
                continue
            if decision and decision not in clean(trace.get("decision")).lower():
                continue
            score, reasons = self._score(trace, terms, artifact_id, artifact_type, module_terms, repository_terms, decision, stage)
            if score > 0 or not any([terms, artifact_id, artifact_type, project_id, module_terms, repository_terms, decision, stage]):
                results.append({**trace, "searchScore": score, "matchReasons": reasons})
        results.sort(key=lambda item: (item.get("searchScore", 0), item.get("confidence", 0)), reverse=True)
        limit = int(query.get("limit") or 30)
        return {"traces": results[:limit], "count": len(results)}

    def _score(
        self,
        trace: dict[str, Any],
        terms: set[str],
        artifact_id: str,
        artifact_type: str,
        module_terms: set[str],
        repository_terms: set[str],
        decision: str,
        stage: str,
    ) -> tuple[int, list[str]]:
        haystack = " ".join([
            clean(trace.get("decision")),
            clean(trace.get("reason")),
            clean(trace.get("artifactTitle")),
            " ".join(string_list(trace.get("tags"))),
            " ".join(_evidence_text(trace.get("evidence"))),
            " ".join(_evidence_text(trace.get("repositoryEvidence"))),
            " ".join(_evidence_text(trace.get("memoryUsed"))),
            " ".join(_evidence_text(trace.get("graphEvidence"))),
        ]).lower()
        score = 0
        reasons: list[str] = []
        if artifact_id and clean(trace.get("artifactId")) == artifact_id:
            score += 20
            reasons.append("artifact")
        if artifact_type and clean(trace.get("artifactType")).lower() == artifact_type.lower():
            score += 10
            reasons.append("artifact_type")
        if stage and clean(trace.get("stage")).lower() == stage:
            score += 8
            reasons.append("stage")
        if decision and decision in clean(trace.get("decision")).lower():
            score += 12
            reasons.append("decision")
        overlap = {term for term in terms if term and term in haystack}
        if overlap:
            score += len(overlap) * 3
            reasons.append("keyword")
        if any(term in haystack for term in module_terms):
            score += 10
            reasons.append("module")
        if any(term in haystack for term in repository_terms):
            score += 10
            reasons.append("repository")
        return score, reasons


def _evidence_text(values: Any) -> list[str]:
    output: list[str] = []
    if not isinstance(values, list):
        values = [values] if values else []
    for item in values:
        if isinstance(item, dict):
            output.extend(string_list([item.get("name"), item.get("title"), item.get("summary"), item.get("reason"), item.get("path")]))
        else:
            output.extend(string_list(item))
    return output
