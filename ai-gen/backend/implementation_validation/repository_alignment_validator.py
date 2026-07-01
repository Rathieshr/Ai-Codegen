"""Repository alignment validation."""

from __future__ import annotations

from typing import Any

from .models import clean, string_list, violation


class RepositoryAlignmentValidator:
    def validate(self, execution_package: dict[str, Any], changed_files: list[dict[str, Any]]) -> dict[str, Any]:
        repository = execution_package.get("repositoryContext") if isinstance(execution_package.get("repositoryContext"), dict) else {}
        relevant_files = _repo_item_names(repository.get("relevantFiles"))
        modules = _repo_item_names(repository.get("relevantModules"))
        services = _repo_item_names(repository.get("relevantServices"))
        allowed_terms = relevant_files + modules + services + string_list(repository.get("fileRankingStatus"))
        changed_results: list[dict[str, Any]] = []
        violations = []
        for file in changed_files:
            path = clean(file.get("path"))
            matched = _matched_terms(path, allowed_terms)
            status = "aligned" if matched else ("needs review" if not relevant_files else "unrelated")
            changed_results.append({"path": path, "status": status, "matchedEvidence": matched})
            if status == "unrelated":
                violations.append(
                    violation(
                        rule="repository_alignment",
                        severity="major",
                        message="Changed file is not part of the Execution Package repository evidence.",
                        file_path=path,
                        recommendation="Confirm this file is required, or update repository evidence before merging.",
                    )
                )
            if _looks_like_fake_service(path, repository):
                violations.append(
                    violation(
                        rule="fake_service_risk",
                        severity="major",
                        message="New service-like file is not present in repository evidence.",
                        file_path=path,
                        recommendation="Reuse the closest existing service unless the Execution Package explicitly requires a new one.",
                    )
                )
        if not changed_files:
            score = 0
        elif not relevant_files:
            score = 70
        else:
            aligned = len([item for item in changed_results if item["status"] == "aligned"])
            score = round((aligned / len(changed_results)) * 100)
        return {"score": score, "changedFiles": changed_results, "violations": violations}


def _repo_item_names(value: Any) -> list[str]:
    if isinstance(value, list):
        return [clean(item.get("path") or item.get("name") or item.get("title") or item) for item in value]
    return string_list(value)


def _matched_terms(path: str, terms: list[str]) -> list[str]:
    haystack = path.casefold()
    matches = []
    for term in terms:
        text = clean(term)
        if not text or text == "Repository file ranking not available":
            continue
        compact = text.casefold()
        basename = compact.split("/")[-1]
        tokens = [token for token in basename.replace(".", " ").replace("-", " ").replace("_", " ").split() if len(token) >= 4]
        if compact in haystack or basename in haystack or any(token in haystack for token in tokens):
            matches.append(text)
    return matches


def _looks_like_fake_service(path: str, repository: dict[str, Any]) -> bool:
    status = clean(repository.get("fileRankingStatus")).casefold()
    if "unavailable" not in status:
        return False
    lowered = path.casefold()
    return "service" in lowered and any(marker in lowered for marker in ["new", "fake", "stub"])
