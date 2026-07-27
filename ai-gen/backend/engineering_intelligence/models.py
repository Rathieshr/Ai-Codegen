"""Canonical models shared by HEI intelligence consumers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RepositorySummary:
    repositoryId: str = ""
    repositoryName: str = ""
    branch: str = ""
    mode: str = "Unavailable"
    snapshotId: str = ""
    repositorySnapshotVersion: str = ""
    modules: list[str] = field(default_factory=list)
    screens: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    apiEndpoints: list[str] = field(default_factory=list)
    databaseObjects: list[str] = field(default_factory=list)
    sharedComponents: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)
    architectureLayer: list[str] = field(default_factory=list)
    repositoryHealth: str = "Unavailable"
    affectedModules: list[str] = field(default_factory=list)
    confidence: int = 0
    warnings: list[str] = field(default_factory=list)
    graph: dict[str, Any] = field(default_factory=dict)


@dataclass
class AzureDevOpsSummary:
    projectId: str = ""
    epics: list[dict[str, Any]] = field(default_factory=list)
    features: list[dict[str, Any]] = field(default_factory=list)
    stories: list[dict[str, Any]] = field(default_factory=list)
    tasks: list[dict[str, Any]] = field(default_factory=list)
    bugs: list[dict[str, Any]] = field(default_factory=list)
    currentSprint: dict[str, Any] = field(default_factory=dict)
    currentIteration: dict[str, Any] = field(default_factory=dict)
    currentAreaPath: str = ""
    parentRelationships: list[dict[str, str]] = field(default_factory=list)
    childRelationships: list[dict[str, str]] = field(default_factory=list)
    existingPlanning: list[dict[str, Any]] = field(default_factory=list)
    storyStatus: dict[str, int] = field(default_factory=dict)
    currentAssignments: list[str] = field(default_factory=list)
    openPullRequests: list[dict[str, Any]] = field(default_factory=list)
    currentDevelopment: list[dict[str, Any]] = field(default_factory=list)
    source: str = "HEI Platform SDK synchronized cache"


@dataclass
class EngineeringMemorySummary:
    matches: list[dict[str, Any]] = field(default_factory=list)
    similarStories: list[dict[str, Any]] = field(default_factory=list)
    similarFeatures: list[dict[str, Any]] = field(default_factory=list)
    similarPullRequests: list[dict[str, Any]] = field(default_factory=list)
    similarBugs: list[dict[str, Any]] = field(default_factory=list)
    reusableComponents: list[dict[str, Any]] = field(default_factory=list)
    reusableApis: list[dict[str, Any]] = field(default_factory=list)
    reusableTests: list[dict[str, Any]] = field(default_factory=list)
    architectureDecisions: list[dict[str, Any]] = field(default_factory=list)
    previousPlanningPacks: list[dict[str, Any]] = field(default_factory=list)
    lessonsLearned: list[dict[str, Any]] = field(default_factory=list)
    coverage: int = 0


@dataclass
class SimilaritySummary:
    existingEpic: list[dict[str, Any]] = field(default_factory=list)
    existingFeature: list[dict[str, Any]] = field(default_factory=list)
    existingStory: list[dict[str, Any]] = field(default_factory=list)
    matches: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ArchitectureSummary:
    layers: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    interfaces: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DependencySummary:
    repositoryDependencies: list[dict[str, Any]] = field(default_factory=list)
    storyDependencies: list[str] = field(default_factory=list)
    apiDependencies: list[dict[str, Any]] = field(default_factory=list)
    moduleDependencies: list[dict[str, Any]] = field(default_factory=list)
    architectureDependencies: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RepositoryRecommendation:
    suggestedRepository: dict[str, Any] = field(default_factory=dict)
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    confidence: int = 0
    reason: str = ""
    source: str = "EngineeringIntelligence"
    signals: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImpactSummary:
    affectedFeatures: list[str] = field(default_factory=list)
    affectedStories: list[str] = field(default_factory=list)
    affectedModules: list[str] = field(default_factory=list)
    affectedApis: list[str] = field(default_factory=list)
    affectedServices: list[str] = field(default_factory=list)
    affectedTests: list[str] = field(default_factory=list)
    affectedDocumentation: list[str] = field(default_factory=list)
    engineeringComplexity: str = "Low"
    risk: str = "Low"
    estimatedEngineeringDays: str = "Estimate after Planning Recommendation"
    storyPointEstimate: str = "Estimate after Planning Recommendation"
    potentialRisks: list[str] = field(default_factory=list)
    potentialBreakingChanges: list[str] = field(default_factory=list)
    sprintImpact: str = "Review during Planning Proposal estimation."


@dataclass
class ReuseSummary:
    components: list[dict[str, Any]] = field(default_factory=list)
    apis: list[dict[str, Any]] = field(default_factory=list)
    tests: list[dict[str, Any]] = field(default_factory=list)
    pullRequests: list[dict[str, Any]] = field(default_factory=list)
    implementations: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class EngineeringSummary:
    repository: str = "Continue without Repository"
    project: str = ""
    planningMode: str = "AI_RECOMMENDED"
    repositoryConfidence: int = 0
    memoryCoverage: int = 0
    similarityMatches: int = 0
    engineeringComplexity: str = "Low"
    risk: str = "Low"
    readiness: str = "ReadyWithRecommendations"


@dataclass
class EngineeringContext:
    contextId: str
    contextVersion: str
    requirement: dict[str, Any]
    repository: RepositorySummary
    azureDevOps: AzureDevOpsSummary
    engineeringMemory: EngineeringMemorySummary
    similarWork: SimilaritySummary
    architecture: ArchitectureSummary
    dependencies: DependencySummary
    repositoryRecommendation: RepositoryRecommendation
    planningRecommendationInput: dict[str, Any]
    impact: ImpactSummary
    reuse: ReuseSummary
    readiness: dict[str, Any]
    summary: EngineeringSummary
    projectIntelligence: dict[str, Any] = field(default_factory=dict)
    relevantDocumentation: list[dict[str, Any]] = field(default_factory=list)
    correlationId: str = ""
    generatedAt: str = ""
    sourceVersions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EngineeringAnalysisResult:
    context: EngineeringContext
    rawContext: dict[str, Any] = field(default_factory=dict)
    analysis: dict[str, Any] = field(default_factory=dict)
    planningRecommendationInput: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "engineeringContext": self.context.to_dict(),
            "rawContext": self.rawContext,
            "analysis": self.analysis,
            "planningRecommendationInput": self.planningRecommendationInput,
        }
