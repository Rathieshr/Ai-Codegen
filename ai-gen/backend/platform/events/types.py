"""Platform event types and normalization helpers."""

from __future__ import annotations

from enum import Enum
from typing import Any

from ..shared import OperationSource, as_dict, clean, enum_value, generated_id, now_iso


class PlatformEventType(str, Enum):
    CONSUMER_MIGRATION_STARTED = "ConsumerMigrationStarted"
    CONSUMER_MIGRATION_COMPLETED = "ConsumerMigrationCompleted"
    EXECUTION_PACKAGE_CONSUMED = "ExecutionPackageConsumed"
    EXECUTION_PACKAGE_VALIDATION_FAILED = "ExecutionPackageValidationFailed"
    EXECUTION_PACKAGE_REQUESTED = "ExecutionPackageRequested"
    EXECUTION_PACKAGE_BUILT = "ExecutionPackageBuilt"
    EXECUTION_PACKAGE_READY = "ExecutionPackageReady"
    EXECUTION_PACKAGE_FAILED = "ExecutionPackageFailed"
    EXECUTION_MANIFEST_REQUESTED = "ExecutionManifestRequested"
    EXECUTION_MANIFEST_BUILT = "ExecutionManifestBuilt"
    EXECUTION_MANIFEST_REUSED = "ExecutionManifestReused"
    EXECUTION_STARTED = "ExecutionStarted"
    EXECUTION_RESPONSE_RECEIVED = "ExecutionResponseReceived"
    EXECUTION_INTERPRETED = "ExecutionInterpreted"
    EXECUTION_COMPLETED = "ExecutionCompleted"
    EXECUTION_FAILED = "ExecutionFailed"
    EXECUTION_CANCELLED = "ExecutionCancelled"
    EXECUTION_RESUMED = "ExecutionResumed"
    EXECUTION_RETRIED = "ExecutionRetried"
    EXECUTION_TIMED_OUT = "ExecutionTimedOut"
    EXECUTION_RECOVERED = "ExecutionRecovered"
    EXECUTION_PARTIAL_RESPONSE_RECEIVED = "ExecutionPartialResponseReceived"
    EXECUTION_DUPLICATE_RESPONSE_IGNORED = "ExecutionDuplicateResponseIgnored"
    PROMPT_GENERATED = "PromptGenerated"
    PROVIDER_CALLED = "ProviderCalled"
    RESPONSE_INTERPRETED = "ResponseInterpreted"
    ARTIFACTS_EXTRACTED = "ArtifactsExtracted"
    RESPONSE_INTERPRETATION_FAILED = "ResponseInterpretationFailed"
    ENGINEERING_DIFF_COMPLETED = "EngineeringDiffCompleted"
    ENGINEERING_DIFF_FAILED = "EngineeringDiffFailed"
    PROMPT_COMPILATION_REQUESTED = "PromptCompilationRequested"
    PROMPT_COMPILATION_COMPLETED = "PromptCompilationCompleted"
    COMPILED_PROMPT_REUSED = "CompiledPromptReused"
    TOKEN_OPTIMIZATION_REQUESTED = "TokenOptimizationRequested"
    TOKEN_OPTIMIZATION_COMPLETED = "TokenOptimizationCompleted"
    TOKEN_OPTIMIZATION_BLOCKED = "TokenOptimizationBlocked"
    BUDGETED_PROMPT_REUSED = "BudgetedPromptReused"
    CONTEXT_ORCHESTRATION_REQUESTED = "ContextOrchestrationRequested"
    CONTEXT_ORCHESTRATION_COMPLETED = "ContextOrchestrationCompleted"
    CONTEXT_ORCHESTRATION_NEEDS_REVIEW = "ContextOrchestrationNeedsReview"
    CONTEXT_ORCHESTRATION_FAILED = "ContextOrchestrationFailed"
    REPOSITORY_REGISTERED = "RepositoryRegistered"
    REPOSITORY_SCAN_REQUESTED = "RepositoryScanRequested"
    REPOSITORY_SCAN_COMPLETED = "RepositoryScanCompleted"
    REPOSITORY_SCAN_FAILED = "RepositoryScanFailed"
    WORK_ITEM_CREATED = "WorkItemCreated"
    WORK_ITEM_UPDATED = "WorkItemUpdated"
    PLANNING_PACK_CREATED = "PlanningPackCreated"
    PLANNING_PACK_APPROVED = "PlanningPackApproved"
    EXECUTION_PACK_CREATED = "ExecutionPackCreated"
    EXECUTION_PACK_APPROVED = "ExecutionPackApproved"
    PULL_REQUEST_CREATED = "PullRequestCreated"
    PULL_REQUEST_UPDATED = "PullRequestUpdated"
    PULL_REQUEST_MERGED = "PullRequestMerged"
    VALIDATION_REQUESTED = "ValidationRequested"
    VALIDATION_SKIPPED = "ValidationSkipped"
    VALIDATION_BLOCKED = "ValidationBlocked"
    VALIDATION_COMPLETED = "ValidationCompleted"
    QA_PACK_CREATED = "QAPackCreated"
    QA_REQUESTED = "QARequested"
    QA_SKIPPED = "QASkipped"
    MEMORY_CANDIDATE_CREATED = "MemoryCandidateCreated"
    MEMORY_CANDIDATE_REJECTED = "MemoryCandidateRejected"
    PR_CANDIDATE_CREATED = "PRCandidateCreated"
    MEMORY_CAPTURE_REQUESTED = "MemoryCaptureRequested"
    MEMORY_CAPTURE_APPROVED = "MemoryCaptureApproved"
    AGENT_RUN_REQUESTED = "AgentRunRequested"
    AGENT_RUN_COMPLETED = "AgentRunCompleted"
    AGENT_RUN_FAILED = "AgentRunFailed"
    AZURE_DEVOPS_CONNECTION_REGISTERED = "AzureDevOpsConnectionRegistered"
    AZURE_DEVOPS_CONNECTION_VALIDATED = "AzureDevOpsConnectionValidated"
    AZURE_DEVOPS_CONNECTION_FAILED = "AzureDevOpsConnectionFailed"
    AZURE_DEVOPS_PROJECT_DISCOVERED = "AzureDevOpsProjectDiscovered"
    AZURE_DEVOPS_READ_FAILED = "AzureDevOpsReadFailed"
    AZURE_DEVOPS_WEBHOOK_RECEIVED = "AzureDevOpsWebhookReceived"
    AZURE_DEVOPS_SYNC_REQUESTED = "AzureDevOpsSyncRequested"
    AZURE_DEVOPS_SYNC_STARTED = "AzureDevOpsSyncStarted"
    AZURE_DEVOPS_SYNC_COMPLETED = "AzureDevOpsSyncCompleted"
    AZURE_DEVOPS_SYNC_FAILED = "AzureDevOpsSyncFailed"
    AZURE_DEVOPS_WORK_ITEM_SYNCHRONIZED = "AzureDevOpsWorkItemSynchronized"
    AZURE_DEVOPS_PULL_REQUEST_SYNCHRONIZED = "AzureDevOpsPullRequestSynchronized"
    AZURE_DEVOPS_BUILD_SYNCHRONIZED = "AzureDevOpsBuildSynchronized"
    AZURE_DEVOPS_RECONCILIATION_REQUIRED = "AzureDevOpsReconciliationRequired"
    PULL_REQUEST_ANALYSIS_REQUESTED = "PullRequestAnalysisRequested"
    PULL_REQUEST_ANALYSIS_COMPLETED = "PullRequestAnalysisCompleted"
    PULL_REQUEST_COMMENT_APPROVAL_REQUIRED = "PullRequestCommentApprovalRequired"
    PULL_REQUEST_COMMENT_POSTED = "PullRequestCommentPosted"
    SPRINT_INTELLIGENCE_GENERATED = "SprintIntelligenceGenerated"
    AZURE_DEVOPS_ACTION_PACK_PREPARED = "AzureDevOpsActionPackPrepared"
    AZURE_DEVOPS_ACTION_PACK_APPLIED = "AzureDevOpsActionPackApplied"


def normalize_platform_event(event: dict[str, Any]) -> dict[str, Any]:
    event_type = clean(event.get("eventType") or event.get("type")) or PlatformEventType.WORK_ITEM_UPDATED.value
    return {
        "eventId": clean(event.get("eventId") or event.get("id")) or generated_id("platform_event"),
        "eventType": event_type,
        "source": enum_value(event.get("source"), OperationSource, OperationSource.MANUAL),
        "projectId": clean(event.get("projectId") or event.get("project_id")),
        "repositoryId": clean(event.get("repositoryId") or event.get("repository_id")),
        "workItemId": clean(event.get("workItemId") or event.get("work_item_id")),
        "correlationId": clean(event.get("correlationId") or event.get("correlation_id")) or generated_id("corr"),
        "payload": as_dict(event.get("payload")),
        "createdAt": clean(event.get("createdAt")) or now_iso(),
    }
