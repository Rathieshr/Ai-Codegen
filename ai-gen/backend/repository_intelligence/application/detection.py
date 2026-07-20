"""Evidence-based repository detection for normalized requirements."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.platform.shared import JsonMapStore


_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "into",
    "is", "it", "of", "on", "or", "that", "the", "their", "this", "to", "use", "user",
    "users", "with", "will", "should", "must", "can", "provide", "support", "system",
}


class RepositoryDetectionService:
    """Ranks registered repositories without inventing repository evidence."""

    def __init__(
        self,
        *,
        repository_service: Any,
        snapshot_service: Any,
        memory_engine: Any,
        suggestion_store: JsonMapStore,
        override_store: JsonMapStore,
        requirement_ingestion: Any | None = None,
    ) -> None:
        self.repository_service = repository_service
        self.snapshot_service = snapshot_service
        self.memory_engine = memory_engine
        self.suggestion_store = suggestion_store
        self.override_store = override_store
        self.requirement_ingestion = requirement_ingestion

    def detect(self, request: dict[str, Any]) -> dict[str, Any]:
        requirement_id = _text(request.get("requirementId"))
        project_id = _text(request.get("projectId"))
        workspace_repository_id = _text(
            request.get("currentWorkspaceRepositoryId") or request.get("workspaceRepositoryId")
        )
        text = "\n".join(
            _strings(
                request.get("title"), request.get("content"), request.get("planningRequirement"),
                request.get("businessGoals"), request.get("functionalRequirements"),
                request.get("nonFunctionalRequirements"), request.get("acceptanceCriteria"),
                request.get("businessDomain"), request.get("domain"), request.get("keywords"),
                request.get("technologies"), request.get("modules"),
            )
        )
        terms = _terms(text)
        explicit_technologies = _normalized_values(request.get("technologies"))
        explicit_modules = _normalized_values(request.get("modules"))
        repositories = [
            repository for repository in self.repository_service.list_repositories()
            if getattr(getattr(repository, "status", None), "value", "") != "Disabled"
        ]
        memory = self._memory_context(project_id, text)
        overrides = self.override_store.read()
        prior_override = overrides.get(requirement_id) if requirement_id else None

        ranked = [
            self._rank_repository(
                repository,
                terms=terms,
                technologies=explicit_technologies,
                modules=explicit_modules,
                project_id=project_id,
                workspace_repository_id=workspace_repository_id,
                memory_results=memory,
                learned_overrides=list(overrides.values()),
            )
            for repository in repositories
        ]
        ranked.sort(key=lambda item: (item["score"], item["name"].lower()), reverse=True)

        source = "Detection"
        if isinstance(prior_override, dict):
            overridden_id = _text(prior_override.get("repositoryId"))
            selected = next((item for item in ranked if item["repositoryId"] == overridden_id), None)
            if selected:
                ranked.remove(selected)
                selected = {
                    **selected,
                    "confidence": 1.0,
                    "reason": f"Selected by {_text(prior_override.get('actor')) or 'a user'} as the repository for this requirement.",
                    "evidence": ["Manual repository override", *selected["evidence"]],
                    "manualOverride": True,
                }
                ranked.insert(0, selected)
                source = "ManualOverride"

        selected = self._public_candidate(ranked[0]) if ranked else None
        alternatives = [self._public_candidate(item) for item in ranked[1:4]]
        result = {
            "detectionId": f"repository_detection_{uuid4().hex}",
            "requirementId": requirement_id,
            "suggestedRepository": selected,
            "confidence": selected.get("confidence", 0.0) if selected else 0.0,
            "reason": selected.get("reason", "No registered repositories are available for detection.") if selected else "No registered repositories are available for detection.",
            "alternativeRepositories": alternatives,
            "availableRepositories": [self._public_candidate(item) for item in ranked],
            "signals": {
                "keywords": sorted(terms)[:30],
                "technologies": sorted(explicit_technologies),
                "modules": sorted(explicit_modules),
                "azureDevOpsProject": project_id,
                "currentWorkspaceRepositoryId": workspace_repository_id,
                "engineeringMemoryMatches": len(memory),
            },
            "source": source,
            "detectedAt": _now(),
            "_input": dict(request),
        }
        key = requirement_id or result["detectionId"]
        values = self.suggestion_store.read()
        values[key] = result
        self.suggestion_store.write(values)
        return self._public_result(result)

    def detect_requirement(self, requirement: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
        metadata = requirement.get("metadata") if isinstance(requirement.get("metadata"), dict) else {}
        attributes = metadata.get("attributes") if isinstance(metadata.get("attributes"), dict) else {}
        return self.detect({
            "requirementId": requirement.get("requirementId"),
            "projectId": metadata.get("projectId"),
            "title": requirement.get("title"),
            "content": analysis.get("planningRequirement") or requirement.get("normalizedRequirement"),
            "businessGoals": analysis.get("businessGoals"),
            "functionalRequirements": analysis.get("functionalRequirements"),
            "nonFunctionalRequirements": analysis.get("nonFunctionalRequirements"),
            "acceptanceCriteria": analysis.get("acceptanceCriteria"),
            "technologies": attributes.get("technologies"),
            "modules": attributes.get("modules"),
            "businessDomain": attributes.get("businessDomain") or attributes.get("domain"),
            "keywords": attributes.get("keywords"),
            "currentWorkspaceRepositoryId": metadata.get("repositoryId"),
        })

    def suggestions(self, *, requirement_id: str = "", project_id: str = "") -> dict[str, Any]:
        values = [self._public_result(item) for item in self.suggestion_store.read().values() if isinstance(item, dict)]
        if requirement_id:
            values = [item for item in values if item.get("requirementId") == requirement_id]
        if project_id:
            values = [item for item in values if item.get("signals", {}).get("azureDevOpsProject") == project_id]
        values.sort(key=lambda item: item.get("detectedAt", ""), reverse=True)
        return {"suggestions": values, "count": len(values)}

    def override(self, requirement_id: str, request: dict[str, Any]) -> dict[str, Any]:
        repository_id = _text(request.get("repositoryId"))
        repository = self.repository_service.get_repository(repository_id)
        if not repository:
            raise ValueError("The selected repository is not registered in Repository Intelligence.")
        stored = self.suggestion_store.read().get(requirement_id)
        if not isinstance(stored, dict):
            raise ValueError("Run repository detection before overriding the recommendation.")
        record = {
            "requirementId": requirement_id,
            "repositoryId": repository.repository_id,
            "repositoryName": repository.name,
            "actor": _text(request.get("actor")) or "HEI User",
            "reason": _text(request.get("reason")) or "Manual repository selection",
            "keywords": list(stored.get("signals", {}).get("keywords") or []),
            "previousRepositoryId": _text((stored.get("suggestedRepository") or {}).get("repositoryId")),
            "overriddenAt": _now(),
        }
        overrides = self.override_store.read()
        overrides[requirement_id] = record
        self.override_store.write(overrides)
        if self.requirement_ingestion:
            self.requirement_ingestion.update_repository(
                requirement_id,
                repository_id=repository.repository_id,
                repository_name=repository.name,
                actor=record["actor"],
            )
        detection_input = dict(stored.get("_input") or {})
        detection_input["requirementId"] = requirement_id
        detection_input["currentWorkspaceRepositoryId"] = repository.repository_id
        result = self.detect(detection_input)
        return {"override": record, "suggestion": result}

    def _rank_repository(
        self,
        repository: Any,
        *,
        terms: set[str],
        technologies: set[str],
        modules: set[str],
        project_id: str,
        workspace_repository_id: str,
        memory_results: list[dict[str, Any]],
        learned_overrides: list[Any],
    ) -> dict[str, Any]:
        snapshot = self.snapshot_service.get_latest_snapshot(repository.repository_id)
        snapshot_modules = list(snapshot.modules) if snapshot else []
        snapshot_languages = list(snapshot.languages) if snapshot else []
        metadata = repository.metadata if isinstance(repository.metadata, dict) else {}
        corpus_values = _strings(
            repository.name, repository.url, repository.project_id, metadata,
            snapshot_modules, snapshot_languages,
        )
        corpus = _terms(" ".join(corpus_values))
        keyword_overlap = sorted(terms & corpus)
        module_matches = sorted(value for value in snapshot_modules if _terms(value) & terms or value.lower() in modules)
        language_matches = sorted(value for value in snapshot_languages if value.lower() in technologies or value.lower() in terms)
        score = min(36.0, len(keyword_overlap) * 4.0)
        evidence: list[str] = []
        reasons: list[str] = []
        if keyword_overlap:
            evidence.append(f"Keyword match: {', '.join(keyword_overlap[:8])}")
            reasons.append("requirement keywords match repository metadata")
        if module_matches:
            score += min(28.0, len(module_matches) * 9.0)
            evidence.append(f"Module match: {', '.join(module_matches[:5])}")
            reasons.append("existing modules support the requested capability")
        if language_matches:
            score += min(16.0, len(language_matches) * 8.0)
            evidence.append(f"Technology match: {', '.join(language_matches[:5])}")
            reasons.append("technology aligns with the repository snapshot")
        if project_id and repository.project_id and repository.project_id.lower() == project_id.lower():
            score += 24.0
            evidence.append("Azure DevOps project match")
            reasons.append("repository belongs to the current Azure DevOps project")
        if workspace_repository_id and repository.repository_id == workspace_repository_id:
            score += 12.0
            evidence.append("Current workspace repository")
            reasons.append("repository is active in the current workspace")

        memory_matches = 0
        for memory in memory_results:
            index = memory.get("index") if isinstance(memory.get("index"), dict) else {}
            memory_repositories = {str(value).lower() for value in index.get("repository", [])}
            if repository.repository_id.lower() in memory_repositories or repository.name.lower() in memory_repositories:
                memory_matches += 1
        if memory_matches:
            score += min(14.0, memory_matches * 5.0)
            evidence.append(f"Engineering Memory: {memory_matches} relevant approved item(s)")
            reasons.append("validated Engineering Memory links similar work to this repository")

        learned_matches = 0
        for override in learned_overrides:
            if not isinstance(override, dict) or _text(override.get("repositoryId")) != repository.repository_id:
                continue
            learned_terms = {str(value).lower() for value in override.get("keywords") or []}
            if terms & learned_terms:
                learned_matches += 1
        if learned_matches:
            score += min(10.0, learned_matches * 3.0)
            evidence.append(f"Prior override learning: {learned_matches} similar selection(s)")
            reasons.append("users previously selected this repository for similar requirements")
        if snapshot:
            score += 2.0
            evidence.append(f"Repository Snapshot v{snapshot.version} available")
        confidence = round(min(0.98, 0.28 + score / 120.0), 2) if score else 0.2
        reason = "; ".join(reasons[:3]) if reasons else "Registered repository with no strong requirement match."
        return {
            "repositoryId": repository.repository_id,
            "name": repository.name,
            "url": repository.url,
            "defaultBranch": repository.default_branch,
            "repositoryType": repository.repository_type.value,
            "projectId": repository.project_id,
            "confidence": confidence,
            "score": round(score, 2),
            "reason": reason[0].upper() + reason[1:] if reason else reason,
            "evidence": evidence or ["Repository is registered; no matching indexed evidence was found."],
            "matchedModules": module_matches,
            "matchedTechnologies": language_matches,
            "snapshotVersion": f"v{snapshot.version}" if snapshot else "Unavailable",
            "memoryMatches": memory_matches,
        }

    def _memory_context(self, project_id: str, text: str) -> list[dict[str, Any]]:
        try:
            result = self.memory_engine.find_relevant_memory({"projectId": project_id, "text": text, "limit": 20})
            return [item for item in result.get("results") or [] if isinstance(item, dict)]
        except (AttributeError, TypeError, ValueError):
            return []

    @staticmethod
    def _public_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in candidate.items() if key != "score"}

    @staticmethod
    def _public_result(result: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in result.items() if key != "_input"}


def _strings(*values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        if isinstance(value, dict):
            result.extend(_strings(*value.keys(), *value.values()))
        elif isinstance(value, (list, tuple, set)):
            result.extend(_strings(*value))
        elif value is not None and str(value).strip():
            result.append(str(value).strip())
    return result


def _normalized_values(value: Any) -> set[str]:
    return {item.lower() for item in _strings(value)}


def _terms(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]{2,}", value.lower())
        if token not in _STOP_WORDS
    }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
