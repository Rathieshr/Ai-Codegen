"""Canonical Planning Proposal models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ProposalTraceability:
    requirementId: str
    businessGoals: list[str]
    functionalRequirements: list[str]
    acceptanceCriteria: list[str]
    recommendationId: str
    repositoryModules: list[str]
    memoryReferences: list[str]


@dataclass
class ProposalEstimate:
    aiEngineeringDays: float
    aiStoryPoints: int
    engineeringDays: float
    storyPoints: int
    sprintCount: float
    developersRequired: int
    complexity: str
    risk: str
    confidence: int
    overrideReason: str = ""


@dataclass
class ProposalNode:
    nodeId: str
    proposalId: str
    parentId: str
    type: str
    title: str
    description: str
    businessValue: str
    acceptanceCriteria: list[str]
    businessRules: list[str]
    dependencies: list[str]
    estimate: dict[str, Any]
    storyPoints: int
    repositoryModules: list[str]
    affectedApis: list[str]
    affectedScreens: list[str]
    technicalNotes: list[str]
    generatedTests: list[str]
    risk: str
    priority: str
    origin: str
    confidence: int
    reason: str
    repositoryMapping: dict[str, Any]
    traceability: ProposalTraceability
    planningVersion: int
    status: str = "Draft"
    taskType: str = ""
    owner: str = ""
    order: int = 0


@dataclass
class ProposalValidation:
    status: str
    mandatoryPassed: bool
    findings: list[dict[str, Any]]
    checkedAt: str


@dataclass
class ProposalHealth:
    overallHealth: int
    coverage: int
    estimateCompleteness: int
    repositoryCoverage: int
    requirementCoverage: int
    engineeringConfidence: int
    planningConfidence: int
    risk: str


@dataclass
class ProposalDiff:
    diffId: str
    recommendationId: str
    summary: dict[str, int]
    changes: list[dict[str, Any]]
    estimatedSprintImpact: str


@dataclass
class ProposalReview:
    status: str
    checklist: list[dict[str, Any]]
    reviewer: str = ""
    comments: str = ""
    reviewedAt: str = ""


@dataclass
class ProposalVersion:
    version: int
    author: str
    reason: str
    timestamp: str
    changes: list[str]
    snapshot: dict[str, Any]


@dataclass
class PlanningProposal:
    proposalId: str
    planningPackId: str
    requirementId: str
    contextId: str
    contextVersion: str
    recommendationId: str
    recommendationVersion: int
    projectId: str
    correlationId: str
    title: str
    status: str
    version: int
    nodes: list[ProposalNode]
    estimate: ProposalEstimate
    implementationOrder: list[str]
    dependencies: list[dict[str, Any]]
    validation: ProposalValidation
    health: ProposalHealth
    diff: ProposalDiff
    review: ProposalReview
    author: str
    createdAt: str
    updatedAt: str
    approvedBy: str = ""
    approvedAt: str = ""
    history: list[ProposalVersion] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
