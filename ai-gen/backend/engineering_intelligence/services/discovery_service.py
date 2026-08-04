"""Evidence-backed Engineering Discovery projections."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict
from typing import Any, Iterable

from ..models import DiscoveryEvidence, EngineeringContext, EngineeringDiscoveryReport


class EngineeringDiscoveryService:
    """Explains relevant engineering knowledge already present in a context."""

    def build_report(
        self, value: EngineeringContext | dict[str, Any],
    ) -> dict[str, Any]:
        context = value.to_dict() if isinstance(value, EngineeringContext) else dict(value)
        repository = dict(context.get("repository") or {})
        markdown = dict(context.get("repository_markdown_context") or {})
        azure_devops = dict(context.get("azureDevOps") or {})
        memory = dict(context.get("engineeringMemory") or {})
        similarity = dict(context.get("similarWork") or {})
        architecture = dict(context.get("architecture") or {})
        project = dict(context.get("projectIntelligence") or {})
        synthesis = dict(context.get("knowledge_synthesis") or {})
        terms = _search_terms(context.get("requirement") or {})

        repository_evidence = self._repository_evidence(repository, terms)
        documentation = self._documentation_evidence(context, markdown)
        markdown_evidence = [
            item for item in documentation if item["source"] == "Repository Markdown"
        ]
        similar_features = self._similar_features(similarity, azure_devops, terms)
        ado_evidence = self._ado_evidence(similar_features, azure_devops, terms)
        memory_evidence = self._memory_evidence(memory)
        reusable = self._reusable_evidence(context, repository, memory_evidence, terms)
        architecture_evidence = self._architecture_evidence(
            architecture, documentation, repository,
        )
        knowledge_evidence = self._knowledge_evidence(project)
        project_evidence = self._project_intelligence_evidence(
            project, documentation, similar_features,
        )
        conflicts = _unique_records([
            *(markdown.get("conflicts") or []),
            *(synthesis.get("conflicts") or []),
        ])
        unknowns = [
            {
                "area": _display_name(name),
                "reason": f"{_display_name(name)} remains unresolved in the current requirement and selected evidence.",
                "classification": "UnresolvedRequirementInformation",
            }
            for name in synthesis.get("unresolvedInformation") or []
        ]
        source_status = self._source_status(
            repository, markdown, azure_devops, memory, project,
            repository_evidence, markdown_evidence, ado_evidence, memory_evidence,
            project_evidence, knowledge_evidence,
        )
        groups = {
            "Repository Intelligence": repository_evidence,
            "Repository Markdown": markdown_evidence,
            "Azure DevOps": ado_evidence,
            "Engineering Memory": memory_evidence,
            "Project Intelligence": project_evidence,
            "Knowledge Registry": knowledge_evidence,
        }
        what_i_found = [
            {
                "source": source,
                "status": next(
                    (item["status"] for item in source_status if item["source"] == source),
                    "NoRelevantEvidence",
                ),
                "count": len(items),
                "summary": _finding_summary(source, items),
                "evidenceReferences": [item["sourceReference"] for item in items[:8]],
                "findings": [
                    {
                        "title": item.get("title") or item.get("sourceReference"),
                        "type": item.get("evidenceType") or "Evidence",
                        "sourceReference": item.get("sourceReference"),
                        "reason": item.get("reason"),
                        "confidence": item.get("confidence"),
                    }
                    for item in items[:8]
                ],
            }
            for source, items in groups.items()
        ]
        all_evidence = _unique_evidence([
            *repository_evidence, *documentation, *ado_evidence,
            *memory_evidence, *project_evidence, *knowledge_evidence,
        ])
        pending = sum(item["status"] == "DiscoveryPending" for item in source_status)
        if not all_evidence:
            status = "DiscoveryPending" if pending else "NoRelevantEvidence"
        elif pending:
            status = "Partial"
        else:
            status = "Ready"
        confidence = self._confidence(
            all_evidence, source_status, int(repository.get("confidence") or 0), conflicts,
        )
        summary = {
            "DiscoveryPending": "Engineering sources are still being synchronized.",
            "NoRelevantEvidence": "Discovery completed, but no relevant engineering evidence was found.",
            "Partial": "Relevant engineering evidence was found; one or more sources are still pending.",
            "Ready": "Relevant engineering knowledge is ready for requirement reasoning.",
        }[status]
        return EngineeringDiscoveryReport(
            schemaVersion="hei-engineering-discovery-v2",
            contextId=str(context.get("contextId") or ""),
            contextVersion=str(context.get("contextVersion") or ""),
            status=status,
            summary=summary,
            whatIFound=what_i_found,
            reusableComponents=reusable,
            similarFeatures=similar_features,
            relevantDocumentation=documentation,
            architectureEvidence=architecture_evidence,
            repositoryEvidence=repository_evidence,
            azureDevOpsEvidence=ado_evidence,
            engineeringMemoryEvidence=memory_evidence,
            projectIntelligenceEvidence=project_evidence,
            knowledgeEvidence=knowledge_evidence,
            conflicts=conflicts,
            unknowns=unknowns,
            sourceStatus=source_status,
            confidence=confidence,
        ).to_dict()

    def _repository_evidence(
        self, repository: dict[str, Any], terms: set[str],
    ) -> list[dict[str, Any]]:
        repository_id = str(repository.get("repositoryId") or "repository")
        snapshot = str(
            repository.get("repositorySnapshotVersion")
            or repository.get("snapshotVersion") or "snapshot-unavailable"
        )
        result: list[dict[str, Any]] = []
        collections = (
            ("Module", repository.get("affectedModules") or []),
            ("Service", repository.get("services") or []),
            ("API", repository.get("apiEndpoints") or []),
            ("Screen", repository.get("screens") or []),
            ("DatabaseTable", repository.get("databaseObjects") or []),
            ("Test", repository.get("tests") or []),
        )
        affected = {_normal(value) for value in repository.get("affectedModules") or []}
        for evidence_type, values in collections:
            for value in values:
                title = str(value or "").strip()
                if not title:
                    continue
                relevant = evidence_type == "Module" or _matches(title, terms, affected)
                if not relevant:
                    continue
                result.append(_evidence(
                    evidence_type, title, "Repository Intelligence",
                    f"repository:{repository_id}:{snapshot}:{_slug(title)}",
                    "Matched requirement intent in the current Repository Intelligence snapshot.",
                    int(repository.get("confidence") or 80),
                    {"repositoryId": repository_id, "snapshotVersion": snapshot},
                ))
        for item in repository.get("files") or []:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or item.get("name") or "").strip()
            if not path or not _matches(path, terms, affected):
                continue
            result.append(_evidence(
                "File", path, "Repository Intelligence",
                str(item.get("evidenceId") or f"repository:{repository_id}:{snapshot}:file:{path}"),
                str(item.get("reason") or "File name or path matched the requirement intent."),
                _percent(item.get("confidence"), int(repository.get("confidence") or 75)),
                {"path": path, "repositoryId": repository_id, "snapshotVersion": snapshot},
            ))
        return _unique_evidence(result)

    def _documentation_evidence(
        self, context: dict[str, Any], markdown: dict[str, Any],
    ) -> list[dict[str, Any]]:
        documents = [
            *(markdown.get("selected") or []),
            *(context.get("relevantDocumentation") or []),
        ]
        result = []
        for item in documents:
            if isinstance(item, str):
                item = {"path": item, "heading": "Document"}
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or item.get("name") or "").strip()
            if not path:
                continue
            heading = str(item.get("heading") or item.get("title") or "Document").strip()
            reference = str(item.get("evidenceId") or item.get("referenceId") or f"documentation:{path}:{_slug(heading)}")
            result.append(_evidence(
                "Documentation", f"{path} · {heading}",
                "Repository Markdown" if item.get("evidenceId") else "Project Intelligence",
                reference,
                str(item.get("selectionReason") or item.get("reason") or "Selected as relevant engineering documentation."),
                _percent(item.get("confidence") or item.get("relevanceScore"), 75),
                {
                    "path": path, "heading": heading,
                    "classification": item.get("classification"),
                    "repositoryRevision": item.get("repositoryRevision"),
                    "authority": item.get("authority"),
                },
            ))
        return _unique_evidence(result)

    def _similar_features(
        self, similarity: dict[str, Any], azure_devops: dict[str, Any], terms: set[str],
    ) -> list[dict[str, Any]]:
        candidates = [
            *(similarity.get("existingFeature") or []),
            *(similarity.get("matches") or []),
        ]
        result = []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            work_item = item.get("workItem") or item
            kind = str(work_item.get("type") or work_item.get("workItemType") or "")
            title = str(work_item.get("title") or item.get("title") or "").strip()
            if not title or (kind and kind.casefold() not in {"feature", "story", "user story", "epic"}):
                continue
            score = _percent(item.get("confidence") or item.get("similarity"), 65)
            if score < 45 and not _matches(title, terms, set()):
                continue
            work_item_id = str(work_item.get("id") or work_item.get("workItemId") or _slug(title))
            source = "Project Intelligence" if "project intelligence" in str(item.get("source") or "").casefold() else "Azure DevOps"
            source_reference = (
                f"project-artifact:{work_item_id}:version:{work_item.get('version') or item.get('version') or 1}"
                if source == "Project Intelligence"
                else f"ado:work-item:{work_item_id}:revision:{work_item.get('revision') or 0}"
            )
            result.append(_evidence(
                "SimilarWork", title, source,
                source_reference,
                str(item.get("reason") or "The synchronized work item matches the requirement intent."),
                score,
                {"workItemId": work_item_id, "workItemType": kind or "Work Item", "state": work_item.get("state")},
            ))
        return _unique_evidence(result)

    def _ado_evidence(
        self, similar: list[dict[str, Any]], azure_devops: dict[str, Any], terms: set[str],
    ) -> list[dict[str, Any]]:
        result = [item for item in similar if item["source"] == "Azure DevOps"]
        known = {item["metadata"].get("workItemId") for item in similar}
        for item in azure_devops.get("existingPlanning") or []:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            item_id = str(item.get("id") or item.get("workItemId") or "")
            if not title or item_id in known or not _matches(title, terms, set()):
                continue
            result.append(_evidence(
                "WorkItem", title, "Azure DevOps",
                f"ado:work-item:{item_id or _slug(title)}:revision:{item.get('revision') or 0}",
                "The synchronized work-item title matched requirement search terms.",
                65,
                {"workItemId": item_id, "workItemType": item.get("type"), "state": item.get("state")},
            ))
        return _unique_evidence(result)

    def _project_intelligence_evidence(
        self,
        project: dict[str, Any],
        documentation: list[dict[str, Any]],
        similar: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result = [
            *[item for item in documentation if item["source"] == "Project Intelligence"],
            *[item for item in similar if item["source"] == "Project Intelligence"],
        ]
        for item in project.get("approvedArtifacts") or []:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            artifact_id = str(item.get("id") or _slug(title))
            result.append(_evidence(
                str(item.get("artifactType") or "ApprovedArtifact"), title,
                "Project Intelligence",
                f"project-artifact:{artifact_id}:version:{item.get('version') or 1}",
                str(item.get("reason") or "Approved project artifact matched requirement intent."),
                _percent(item.get("confidence"), 75),
                {"artifactId": artifact_id, "version": item.get("version"), "state": item.get("state")},
            ))
        return _unique_evidence(result)

    def _memory_evidence(self, memory: dict[str, Any]) -> list[dict[str, Any]]:
        result = []
        for item in memory.get("matches") or []:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("summary") or "").strip()
            if not title:
                continue
            memory_id = str(item.get("id") or item.get("memoryId") or _slug(title))
            result.append(_evidence(
                str(item.get("artifactType") or item.get("category") or "EngineeringMemory"),
                title, "Engineering Memory",
                f"memory:{memory_id}:version:{item.get('version') or 1}",
                str(item.get("reason") or "Approved Engineering Memory matched the requirement context."),
                _percent(item.get("confidence"), 75),
                {"memoryId": memory_id, "version": item.get("version"), "category": item.get("category")},
            ))
        return _unique_evidence(result)

    def _reusable_evidence(
        self,
        context: dict[str, Any],
        repository: dict[str, Any],
        memory: list[dict[str, Any]],
        terms: set[str],
    ) -> list[dict[str, Any]]:
        result = [
            item for item in memory
            if item["evidenceType"].casefold() in {
                "component", "api", "test", "executionpackage", "implementationpattern",
            }
        ]
        reuse = context.get("reuse") or {}
        for evidence_type, values in (
            ("Component", repository.get("sharedComponents") or []),
            ("API", reuse.get("apis") or []),
            ("Test", reuse.get("tests") or []),
        ):
            for value in values:
                item = value if isinstance(value, dict) else {"name": value}
                title = str(item.get("name") or item.get("title") or "").strip()
                if not title or not _matches(title, terms, set()):
                    continue
                result.append(_evidence(
                    evidence_type, title, "Repository Intelligence",
                    str(item.get("evidenceId") or f"repository:reuse:{evidence_type.casefold()}:{_slug(title)}"),
                    str(item.get("reason") or "Existing repository artifact matches the requirement intent."),
                    _percent(item.get("confidence"), 75),
                    {"reusable": True},
                ))
        return _unique_evidence(result)

    def _architecture_evidence(
        self,
        architecture: dict[str, Any],
        documentation: list[dict[str, Any]],
        repository: dict[str, Any],
    ) -> list[dict[str, Any]]:
        result = []
        for item in architecture.get("evidence") or []:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("name") or item.get("path") or "Architecture evidence")
            result.append(_evidence(
                "Architecture", title, "Repository Intelligence",
                str(item.get("evidenceId") or item.get("referenceId") or f"architecture:{_slug(title)}"),
                str(item.get("reason") or "Repository graph supports this architecture finding."),
                _percent(item.get("confidence"), int(repository.get("confidence") or 75)),
                item,
            ))
        result.extend(
            item for item in documentation
            if str(item.get("metadata", {}).get("classification") or "").casefold() in {"architecture", "adr"}
        )
        return _unique_evidence(result)

    def _knowledge_evidence(self, project: dict[str, Any]) -> list[dict[str, Any]]:
        knowledge = project.get("knowledge") or {}
        version = str(knowledge.get("version") or "not-versioned")
        result = []
        for evidence_type, key in (
            ("Module", "modules"), ("Flow", "flows"), ("Application", "applications"),
            ("Component", "components"), ("Standard", "standards"),
            ("Architecture", "architectureNotes"),
        ):
            for value in knowledge.get(key) or []:
                title = str(value or "").strip()
                if title:
                    result.append(_evidence(
                        evidence_type, title, "Knowledge Registry",
                        f"knowledge:{version}:{key}:{_slug(title)}",
                        "Intent-selected Knowledge Registry evidence.", 80,
                        {"knowledgeVersion": version},
                    ))
        return _unique_evidence(result)

    def _source_status(
        self,
        repository: dict[str, Any], markdown: dict[str, Any], azure_devops: dict[str, Any],
        memory: dict[str, Any], project: dict[str, Any], repository_evidence: list[dict[str, Any]],
        documentation: list[dict[str, Any]], ado_evidence: list[dict[str, Any]],
        memory_evidence: list[dict[str, Any]], project_evidence: list[dict[str, Any]],
        knowledge_evidence: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        repository_id = repository.get("repositoryId")
        snapshot = repository.get("repositorySnapshotVersion") or repository.get("snapshotVersion")
        markdown_diagnostics = markdown.get("diagnostics") or {}
        knowledge = project.get("knowledge") or {}
        return [
            _source_state(
                "Repository Intelligence", bool(repository_id and snapshot), bool(repository_evidence),
                "Repository synchronization is required before code evidence can be discovered."
                if not snapshot else "No relevant repository evidence found.",
            ),
            _source_state(
                "Repository Markdown", bool(
                    markdown_diagnostics.get("indexedAt")
                    or markdown_diagnostics.get("filesScanned")
                    or markdown_diagnostics.get("sectionsIndexed")
                ),
                bool(documentation),
                str(markdown_diagnostics.get("warning") or "No relevant documentation found."),
            ),
            _source_state(
                "Azure DevOps", bool(azure_devops.get("available")), bool(ado_evidence),
                "Azure DevOps synchronization is pending." if not azure_devops.get("available") else "No relevant Azure DevOps work found.",
            ),
            _source_state(
                "Engineering Memory", bool(memory.get("available")), bool(memory_evidence),
                "Engineering Memory retrieval is pending." if not memory.get("available") else "No relevant approved Engineering Memory found.",
            ),
            _source_state(
                "Project Intelligence", bool(project.get("available")), bool(project_evidence),
                "Project Intelligence is pending." if not project.get("available") else "No relevant approved project evidence found.",
            ),
            _source_state(
                "Knowledge Registry", bool(knowledge.get("version") or project.get("available")), bool(knowledge_evidence),
                "Knowledge Registry synchronization is pending." if not knowledge else "No relevant Knowledge Registry evidence found.",
            ),
        ]

    @staticmethod
    def _confidence(
        evidence: list[dict[str, Any]], source_status: list[dict[str, Any]],
        repository_confidence: int, conflicts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        completed = sum(item["status"] in {"Ready", "NoRelevantEvidence"} for item in source_status)
        source_coverage = round(completed / max(1, len(source_status)) * 100)
        evidence_quality = round(
            sum(item["confidence"] for item in evidence) / len(evidence)
        ) if evidence else 0
        score = round(
            min(100, evidence_quality * 0.55 + source_coverage * 0.3 + repository_confidence * 0.15)
        )
        score = max(0, score - min(20, len(conflicts) * 5))
        return {
            "score": score,
            "level": "High" if score >= 80 else "Medium" if score >= 55 else "Low",
            "evidenceCoverage": source_coverage,
            "evidenceCount": len(evidence),
            "conflictCount": len(conflicts),
            "reason": "Calculated from source completion, evidence confidence, repository confidence, and unresolved conflicts.",
        }

    buildReport = build_report


def _evidence(
    evidence_type: str, title: str, source: str, source_reference: str,
    reason: str, confidence: int, metadata: dict[str, Any],
) -> dict[str, Any]:
    evidence_id = "discovery:" + hashlib.sha256(
        f"{source}|{source_reference}|{title}".encode("utf-8")
    ).hexdigest()[:16]
    return asdict(DiscoveryEvidence(
        evidenceId=evidence_id,
        evidenceType=evidence_type,
        title=title,
        source=source,
        sourceReference=source_reference,
        reason=reason,
        confidence=max(0, min(100, int(confidence))),
        metadata={key: value for key, value in metadata.items() if value not in (None, "", [])},
    ))


def _source_state(source: str, searched: bool, found: bool, message: str) -> dict[str, Any]:
    if not searched:
        status = "DiscoveryPending"
    elif found:
        status = "Ready"
    else:
        status = "NoRelevantEvidence"
    return {"source": source, "status": status, "message": message}


def _finding_summary(source: str, evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return "No relevant evidence found."
    kinds: dict[str, int] = {}
    for item in evidence:
        kind = item["evidenceType"]
        kinds[kind] = kinds.get(kind, 0) + 1
    detail = ", ".join(f"{count} {kind.lower()}" for kind, count in sorted(kinds.items()))
    return f"{source} contributed {detail}."


def _search_terms(requirement: dict[str, Any]) -> set[str]:
    intent = requirement.get("requirementIntent") or {}
    values: list[Any] = [
        requirement.get("title"), requirement.get("planningRequirement"),
        requirement.get("content"), intent.get("intentSummary"), intent.get("businessGoal"),
    ]
    for key in (
        "businessGoals", "functionalRequirements", "acceptanceCriteria", "actors",
    ):
        values.extend(requirement.get(key) or [])
    for key in (
        "functionalIntent", "entities", "capabilities", "actions", "concepts",
        "searchKeywords", "possibleModuleNames", "possibleFeatureNames", "possibleApis",
        "possibleRepositoryTerms", "possibleAzureDevOpsSearchTerms", "possibleMarkdownSearchTerms",
    ):
        values.extend(intent.get(key) or [])
    return {
        term for value in values for term in re.findall(r"[a-z0-9]+", str(value).casefold())
        if len(term) > 2 and term not in {"with", "from", "that", "this", "should", "user", "users"}
    }


def _matches(value: str, terms: set[str], affected: set[str]) -> bool:
    normalized = _normal(value)
    words = set(re.findall(r"[a-z0-9]+", normalized))
    return bool(words & terms or any(name and name in normalized for name in affected))


def _percent(value: Any, fallback: int) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return round(number * 100 if 0 < number <= 1 else number)


def _display_name(value: Any) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", " ", str(value or "Unknown")).replace("_", " ").title()


def _normal(value: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def _slug(value: Any) -> str:
    return "-".join(re.findall(r"[a-z0-9]+", str(value or "").casefold()))[:120] or "unknown"


def _unique_evidence(values: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for value in values:
        marker = (value.get("sourceReference"), value.get("title"))
        if marker not in seen:
            seen.add(marker)
            result.append(value)
    return result


def _unique_records(values: Iterable[Any]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for value in values:
        if not isinstance(value, dict):
            continue
        marker = str(value.get("conflictId") or value.get("reason") or sorted(value.items()))
        if marker not in seen:
            seen.add(marker)
            result.append(dict(value))
    return result
