"""Canonical Planning Context models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PlanningRepository:
    repositoryId: str = ""
    repositoryName: str = ""
    mode: str = "Unavailable"
    branch: str = ""
    snapshotId: str = ""
    snapshotVersion: str = ""
    confidence: int = 0
    affectedModules: list[str] = field(default_factory=list)
    affectedServices: list[str] = field(default_factory=list)
    affectedApis: list[str] = field(default_factory=list)
    affectedScreens: list[str] = field(default_factory=list)
    reusableComponents: list[str] = field(default_factory=list)
    reusableTests: list[str] = field(default_factory=list)
    reusePercent: int = 0
    reason: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class PlanningMemory:
    matches: list[dict[str, Any]] = field(default_factory=list)
    previousStories: list[dict[str, Any]] = field(default_factory=list)
    previousPullRequests: list[dict[str, Any]] = field(default_factory=list)
    previousBugs: list[dict[str, Any]] = field(default_factory=list)
    architectureDecisions: list[dict[str, Any]] = field(default_factory=list)
    reusableComponents: list[str] = field(default_factory=list)
    reusableTests: list[str] = field(default_factory=list)
    lessonsLearned: list[str] = field(default_factory=list)
    coverage: int = 0


@dataclass
class PlanningSimilarity:
    workItemId: str
    workItemType: str
    title: str
    similarity: int
    confidence: int
    reason: str
    suggestedAction: str
    state: str = ""


@dataclass
class PlanningClassification:
    value: str
    confidence: int
    reason: str
    source: str = "HEI"
    overriddenBy: str = ""


@dataclass
class PlanningImpact:
    affectedFeatures: list[str] = field(default_factory=list)
    affectedStories: list[str] = field(default_factory=list)
    affectedApis: list[str] = field(default_factory=list)
    affectedModules: list[str] = field(default_factory=list)
    potentialRisks: list[str] = field(default_factory=list)
    potentialBreakingChanges: list[str] = field(default_factory=list)
    sprintImpact: str = "Not assessed"
    engineeringEffort: str = "Requires estimation"
    complexity: str = "Medium"


@dataclass
class PlanningRecommendation:
    planningMode: str
    confidence: int
    strategy: str
    create: list[str] = field(default_factory=list)
    reuse: list[str] = field(default_factory=list)
    modify: list[str] = field(default_factory=list)
    doNotCreate: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


@dataclass
class PlanningSummary:
    currentProject: str
    repository: str
    planningMode: str
    recommendedStrategy: str
    affectedFeatures: int
    affectedStories: int
    engineeringRisk: str
    estimatedComplexity: str
    planningConfidence: int


@dataclass
class PlanningContext:
    contextId: str
    contextVersion: str
    requirementId: str
    requirementContextVersion: str
    analysisId: str
    projectId: str
    requirement: dict[str, Any]
    status: str
    reviewStatus: str
    azureDevOps: dict[str, Any]
    repository: PlanningRepository
    memory: PlanningMemory
    similarWork: list[PlanningSimilarity]
    classification: PlanningClassification
    impact: PlanningImpact
    recommendation: PlanningRecommendation
    readiness: dict[str, Any]
    summary: PlanningSummary
    correlationId: str
    generatedAt: str
    reviewedAt: str = ""
    reviewedBy: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
