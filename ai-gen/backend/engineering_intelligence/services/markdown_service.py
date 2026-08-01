"""Repository-wide Markdown discovery, indexing, and bounded retrieval."""

from __future__ import annotations

import fnmatch
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Iterable


DEFAULT_INCLUDES = ("*.md", "*.markdown", "**/*.md", "**/*.markdown")
DEFAULT_EXCLUDED_DIRECTORIES = {
    ".git", ".cache", ".next", ".nuxt", ".pytest_cache", ".turbo",
    "__pycache__", "bin", "build", "coverage", "dist", "generated",
    "node_modules", "obj", "out", "packages", "target", "vendor",
}
CLASSIFICATIONS = {
    "product", "business_rule", "architecture", "adr", "domain_glossary",
    "api", "integration", "security", "compliance", "coding_standard",
    "deployment", "operations", "feature_specification", "planning_history",
    "general_documentation",
}
STATEMENT_RULES = {
    "businessGoals": ("goal", "outcome", "business value", "objective"),
    "businessRules": ("business rule", "must", "shall", "required"),
    "constraints": ("constraint", "limitation", "must not", "shall not"),
    "architectureDecisions": ("decision", "architecture", "adr", "chosen"),
    "domainTerminology": ("glossary", "terminology", "means", "definition"),
    "supportedPlatforms": ("platform", "supported", "compatibility"),
    "integrationContracts": ("integration", "contract", "endpoint", "webhook"),
    "securityRequirements": ("security", "permission", "authorization", "authentication"),
    "nonFunctionalRequirements": ("performance", "availability", "latency", "scalability"),
    "deprecatedApproaches": ("deprecated", "do not use", "replaced by", "obsolete"),
    "reusableComponents": ("reuse", "component", "service", "library"),
    "knownRisks": ("risk", "warning", "failure", "caveat"),
    "implementationConventions": ("convention", "coding standard", "guideline", "style"),
}


class MarkdownService:
    def __init__(
        self,
        *,
        include_patterns: Iterable[str] | None = None,
        exclude_patterns: Iterable[str] | None = None,
    ) -> None:
        self.include_patterns = tuple(include_patterns or DEFAULT_INCLUDES)
        self.exclude_patterns = tuple(exclude_patterns or ())
        self._sections: list[dict[str, Any]] = []
        self._scan_diagnostics: dict[str, dict[str, Any]] = {}

    def discover_repository(
        self,
        root_path: str | Path,
        *,
        repository_id: str,
        repository_name: str = "",
        project_id: str = "",
        revision: str = "",
        include_patterns: Iterable[str] | None = None,
        exclude_patterns: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        root = Path(root_path).expanduser()
        if not root.is_dir():
            return self._empty_discovery(repository_id, revision, "Repository path is unavailable.")
        includes = tuple(include_patterns or self.include_patterns)
        excludes = tuple(exclude_patterns or self.exclude_patterns)
        documents: list[dict[str, Any]] = []
        ignored = 0
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if self._ignored(relative, includes, excludes):
                ignored += int(path.suffix.casefold() in {".md", ".markdown"})
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                ignored += 1
                continue
            documents.append({"path": relative, "content": content})
        return self.index_repository_documents(
            documents,
            repository_id=repository_id,
            repository_name=repository_name,
            project_id=project_id,
            revision=revision,
            ignored_count=ignored,
        )

    def index_repository_documents(
        self,
        documents: Iterable[dict[str, Any]],
        *,
        repository_id: str,
        repository_name: str = "",
        project_id: str = "",
        revision: str = "",
        ignored_count: int = 0,
    ) -> dict[str, Any]:
        indexed_at = datetime.now(timezone.utc).isoformat()
        sections: list[dict[str, Any]] = []
        files_scanned = 0
        for document in documents:
            path = str(document.get("path") or "").strip().replace("\\", "/")
            content = str(document.get("content") or "")
            if not path.casefold().endswith((".md", ".markdown")) or not content.strip():
                continue
            if self._ignored(path, self.include_patterns, self.exclude_patterns):
                ignored_count += 1
                continue
            files_scanned += 1
            sections.extend(self._parse_document(
                path,
                content,
                repository_id=repository_id,
                repository_name=repository_name,
                project_id=project_id,
                revision=str(document.get("revision") or revision),
                indexed_at=indexed_at,
            ))
        self._sections = [
            item for item in self._sections if item.get("repositoryId") != repository_id
        ] + sections
        diagnostic = {
            "repositoryId": repository_id,
            "repositoryRevision": revision,
            "filesScanned": files_scanned,
            "sectionsIndexed": len(sections),
            "ignoredFiles": ignored_count,
            "indexedAt": indexed_at,
            "contentHashes": sorted({item["contentHash"] for item in sections}),
        }
        self._scan_diagnostics[repository_id] = diagnostic
        return {**diagnostic, "sections": self._public(sections)}

    def index_markdown(self, documents: dict[str, str]) -> dict[str, Any]:
        result = self.index_repository_documents(
            [{"path": path, "content": content} for path, content in documents.items()],
            repository_id="manual",
            repository_name="Manually supplied documents",
        )
        return {
            "documentsIndexed": result["filesScanned"],
            "sectionsIndexed": result["sectionsIndexed"],
            "documents": result["sections"],
        }

    def retrieve(
        self,
        query: str,
        *,
        project_id: str = "",
        repository_id: str = "",
        token_budget: int = 1800,
        limit: int = 12,
        code_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        terms = _terms(query)
        ranked: list[tuple[float, dict[str, Any], list[str]]] = []
        rejected: list[dict[str, Any]] = []
        for section in self._sections:
            if project_id and section.get("projectId") and section.get("projectId") != project_id:
                rejected.append(_rejection(section, "different_project"))
                continue
            if repository_id and section.get("repositoryId") != repository_id:
                rejected.append(_rejection(section, "different_repository"))
                continue
            searchable = " ".join([
                section["path"], section["heading"], section["classification"],
                section["sourceText"], " ".join(section["statements"].keys()),
            ]).casefold()
            matched = sorted(term for term in terms if term in searchable)
            if terms and not matched:
                rejected.append(_rejection(section, "not_relevant"))
                continue
            authority = _authority_score(section["classification"])
            score = len(matched) * 8 + authority + min(8, len(section["statements"]))
            ranked.append((score, section, matched))
        ranked.sort(key=lambda item: (-item[0], item[1]["path"], item[1]["sectionId"]))

        selected: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        tokens = 0
        for score, section, matched in ranked:
            duplicate_key = (section["contentHash"], section["sourceText"].casefold())
            if duplicate_key in seen:
                rejected.append(_rejection(section, "duplicate"))
                continue
            estimate = max(1, len(section["sourceText"]) // 4)
            if len(selected) >= limit or tokens + estimate > token_budget:
                rejected.append(_rejection(section, "token_budget"))
                continue
            seen.add(duplicate_key)
            tokens += estimate
            selected.append({
                **self._public([section])[0],
                "relevanceScore": round(min(100.0, score * 3.5), 1),
                "selectionReason": (
                    "Matched " + ", ".join(matched[:8])
                    if matched else "Authoritative repository documentation"
                ),
                "authority": _authority(section["classification"]),
                "estimatedTokens": estimate,
            })
        conflicts = self.detect_conflicts(selected, code_context or {})
        conflicted_evidence = {
            item.get("markdownEvidenceId") for item in conflicts
        }
        for item in selected:
            item["factualStatus"] = (
                "conflicted"
                if item.get("evidenceId") in conflicted_evidence
                else "usable"
            )
        return {
            "selected": selected,
            "rejected": rejected,
            "conflicts": conflicts,
            "diagnostics": {
                **self._scan_diagnostics.get(repository_id, {}),
                "sectionsSelected": len(selected),
                "rejectedContextCount": len(rejected),
                "selectedTokens": tokens,
                "tokenBudget": token_budget,
                "conflictsDetected": len(conflicts),
            },
        }

    def search_documentation(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        return self.retrieve(query, limit=limit, token_budget=max(600, limit * 180))["selected"]

    def get_architecture_summary(self) -> str:
        candidates = [
            item for item in self._sections
            if item["classification"] in {"architecture", "adr"}
        ]
        return "\n\n".join(item["summary"] for item in candidates[:5])

    def detect_conflicts(
        self,
        selected: list[dict[str, Any]],
        code_context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        implemented = {
            str(value).casefold(): str(value)
            for key in ("modules", "services", "apiEndpoints")
            for value in code_context.get(key) or []
        }
        conflicts = []
        for section in selected:
            deprecated = (section.get("statements") or {}).get("deprecatedApproaches") or []
            for statement in deprecated:
                matches = sorted(
                    original for name, original in implemented.items()
                    if name and name in statement.casefold()
                )
                if matches:
                    conflicts.append({
                        "conflictId": "markdown-code-" + hashlib.sha256(
                            f"{section['evidenceId']}|{statement}".encode()
                        ).hexdigest()[:12],
                        "claimType": "current_implementation",
                        "markdownEvidenceId": section["evidenceId"],
                        "path": section["path"],
                        "heading": section["heading"],
                        "repositoryCodeEvidence": matches,
                        "reason": "Repository documentation deprecates an item still present in current code.",
                        "resolution": "Exclude the uncertain claim until a human resolves the source conflict.",
                    })
        return conflicts

    @staticmethod
    def _ignored(path: str, includes: Iterable[str], excludes: Iterable[str]) -> bool:
        parts = {part.casefold() for part in Path(path).parts}
        if parts & DEFAULT_EXCLUDED_DIRECTORIES:
            return True
        if any(fnmatch.fnmatch(path, pattern) for pattern in excludes):
            return True
        return not any(fnmatch.fnmatch(path, pattern) for pattern in includes)

    @staticmethod
    def _empty_discovery(repository_id: str, revision: str, warning: str) -> dict[str, Any]:
        return {
            "repositoryId": repository_id,
            "repositoryRevision": revision,
            "filesScanned": 0,
            "sectionsIndexed": 0,
            "ignoredFiles": 0,
            "sections": [],
            "warning": warning,
        }

    def _parse_document(
        self,
        path: str,
        content: str,
        *,
        repository_id: str,
        repository_name: str,
        project_id: str,
        revision: str,
        indexed_at: str,
    ) -> list[dict[str, Any]]:
        matches = list(re.finditer(r"(?m)^(#{1,6})\s+(.+?)\s*$", content))
        spans: list[tuple[str, str]] = []
        if not matches:
            spans.append((Path(path).stem, content))
        else:
            preamble = content[:matches[0].start()].strip()
            if preamble:
                spans.append((Path(path).stem, preamble))
            for index, match in enumerate(matches):
                end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
                spans.append((match.group(2).strip(), content[match.end():end].strip()))
        result = []
        document_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        for index, (heading, section_text) in enumerate(spans, start=1):
            if not section_text:
                continue
            classification = _classification(path, heading, section_text)
            source_text = _compact(section_text, 1600)
            section_id = f"section-{index}-{_slug(heading)}"
            evidence_id = (
                f"markdown:{repository_id}:{document_hash[:12]}:{section_id}"
            )
            statements = _extract_statements(section_text)
            extracted_statements = [
                {
                    "statementId": f"{evidence_id}:{claim_type}:{statement_index}",
                    "claimType": claim_type,
                    "text": statement,
                    "evidenceId": evidence_id,
                    "repository": repository_name or repository_id,
                    "path": path,
                    "heading": heading,
                    "sectionId": section_id,
                    "sourceText": statement,
                    "classification": classification,
                    "extractionMethod": "deterministic_markdown_section_v1",
                    "confidence": _classification_confidence(classification),
                    "contentHash": document_hash,
                    "repositoryRevision": revision,
                    "indexedAt": indexed_at,
                }
                for claim_type, values in statements.items()
                for statement_index, statement in enumerate(values, start=1)
            ]
            result.append({
                "evidenceId": evidence_id,
                "repositoryId": repository_id,
                "repository": repository_name or repository_id,
                "projectId": project_id,
                "path": path,
                "heading": heading,
                "sectionId": section_id,
                "sourceText": source_text,
                "summary": _compact(source_text, 420),
                "classification": classification,
                "extractionMethod": "deterministic_markdown_section_v1",
                "confidence": _classification_confidence(classification),
                "contentHash": document_hash,
                "repositoryRevision": revision,
                "indexedAt": indexed_at,
                "statements": statements,
                "extractedStatements": extracted_statements,
            })
        return result

    @staticmethod
    def _public(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [dict(item) for item in sections]

    indexMarkdown = index_markdown
    searchDocumentation = search_documentation
    getArchitectureSummary = get_architecture_summary


def _classification(path: str, heading: str, content: str) -> str:
    value = f"{path} {heading}".casefold()
    rules = (
        ("adr", ("adr/", "decision record", "architecture decision")),
        ("architecture", ("architecture", "architectural", "design/")),
        ("business_rule", ("business rule", "business-rules")),
        ("domain_glossary", ("glossary", "terminology", "domain language")),
        ("api", ("api", "endpoint", "openapi")),
        ("integration", ("integration", "webhook", "connector")),
        ("security", ("security", "authentication", "authorization")),
        ("compliance", ("compliance", "governance", "regulatory")),
        ("coding_standard", ("contributing", "coding", "style guide", "guideline")),
        ("deployment", ("deploy", "release", "pipeline")),
        ("operations", ("operations", "runbook", "monitoring")),
        ("feature_specification", ("feature", "specification", "requirements")),
        ("planning_history", ("planning", "roadmap", "backlog")),
        ("product", ("readme", "product", "vision", "prd", "brd")),
    )
    for classification, markers in rules:
        if any(marker in value for marker in markers):
            return classification
    if any(marker in content.casefold() for marker in ("business goal", "user need", "business value")):
        return "product"
    return "general_documentation"


def _extract_statements(content: str) -> dict[str, list[str]]:
    candidates = [
        _compact(item, 420)
        for item in re.split(r"(?<=[.!?])\s+|^\s*[-*]\s+", content, flags=re.MULTILINE)
        if len(item.strip()) >= 12
    ]
    result: dict[str, list[str]] = {}
    for key, markers in STATEMENT_RULES.items():
        values = [
            item for item in candidates
            if any(marker in item.casefold() for marker in markers)
        ][:8]
        if values:
            result[key] = values
    return result


def _terms(value: str) -> set[str]:
    ignored = {"that", "this", "with", "from", "into", "have", "will", "should", "user"}
    return {
        term for term in re.findall(r"[a-z0-9][a-z0-9_-]+", value.casefold())
        if len(term) > 2 and term not in ignored
    }


def _authority_score(classification: str) -> int:
    if classification in {"adr", "architecture", "business_rule", "security", "compliance"}:
        return 12
    if classification in {"product", "feature_specification", "api", "integration"}:
        return 8
    return 4


def _authority(classification: str) -> str:
    if classification in {"business_rule", "product", "feature_specification"}:
        return "approved_business_documentation"
    if classification in {"adr", "architecture"}:
        return "architecture_documentation"
    return "repository_documentation"


def _classification_confidence(classification: str) -> int:
    return 88 if classification != "general_documentation" else 70


def _rejection(section: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "evidenceId": section.get("evidenceId"),
        "path": section.get("path"),
        "heading": section.get("heading"),
        "reason": reason,
    }


def _compact(value: str, limit: int) -> str:
    return re.sub(r"\s+", " ", value).strip()[:limit]


def _slug(value: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return clean[:48] or "content"
