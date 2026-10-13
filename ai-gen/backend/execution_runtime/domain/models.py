"""Canonical AI Execution Runtime contracts."""

from __future__ import annotations

from typing import Any, TypedDict


EXECUTION_RUNTIME_VERSION = "5.10"


class ExecutionSession(TypedDict):
    sessionId: str
    idempotencyKey: str
    executionPlanVersion: str
    executionPackageVersion: str
    repositorySnapshotVersion: str
    provider: str
    model: str
    startedAt: str
    completedAt: str
    status: str
    duration: float
    correlationId: str
    developerId: str
    workspaceId: str
    branch: str
    commitBefore: str
    commitAfter: str
    warnings: list[str]
    confidence: float
    attempt: int
    maxRetries: int
    attemptStartedAt: str
    lastCheckpoint: str
    lastFailure: dict[str, Any] | None
    responseHistory: list[dict[str, Any]]
    partialResponses: list[dict[str, Any]]
    duplicateResponseCount: int
    lastResponseDisposition: str
    lastOperationDisposition: str
    recovery: dict[str, Any]


class ExecutionResult(TypedDict):
    resultId: str
    sessionId: str
    provider: str
    model: str
    responseType: str
    status: str
    rawResponse: Any
    structuredResponse: dict[str, Any]
    warnings: list[str]
    errors: list[str]
    confidence: float
    tokenUsage: dict[str, Any]
    duration: float


class ExecutionArtifact(TypedDict):
    artifactId: str
    sessionId: str
    type: str
    path: str
    title: str
    changeType: str
    language: str
    content: str
    confidence: float
    evidence: list[str]


class EngineeringDiff(TypedDict):
    diffId: str
    sessionId: str
    repositorySnapshotVersion: str
    commitBefore: str
    commitAfter: str
    added: list[str]
    modified: list[str]
    deleted: list[str]
    unchanged: list[str]
    artifactIds: list[str]
    summary: dict[str, int]
    confidence: float
    generatedAt: str
