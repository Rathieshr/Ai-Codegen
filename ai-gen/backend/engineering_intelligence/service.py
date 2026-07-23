"""Central orchestration over HEI's existing engineering intelligence providers."""

from __future__ import annotations

import re
from typing import Any, Iterable

from .builder import EngineeringContextBuilder
from .models import (
    ArchitectureSummary,
    AzureDevOpsSummary,
    DependencySummary,
    EngineeringAnalysisResult,
    EngineeringContext,
    EngineeringMemorySummary,
    ImpactSummary,
    RepositoryRecommendation,
    RepositorySummary,
    ReuseSummary,
    SimilaritySummary,
)


class EngineeringIntelligenceService:
    """Builds one canonical context without reimplementing provider intelligence."""

    def __init__(
        self,
        *,
        repository_intelligence: Any | None = None,
        repository_detector: Any | None = None,
        azure_devops: Any | None = None,
        engineering_memory: Any | None = None,
        planning_engine: Any | None = None,
        pull_request_provider: Any | None = None,
        context_builder: EngineeringContextBuilder | None = None,
    ) -> None:
        self.repository_intelligence = repository_intelligence
        self.repository_detector = repository_detector
        self.azure_devops = azure_devops
        self.engineering_memory = engineering_memory
        self.planning_engine = planning_engine
        self.pull_request_provider = pull_request_provider or (lambda _project_id: [])
        self.context_builder = context_builder or EngineeringContextBuilder()

    def analyze_requirement(
        self, requirement: dict[str, Any], analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        analysis = analysis or {}
        return {
            "requirementId": _text(requirement.get("requirementId") or requirement.get("id")),
            "title": _text(requirement.get("title") or analysis.get("title")),
            "planningRequirement": _text(
                analysis.get("planningRequirement")
                or requirement.get("planningRequirement")
                or requirement.get("content")
            ),
            "businessGoals": _strings(analysis.get("businessGoals")),
            "functionalRequirements": _strings(analysis.get("functionalRequirements")),
            "nonFunctionalRequirements": _strings(analysis.get("nonFunctionalRequirements")),
            "acceptanceCriteria": _strings(analysis.get("acceptanceCriteria")),
            "businessRules": _strings(analysis.get("businessRules")),
            "dependencies": _strings(analysis.get("dependencies")),
            "risks": _strings(analysis.get("risks")),
            "constraints": _strings(analysis.get("constraints")),
            "actors": _strings(analysis.get("actors")),
            "assumptions": _strings(analysis.get("assumptions")),
            "openQuestions": _strings(analysis.get("openQuestions")),
            "projectId": _text(
                requirement.get("projectId")
                or requirement.get("metadata", {}).get("projectId")
                or analysis.get("projectId")
            ),
            "contextVersion": requirement.get("contextVersion"),
            "analysisId": analysis.get("analysisId"),
        }

    def analyze_repository(self, requirement: dict[str, Any]) -> RepositorySummary:
        selected = requirement.get("repository") or {}
        repository_id = _text(
            selected.get("repositoryId")
            or requirement.get("repositoryId")
            or requirement.get("metadata", {}).get("repositoryId")
        )
        if not repository_id or not self.repository_intelligence:
            return RepositorySummary(
                repositoryId=repository_id,
                warnings=["No completed Repository Intelligence snapshot is available."],
            )
        repository = self.repository_intelligence.get_repository(repository_id) or {}
        snapshot = self.repository_intelligence.get_current_snapshot(repository_id) or {}
        graph = self.repository_intelligence.get_graph(repository_id) or {}
        nodes = list(graph.get("nodes") or [])
        buckets = _graph_buckets(nodes)
        modules = _unique(_strings(snapshot.get("modules")) + buckets["modules"])
        affected = _relevant_names(_requirement_text(requirement), modules)
        mode = "CodeIndexed" if snapshot else "Unavailable"
        health = _text(repository.get("status")) or ("Healthy" if snapshot else "Unavailable")
        return RepositorySummary(
            repositoryId=repository_id,
            repositoryName=_text(repository.get("name") or selected.get("name")),
            branch=_text(repository.get("defaultBranch") or selected.get("branch") or snapshot.get("branch")),
            mode=mode,
            snapshotId=_text(snapshot.get("snapshotId")),
            repositorySnapshotVersion=_text(snapshot.get("version")),
            modules=modules,
            screens=buckets["screens"],
            services=buckets["services"],
            apiEndpoints=buckets["apis"],
            databaseObjects=buckets["database"],
            sharedComponents=buckets["components"],
            tests=buckets["tests"],
            files=buckets["files"],
            architectureLayer=_unique(
                _strings(graph.get("metadata", {}).get("architectureLayers"))
                + _strings(repository.get("metadata", {}).get("architectureLayers"))
            ),
            repositoryHealth=health,
            affectedModules=affected,
            confidence=92 if snapshot else 20,
            warnings=[] if snapshot else ["The selected repository has no completed snapshot."],
            graph=graph,
        )

    def analyze_azure_devops(self, requirement: dict[str, Any]) -> AzureDevOpsSummary:
        project_id = _text(requirement.get("projectId"))
        if not project_id or not self.azure_devops:
            return AzureDevOpsSummary(projectId=project_id)
        items = [
            _normalize_work_item(item)
            for item in self.azure_devops.cached_collection(project_id, "workItems").values()
            if isinstance(item, dict)
        ]
        iterations = list(self.azure_devops.cached_collection(project_id, "iterations").values())
        pull_requests = list(self.azure_devops.cached_collection(project_id, "pullRequests").values())
        return self._azure_devops_summary(project_id, items, iterations, pull_requests)

    def find_similar_stories(self, value: EngineeringContext | dict[str, Any]) -> list[dict[str, Any]]:
        return self._similar_by_type(value, "Story")

    def find_similar_features(self, value: EngineeringContext | dict[str, Any]) -> list[dict[str, Any]]:
        return self._similar_by_type(value, "Feature")

    def find_similar_epics(self, value: EngineeringContext | dict[str, Any]) -> list[dict[str, Any]]:
        return self._similar_by_type(value, "Epic")

    def find_existing_implementation(
        self, value: EngineeringContext | dict[str, Any],
    ) -> list[dict[str, Any]]:
        context = _context_dict(value)
        repository = context.get("repository") or {}
        reuse = context.get("reuse") or {}
        return _unique_dicts(
            list(reuse.get("implementations") or [])
            + list(repository.get("files") or [])
            + [{"name": name, "type": "Component"} for name in repository.get("sharedComponents") or []]
        )

    def find_repository(self, repository_id: str) -> dict[str, Any] | None:
        if not repository_id or not self.repository_intelligence:
            return None
        return self.repository_intelligence.get_repository(repository_id)

    def get_engineering_memory(self, requirement: dict[str, Any]) -> EngineeringMemorySummary:
        if not self.engineering_memory:
            return EngineeringMemorySummary()
        result = self.engineering_memory.find_relevant_memory({
            "text": _requirement_text(requirement),
            "projectId": _text(requirement.get("projectId")),
            "repository": [
                _text(requirement.get("repositoryId")),
                _text(requirement.get("repository", {}).get("repositoryId")),
            ],
            "limit": 20,
        }) or {}
        return self._memory_summary(list(result.get("results") or []))

    def find_reusable_components(self, value: EngineeringContext | dict[str, Any]) -> list[dict[str, Any]]:
        return list((_context_dict(value).get("reuse") or {}).get("components") or [])

    def find_reusable_tests(self, value: EngineeringContext | dict[str, Any]) -> list[dict[str, Any]]:
        return list((_context_dict(value).get("reuse") or {}).get("tests") or [])

    def find_reusable_prs(self, value: EngineeringContext | dict[str, Any]) -> list[dict[str, Any]]:
        return list((_context_dict(value).get("reuse") or {}).get("pullRequests") or [])

    def analyze_architecture(self, repository: RepositorySummary | dict[str, Any]) -> ArchitectureSummary:
        value = repository if isinstance(repository, dict) else repository.__dict__
        graph = value.get("graph") or {}
        relationships = list(graph.get("relationships") or [])
        return ArchitectureSummary(
            layers=_strings(value.get("architectureLayer")),
            modules=_strings(value.get("modules")),
            services=_strings(value.get("services")),
            interfaces=[
                _text(node.get("name"))
                for node in graph.get("nodes") or []
                if _text(node.get("nodeType")).casefold() in {"dto", "controller", "api"}
            ],
            evidence=relationships[:30],
        )

    def analyze_dependencies(
        self,
        requirement: dict[str, Any],
        repository: RepositorySummary | dict[str, Any],
    ) -> DependencySummary:
        value = repository if isinstance(repository, dict) else repository.__dict__
        graph = value.get("graph") or {}
        relationships = list(graph.get("relationships") or [])
        typed = [
            item for item in relationships
            if _text(item.get("relationshipType")).casefold() in {"depends_on", "references", "uses"}
        ]
        node_map = {
            _text(node.get("nodeId")): node
            for node in graph.get("nodes") or []
            if isinstance(node, dict)
        }
        resolved = [_resolve_relationship(item, node_map) for item in typed]
        return DependencySummary(
            repositoryDependencies=resolved,
            storyDependencies=_strings(requirement.get("dependencies")),
            apiDependencies=[item for item in resolved if "api" in _text(item.get("toType")).casefold()],
            moduleDependencies=[item for item in resolved if "module" in _text(item.get("fromType")).casefold()],
            architectureDependencies=resolved,
        )

    def recommend_repository(
        self,
        requirement: dict[str, Any],
        analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.repository_detector:
            return dict(self.repository_detector.detect_requirement(requirement, analysis or {}))
        repository = self.analyze_repository({**requirement, **(analysis or {})})
        return RepositoryRecommendation(
            suggestedRepository={
                "repositoryId": repository.repositoryId,
                "name": repository.repositoryName,
                "branch": repository.branch,
                "matchedModules": repository.affectedModules,
            } if repository.repositoryId else {},
            confidence=repository.confidence,
            reason="Repository Intelligence snapshot matches the selected engineering workspace."
            if repository.repositoryId else "No repository was selected.",
            signals={"repositoryMode": repository.mode},
        ).__dict__

    def recommend_planning_strategy(
        self, raw_context: dict[str, Any], analysis: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.planning_engine:
            return {
                "mode": "AI_RECOMMENDED",
                "confidence": 35,
                "reason": ["Planning strategy provider is not configured."],
                "recommendedStrategy": {"description": "Review engineering context before planning."},
            }
        return self.planning_engine.recommend(raw_context, analysis)

    def generate_impact_analysis(
        self,
        requirement: dict[str, Any],
        repository: RepositorySummary,
        similarity: SimilaritySummary,
    ) -> ImpactSummary:
        affected_features = [_match_title(item) for item in similarity.existingFeature]
        affected_stories = [_match_title(item) for item in similarity.existingStory]
        complexity_count = len(repository.affectedModules) + len(repository.apiEndpoints) + len(repository.services)
        complexity = "High" if complexity_count > 10 else "Medium" if complexity_count else "Low"
        has_breaking_risk = bool(repository.apiEndpoints and _tokens(_requirement_text(requirement)) & {"change", "replace", "remove"})
        return ImpactSummary(
            affectedFeatures=_unique(affected_features),
            affectedStories=_unique(affected_stories),
            affectedModules=repository.affectedModules,
            affectedApis=repository.apiEndpoints,
            affectedServices=repository.services,
            affectedTests=repository.tests,
            affectedDocumentation=[
                _text(item.get("path") or item.get("name"))
                for item in repository.files
                if _text(item.get("path") or item.get("name")).casefold().endswith((".md", ".txt"))
            ],
            engineeringComplexity=complexity,
            risk="High" if has_breaking_risk else "Medium" if complexity == "High" else "Low",
            potentialRisks=_strings(requirement.get("risks"))
            or (["Validate integration impact during Planning."] if complexity != "Low" else []),
            potentialBreakingChanges=[
                "Existing API contracts require compatibility validation."
            ] if has_breaking_risk else [],
            sprintImpact="Review current sprint capacity." if similarity.matches else "No active planning overlap identified.",
        )

    def generate_planning_context(
        self, requirement_summary: dict[str, Any], *, correlation_id: str = "",
    ) -> dict[str, Any]:
        repository = self.analyze_repository(requirement_summary)
        repository_input = _repository_input(repository)
        if self.planning_engine:
            raw = self.planning_engine.build_context(requirement_summary, repository_input)
            analysis = self.planning_engine.analyze(raw)
            recommendation = self.recommend_planning_strategy(raw, analysis)
            ado = self._azure_devops_from_raw(raw.get("azureDevOps") or {}, requirement_summary)
            memory = self._memory_summary(list(raw.get("engineeringMemory", {}).get("matches") or []))
            similarity = self._similarity_summary(list(analysis.get("similarWork") or []))
        else:
            ado = self.analyze_azure_devops(requirement_summary)
            memory = self.get_engineering_memory(requirement_summary)
            raw = _raw_context(requirement_summary, repository_input, ado, memory)
            analysis = {"similarWork": [], "repositoryMatch": {"confidence": repository.confidence}}
            recommendation = self.recommend_planning_strategy(raw, analysis)
            similarity = SimilaritySummary()
        architecture = self.analyze_architecture(repository)
        dependencies = self.analyze_dependencies(requirement_summary, repository)
        impact = self.generate_impact_analysis(requirement_summary, repository, similarity)
        reuse = ReuseSummary(
            components=_named_items(repository.sharedComponents, "Component"),
            apis=_named_items(repository.apiEndpoints, "API"),
            tests=_named_items(repository.tests, "Test"),
            pullRequests=ado.openPullRequests,
            implementations=repository.files,
        )
        repo_recommendation = _recommendation_from_summary(repository)
        readiness = _readiness(requirement_summary, repository, memory, similarity)
        context = self.context_builder.build(
            requirement=_canonical_requirement(requirement_summary),
            repository=repository,
            azure_devops=ado,
            memory=memory,
            similarity=similarity,
            architecture=architecture,
            dependencies=dependencies,
            repository_recommendation=repo_recommendation,
            planning_recommendation=recommendation,
            impact=impact,
            reuse=reuse,
            readiness=readiness,
            correlation_id=correlation_id or _text(requirement_summary.get("correlationId")),
        )
        # Preserve the established planning lineage while it remains the
        # persisted compatibility contract. Both IDs are source-version based.
        if raw.get("contextId") and raw.get("contextVersion"):
            context.contextId = _text(raw.get("contextId"))
            context.contextVersion = _text(raw.get("contextVersion"))
        raw.setdefault("azureDevOps", {})["openPullRequests"] = ado.openPullRequests
        raw["contextId"] = context.contextId
        raw["contextVersion"] = context.contextVersion
        recommendation["contextId"] = context.contextId
        return EngineeringAnalysisResult(
            context=context,
            rawContext=raw,
            analysis=analysis,
            planningRecommendationInput=recommendation,
        ).to_dict()

    def from_planning_context(self, planning_context: dict[str, Any]) -> dict[str, Any]:
        canonical = planning_context.get("engineeringContext")
        if isinstance(canonical, dict):
            memory = canonical.get("engineeringMemory") or {}
            similarity = canonical.get("similarWork") or {}
            repository = canonical.get("repository") or {}
            impact = canonical.get("impact") or {}
            planning_input = canonical.get("planningRecommendationInput") or {}
            summary = canonical.get("summary") or {}
            return {
                **canonical,
                "repository": {
                    **repository,
                    "snapshotVersion": repository.get("repositorySnapshotVersion"),
                    "affectedServices": repository.get("services") or [],
                    "affectedApis": repository.get("apiEndpoints") or [],
                    "affectedScreens": repository.get("screens") or [],
                    "reusableComponents": repository.get("sharedComponents") or [],
                    "reusableTests": repository.get("tests") or [],
                    "reusePercent": min(
                        95,
                        len(repository.get("sharedComponents") or []) * 12
                        + len(repository.get("apiEndpoints") or []) * 8
                        + len(repository.get("tests") or []) * 5,
                    ),
                },
                "memory": memory,
                "similarWork": [_planning_similarity(item) for item in similarity.get("matches") or []],
                "classification": {
                    "value": planning_input.get("mode") or "AI_RECOMMENDED",
                    "confidence": planning_input.get("confidence") or 0,
                    "reason": " ".join(_strings(planning_input.get("reason"))),
                },
                "impact": {
                    **impact,
                    "complexity": impact.get("engineeringComplexity") or "Medium",
                },
                "summary": {
                    **summary,
                    "currentProject": summary.get("project"),
                    "engineeringRisk": summary.get("risk"),
                    "estimatedComplexity": summary.get("engineeringComplexity"),
                    "planningConfidence": planning_input.get("confidence") or 0,
                },
                "recommendation": planning_context.get("recommendation")
                or planning_input
                or {},
                "requirementId": planning_context.get("requirementId")
                or canonical.get("requirement", {}).get("requirementId"),
                "projectId": planning_context.get("projectId")
                or canonical.get("requirement", {}).get("projectId"),
            }
        repository = planning_context.get("repository") or {}
        memory = planning_context.get("memory") or {}
        return {
            "contextId": planning_context.get("contextId"),
            "contextVersion": planning_context.get("contextVersion"),
            "requirement": planning_context.get("requirement") or {},
            "repository": repository,
            "azureDevOps": planning_context.get("azureDevOps") or {},
            "engineeringMemory": memory,
            "memory": memory,
            "similarWork": planning_context.get("similarWork") or [],
            "architecture": planning_context.get("architecture") or {},
            "dependencies": planning_context.get("dependencies") or {},
            "impact": planning_context.get("impact") or {},
            "reuse": planning_context.get("reuse") or {},
            "readiness": planning_context.get("readiness") or {},
            "summary": planning_context.get("summary") or {},
            "recommendation": planning_context.get("recommendation") or {},
            "requirementId": planning_context.get("requirementId"),
            "projectId": planning_context.get("projectId"),
        }

    def execution_context(self, value: EngineeringContext | dict[str, Any]) -> dict[str, Any]:
        context = _context_dict(value)
        repository = context.get("repository") or {}
        reuse = context.get("reuse") or {}
        return {
            "engineeringContextId": context.get("contextId"),
            "engineeringContextVersion": context.get("contextVersion"),
            "relevantFiles": list(repository.get("files") or []),
            "relevantApis": list(repository.get("apiEndpoints") or []),
            "relevantTests": list(repository.get("tests") or []),
            "relevantPullRequests": list(reuse.get("pullRequests") or []),
            "relevantRepositoryModules": list(repository.get("affectedModules") or repository.get("modules") or []),
            "architecture": context.get("architecture") or {},
            "dependencies": context.get("dependencies") or {},
        }

    def validation_context(self, value: EngineeringContext | dict[str, Any]) -> dict[str, Any]:
        context = _context_dict(value)
        repository = context.get("repository") or {}
        impact = context.get("impact") or {}
        similarity = context.get("similarWork") or {}
        return {
            "engineeringContextId": context.get("contextId"),
            "engineeringContextVersion": context.get("contextVersion"),
            "affectedTests": list(impact.get("affectedTests") or repository.get("tests") or []),
            "affectedComponents": list(repository.get("sharedComponents") or []),
            "affectedStories": list(impact.get("affectedStories") or similarity.get("existingStory") or []),
            "affectedApis": list(impact.get("affectedApis") or repository.get("apiEndpoints") or []),
            "impactAnalysis": impact,
        }

    def planning_engine_context(self, value: EngineeringContext | dict[str, Any]) -> dict[str, Any]:
        context = self.from_planning_context(value) if isinstance(value, dict) else value.to_dict()
        repository = context.get("repository") or {}
        azure_devops = context.get("azureDevOps") or {}
        memory = context.get("engineeringMemory") or context.get("memory") or {}
        return {
            "schemaVersion": "hei-planning-context-v1",
            "contextId": context.get("contextId"),
            "contextVersion": context.get("contextVersion"),
            "requirement": context.get("requirement") or {},
            "projectId": context.get("projectId") or (context.get("requirement") or {}).get("projectId"),
            "repository": {
                "mode": repository.get("mode"),
                "repositoryId": repository.get("repositoryId"),
                "repositoryName": repository.get("repositoryName"),
                "branch": repository.get("branch"),
                "snapshotId": repository.get("snapshotId"),
                "repositorySnapshotVersion": repository.get("repositorySnapshotVersion")
                or repository.get("snapshotVersion"),
                "modules": repository.get("modules") or [],
                "graph": repository.get("graph") or {},
                "warnings": repository.get("warnings") or [],
            },
            "azureDevOps": {
                "source": azure_devops.get("source"),
                "workItems": azure_devops.get("existingPlanning")
                or azure_devops.get("workItems")
                or [],
                "currentIterations": [azure_devops.get("currentIteration")]
                if azure_devops.get("currentIteration")
                else azure_devops.get("iterations") or [],
                "openPullRequests": azure_devops.get("openPullRequests") or [],
            },
            "engineeringMemory": {
                "matches": memory.get("matches") or [],
                "count": len(memory.get("matches") or []),
            },
            "generatedAt": context.get("generatedAt"),
        }

    # Public names from the V1 service contract.
    analyzeRequirement = analyze_requirement
    analyzeRepository = analyze_repository
    analyzeAzureDevOps = analyze_azure_devops
    findSimilarStories = find_similar_stories
    findSimilarFeatures = find_similar_features
    findSimilarEpics = find_similar_epics
    findExistingImplementation = find_existing_implementation
    findRepository = find_repository
    getEngineeringMemory = get_engineering_memory
    findReusableComponents = find_reusable_components
    findReusableTests = find_reusable_tests
    findReusablePRs = find_reusable_prs
    analyzeArchitecture = analyze_architecture
    analyzeDependencies = analyze_dependencies
    recommendRepository = recommend_repository
    recommendPlanningStrategy = recommend_planning_strategy
    generateImpactAnalysis = generate_impact_analysis
    generatePlanningContext = generate_planning_context

    def _similar_by_type(
        self, value: EngineeringContext | dict[str, Any], artifact_type: str,
    ) -> list[dict[str, Any]]:
        similar = (_context_dict(value).get("similarWork") or {})
        if isinstance(similar, list):
            matches = similar
        else:
            matches = similar.get(f"existing{artifact_type}") or similar.get("matches") or []
        return [
            item for item in matches
            if _match_type(item).casefold() == artifact_type.casefold()
        ]

    @staticmethod
    def _memory_summary(matches: list[dict[str, Any]]) -> EngineeringMemorySummary:
        def selected(*terms: str) -> list[dict[str, Any]]:
            return [
                item for item in matches
                if any(term in _memory_kind(item) for term in terms)
            ]

        return EngineeringMemorySummary(
            matches=matches,
            similarStories=selected("story"),
            similarFeatures=selected("feature"),
            similarPullRequests=selected("pull", "pr"),
            similarBugs=selected("bug"),
            reusableComponents=selected("component"),
            reusableApis=selected("api"),
            reusableTests=selected("test"),
            architectureDecisions=selected("architecture", "decision"),
            previousPlanningPacks=selected("planning"),
            lessonsLearned=selected("lesson"),
            coverage=min(100, len(matches) * 12),
        )

    @staticmethod
    def _similarity_summary(matches: list[dict[str, Any]]) -> SimilaritySummary:
        return SimilaritySummary(
            existingEpic=[item for item in matches if _match_type(item) == "Epic"],
            existingFeature=[item for item in matches if _match_type(item) == "Feature"],
            existingStory=[item for item in matches if _match_type(item) == "Story"],
            matches=matches,
        )

    def _azure_devops_from_raw(
        self, raw: dict[str, Any], requirement: dict[str, Any],
    ) -> AzureDevOpsSummary:
        items = list(raw.get("workItems") or [])
        iterations = list(raw.get("currentIterations") or [])
        pull_requests = list(self.pull_request_provider(_text(requirement.get("projectId"))) or [])
        return self._azure_devops_summary(
            _text(requirement.get("projectId")), items, iterations, pull_requests,
        )

    @staticmethod
    def _azure_devops_summary(
        project_id: str,
        items: list[dict[str, Any]],
        iterations: list[dict[str, Any]],
        pull_requests: list[dict[str, Any]],
    ) -> AzureDevOpsSummary:
        by_type = {
            kind: [item for item in items if _text(item.get("type") or item.get("workItemType")) == kind]
            for kind in ("Epic", "Feature", "Story", "Task", "Bug")
        }
        current = next(
            (item for item in iterations if _text(item.get("timeFrame")).casefold() == "current"),
            iterations[0] if iterations else {},
        )
        parents = [
            {"parentId": _text(item.get("parentId")), "childId": _text(item.get("id"))}
            for item in items if item.get("parentId")
        ]
        return AzureDevOpsSummary(
            projectId=project_id,
            epics=by_type["Epic"],
            features=by_type["Feature"],
            stories=by_type["Story"],
            tasks=by_type["Task"],
            bugs=by_type["Bug"],
            currentSprint=current,
            currentIteration=current,
            currentAreaPath=next((_text(item.get("areaPath")) for item in items if item.get("areaPath")), ""),
            parentRelationships=parents,
            childRelationships=parents,
            existingPlanning=items,
            storyStatus=_count_by(items, "state"),
            currentAssignments=_unique([_text(item.get("assignedTo")) for item in items]),
            openPullRequests=[
                item for item in pull_requests
                if _text(item.get("status") or item.get("state")).casefold()
                not in {"completed", "abandoned", "merged", "closed"}
            ],
            currentDevelopment=[
                item for item in items
                if _text(item.get("state")).casefold() in {"active", "in progress", "committed", "doing"}
            ],
        )


def _repository_input(value: RepositorySummary) -> dict[str, Any]:
    return {
        "mode": value.mode,
        "repositoryId": value.repositoryId,
        "repositoryName": value.repositoryName,
        "branch": value.branch,
        "snapshotId": value.snapshotId,
        "repositorySnapshotVersion": value.repositorySnapshotVersion,
        "modules": value.modules,
        "graph": value.graph,
        "warnings": value.warnings,
    }


def _raw_context(
    requirement: dict[str, Any],
    repository: dict[str, Any],
    ado: AzureDevOpsSummary,
    memory: EngineeringMemorySummary,
) -> dict[str, Any]:
    return {
        "requirement": _canonical_requirement(requirement),
        "projectId": requirement.get("projectId"),
        "repository": repository,
        "azureDevOps": {
            "source": ado.source,
            "workItems": ado.existingPlanning,
            "currentIterations": [ado.currentIteration] if ado.currentIteration else [],
        },
        "engineeringMemory": {"matches": memory.matches, "count": len(memory.matches)},
    }


def _canonical_requirement(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _text(value.get("requirementId") or value.get("id")),
        "requirementId": _text(value.get("requirementId") or value.get("id")),
        "title": _text(value.get("title")),
        "planningRequirement": _text(value.get("planningRequirement") or value.get("content")),
        "businessGoals": _strings(value.get("businessGoals")),
        "functionalRequirements": _strings(value.get("functionalRequirements")),
        "nonFunctionalRequirements": _strings(value.get("nonFunctionalRequirements")),
        "acceptanceCriteria": _strings(value.get("acceptanceCriteria")),
        "businessRules": _strings(value.get("businessRules")),
        "dependencies": _strings(value.get("dependencies")),
        "risks": _strings(value.get("risks")),
        "constraints": _strings(value.get("constraints")),
        "actors": _strings(value.get("actors")),
        "assumptions": _strings(value.get("assumptions")),
        "openQuestions": _strings(value.get("openQuestions")),
        "projectId": _text(value.get("projectId")),
        "projectName": _text(value.get("projectName")),
        "contextVersion": value.get("contextVersion"),
        "analysisId": value.get("analysisId"),
    }


def _recommendation_from_summary(repository: RepositorySummary) -> RepositoryRecommendation:
    return RepositoryRecommendation(
        suggestedRepository={
            "repositoryId": repository.repositoryId,
            "name": repository.repositoryName,
            "branch": repository.branch,
            "matchedModules": repository.affectedModules,
        } if repository.repositoryId else {},
        confidence=repository.confidence,
        reason="Repository Intelligence snapshot supports the selected repository."
        if repository.repositoryId else "No repository is available.",
        signals={"mode": repository.mode, "snapshotVersion": repository.repositorySnapshotVersion},
    )


def _readiness(
    requirement: dict[str, Any],
    repository: RepositorySummary,
    memory: EngineeringMemorySummary,
    similarity: SimilaritySummary,
) -> dict[str, Any]:
    quality = int(requirement.get("qualityScore") or 60)
    blockers = _strings((requirement.get("planningReadiness") or {}).get("blockers"))
    warnings = _strings((requirement.get("planningReadiness") or {}).get("warnings")) + repository.warnings
    if blockers:
        status = "Blocked"
    elif similarity.matches and _match_score(similarity.matches[0]) >= 78:
        status = "NeedsUserDecision"
        warnings.append("Similar existing work requires an explicit planning decision.")
    elif warnings or repository.mode == "Unavailable":
        status = "ReadyWithRecommendations"
    else:
        status = "Ready"
    score = round(quality * 0.4 + repository.confidence * 0.35 + memory.coverage * 0.15 + 60 * 0.1)
    return {
        "status": status,
        "score": score,
        "repositoryCoverage": repository.confidence,
        "memoryCoverage": memory.coverage,
        "requirementCompleteness": quality,
        "existingWorkMatch": _match_score(similarity.matches[0]) if similarity.matches else 0,
        "blockers": _unique(blockers),
        "warnings": _unique(warnings),
    }


def _graph_buckets(nodes: Iterable[dict[str, Any]]) -> dict[str, list[Any]]:
    buckets: dict[str, list[Any]] = {
        "modules": [], "screens": [], "services": [], "apis": [],
        "database": [], "components": [], "tests": [], "files": [],
    }
    mapping = {
        "module": "modules", "ui": "screens", "screen": "screens",
        "service": "services", "api": "apis", "controller": "apis",
        "databaseentity": "database", "entity": "database",
        "dto": "components", "viewmodel": "components", "test": "tests",
    }
    for node in nodes:
        kind = _text(node.get("nodeType") or node.get("type")).casefold()
        name = _text(node.get("name"))
        if kind == "file":
            buckets["files"].append({
                "path": _text(node.get("path") or name),
                "name": name,
                "confidence": int(node.get("confidence") or 100),
                "reason": "Repository Intelligence graph evidence.",
                "source": "Repository Intelligence",
            })
            continue
        bucket = mapping.get(kind)
        if bucket and name:
            buckets[bucket].append(name)
    for key in buckets:
        buckets[key] = _unique_dicts(buckets[key]) if key == "files" else _unique(buckets[key])
    return buckets


def _resolve_relationship(value: dict[str, Any], nodes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    source = nodes.get(_text(value.get("fromNodeId"))) or {}
    target = nodes.get(_text(value.get("toNodeId"))) or {}
    return {
        "from": _text(source.get("name") or value.get("fromNodeId")),
        "fromType": _text(source.get("nodeType")),
        "to": _text(target.get("name") or value.get("toNodeId")),
        "toType": _text(target.get("nodeType")),
        "type": _text(value.get("relationshipType")),
        "source": "Repository Intelligence Engineering Graph",
    }


def _normalize_work_item(item: dict[str, Any]) -> dict[str, Any]:
    kind = _text(item.get("workItemType") or item.get("type"))
    if kind.casefold() in {"user story", "product backlog item", "pbi"}:
        kind = "Story"
    return {
        **item,
        "id": _text(item.get("workItemId") or item.get("id")),
        "type": kind,
        "title": _text(item.get("title")),
        "revision": int(item.get("revision") or item.get("rev") or 0),
        "parentId": _text(item.get("parentId") or item.get("parentWorkItemId")),
        "assignedTo": _text(item.get("assignedTo") or item.get("assignedUser")),
    }


def _memory_kind(value: dict[str, Any]) -> str:
    return " ".join([
        _text(value.get("category")),
        _text(value.get("artifactType")),
        _text(value.get("title")),
    ]).casefold()


def _match_type(value: dict[str, Any]) -> str:
    return _text((value.get("workItem") or {}).get("type") or value.get("workItemType") or value.get("type"))


def _match_title(value: dict[str, Any]) -> str:
    return _text((value.get("workItem") or {}).get("title") or value.get("title"))


def _match_score(value: dict[str, Any]) -> int:
    score = float(value.get("confidence") or value.get("similarity") or 0)
    return round(score * 100 if score <= 1 else score)


def _planning_similarity(value: dict[str, Any]) -> dict[str, Any]:
    score = _match_score(value)
    work_item = value.get("workItem") or {}
    if score >= 78:
        action = "Modify"
    elif score >= 55:
        action = "Reuse"
    else:
        action = "Create New"
    return {
        "workItemId": _text(work_item.get("id") or value.get("workItemId")),
        "workItemType": _text(work_item.get("type") or value.get("workItemType")),
        "title": _text(work_item.get("title") or value.get("title")),
        "similarity": score,
        "confidence": score,
        "reason": _text(value.get("reason")),
        "suggestedAction": action,
        "state": _text(work_item.get("state") or value.get("state")),
        "workItem": work_item,
    }


def _requirement_text(value: dict[str, Any]) -> str:
    return " ".join([
        _text(value.get("title")),
        _text(value.get("planningRequirement") or value.get("content")),
        *_strings(value.get("businessGoals")),
        *_strings(value.get("functionalRequirements")),
        *_strings(value.get("acceptanceCriteria")),
    ])


def _relevant_names(text: str, names: list[str]) -> list[str]:
    tokens = _tokens(text)
    matched = [name for name in names if _tokens(name) & tokens]
    return matched or names[:8]


def _tokens(value: Any) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", _text(value).casefold())
        if len(token) > 2
    }


def _named_items(values: list[str], kind: str) -> list[dict[str, Any]]:
    return [{"name": value, "type": kind, "source": "Repository Intelligence"} for value in values]


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in items:
        value = _text(item.get(key)) or "Unknown"
        result[value] = result.get(value, 0) + 1
    return result


def _context_dict(value: EngineeringContext | dict[str, Any]) -> dict[str, Any]:
    return value.to_dict() if isinstance(value, EngineeringContext) else value


def _unique(values: Iterable[Any]) -> list[Any]:
    result = []
    seen = set()
    for value in values:
        if value in (None, ""):
            continue
        marker = str(value).casefold()
        if marker not in seen:
            seen.add(marker)
            result.append(value)
    return result


def _unique_dicts(values: Iterable[Any]) -> list[Any]:
    result = []
    seen = set()
    for value in values:
        marker = str(sorted(value.items())) if isinstance(value, dict) else str(value)
        if marker not in seen:
            seen.add(marker)
            result.append(value)
    return result


def _strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    return [_text(value)] if _text(value) else []


def _text(value: Any) -> str:
    return str(value or "").strip()
