"""Canonical Planning Recommendation models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class RecommendationStrategy(str, Enum):
    NEW_EPIC = "NEW_EPIC"
    NEW_INITIATIVE = "NEW_INITIATIVE"
    NEW_FEATURE = "NEW_FEATURE"
    NEW_STORY = "NEW_STORY"
    EXTEND_EXISTING_FEATURE = "EXTEND_EXISTING_FEATURE"
    EXTEND_EXISTING_EPIC = "EXTEND_EXISTING_EPIC"
    EXTEND_EXISTING_STORY = "EXTEND_EXISTING_STORY"
    MODIFY_EXISTING_STORY = "MODIFY_EXISTING_STORY"
    BUG_FIX = "BUG_FIX"
    ENHANCEMENT = "ENHANCEMENT"
    TECHNICAL_DEBT = "TECHNICAL_DEBT"
    REFACTOR = "REFACTOR"
    REFACTOR_EXISTING_FEATURE = "REFACTOR_EXISTING_FEATURE"
    SPIKE = "SPIKE"
    CONFIGURATION_CHANGE = "CONFIGURATION_CHANGE"
    DOCUMENTATION_UPDATE = "DOCUMENTATION_UPDATE"
    MIXED_RECOMMENDATION = "MIXED_RECOMMENDATION"
    AI_RECOMMENDED = "AI_RECOMMENDED"


@dataclass
class RecommendationReason:
    title: str
    explanation: str
    evidence: list[str] = field(default_factory=list)
    confidence: int = 0


@dataclass
class RecommendationImpact:
    repositoryId: str
    repositoryName: str
    businessImpact: str
    engineeringImpact: str
    repositoryImpact: str
    sprintImpact: str
    estimatedComplexity: str
    affectedModules: list[str] = field(default_factory=list)
    affectedStories: list[str] = field(default_factory=list)
    affectedFeatures: list[str] = field(default_factory=list)
    affectedApis: list[str] = field(default_factory=list)
    affectedServices: list[str] = field(default_factory=list)
    affectedScreens: list[str] = field(default_factory=list)
    affectedDatabaseObjects: list[str] = field(default_factory=list)
    affectedTests: list[str] = field(default_factory=list)
    affectedDocumentation: list[str] = field(default_factory=list)
    affectedPipelines: list[str] = field(default_factory=list)
    riskLevel: str = "Medium"
    storyPointEstimate: str = "Requires Planning Proposal"
    engineeringDays: str = "Requires Planning Proposal"


@dataclass
class RecommendationAlternative:
    strategy: str
    confidence: int
    title: str
    pros: list[str]
    cons: list[str]
    rejectedReason: str
    description: str = ""
    estimatedEffort: str = ""
    risks: list[str] = field(default_factory=list)
    reuseScore: int = 0


@dataclass
class RecommendationConfidence:
    engineering: int
    repository: int
    memory: int
    planning: int
    overall: int


@dataclass
class RecommendationDiff:
    diffId: str
    summary: dict[str, int]
    operations: list[dict[str, Any]]


@dataclass
class RecommendationSummary:
    recommendedStrategy: str
    engineeringConfidence: int
    repositoryConfidence: int
    memoryConfidence: int
    planningConfidence: int
    expectedSprint: str
    expectedStoryCount: int
    expectedTaskCount: int
    expectedModificationCount: int


@dataclass
class PlanningRecommendation:
    recommendationId: str
    contextId: str
    contextVersion: str
    requirementId: str
    projectId: str
    correlationId: str
    strategy: str
    title: str
    status: str
    version: int
    confidence: RecommendationConfidence
    reasons: list[RecommendationReason]
    rejectedAlternatives: list[RecommendationReason]
    alternatives: list[RecommendationAlternative]
    actions: list[dict[str, Any]]
    similarWork: list[dict[str, Any]]
    relatedPullRequests: list[dict[str, Any]]
    currentDevelopment: list[dict[str, Any]]
    repositoryComponents: list[str]
    dependencies: list[str]
    architectureDecisions: list[dict[str, Any]]
    impact: RecommendationImpact
    diff: RecommendationDiff
    summary: RecommendationSummary
    risks: list[str]
    engineeringReasoning: list[str]
    expectedRepositoryImpact: str
    expectedAzureDevOpsImpact: str
    generatedAt: str
    approvedAt: str = ""
    approvedBy: str = ""
    overrideReason: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)
    reasoningVersion: str = ""
    promptVersion: str = ""
    reasoningMode: str = "Deterministic"
    reasoningResult: dict[str, Any] = field(default_factory=dict)
    primaryRecommendation: dict[str, Any] = field(default_factory=dict)
    strategyOptions: list[dict[str, Any]] = field(default_factory=list)
    repositoryAnalysis: dict[str, Any] = field(default_factory=dict)
    existingWorkDetection: dict[str, Any] = field(default_factory=dict)
    reuseSuggestions: list[dict[str, Any]] = field(default_factory=list)
    dependencyAnalysis: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    engineeringImpact: dict[str, Any] = field(default_factory=dict)
    readiness: dict[str, Any] = field(default_factory=dict)
    missingInformation: dict[str, list[str]] = field(default_factory=dict)
    explanation: dict[str, Any] = field(default_factory=dict)
    userChanges: list[dict[str, Any]] = field(default_factory=list)
    approvalHistory: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
