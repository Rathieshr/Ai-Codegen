# Approved Azure DevOps Work Item Automation

## Purpose

HEI may create or update Azure DevOps work items only from an approved Work Item Recommendation or approved Planning Pack. The integration does not expose an unrestricted JSON Patch endpoint.

## Safety Boundary

Every apply request requires:

- an explicitly approved source with an approver;
- a validated Azure DevOps connection in `Connected` state;
- `WorkItems.Write` or an equivalent Azure DevOps permission;
- a live work-item revision matching the approved source revision;
- a caller-provided idempotency key and executor identity;
- a durable authorization audit event before each external write.

Preview performs the same source, connection, revision, and permission checks without obtaining a writer or modifying Azure DevOps. Conflicts and missing permissions are returned as diagnostics.

## Command Allow-list

The automation compiler emits only:

- `CreateEpicCommand`
- `CreateFeatureCommand`
- `CreateStoryCommand`
- `CreateTaskCommand`
- `UpdateWorkItemCommand`
- `LinkParentChildCommand`
- `ApplyEstimateCommand`
- `ApplyTagsCommand`
- `ApplyAreaPathCommand`
- `ApplyIterationPathCommand`
- `AddWorkItemCommentCommand`

Each command has deterministic identity and supports dry-run through the preview APIs.

## APIs

- `POST /ado-automation/planning-packs/{id}/preview`
- `POST /ado-automation/planning-packs/{id}/apply`
- `POST /ado-automation/recommendations/{id}/preview`
- `POST /ado-automation/recommendations/{id}/apply`

Apply requests require `connectionId`, `idempotencyKey`, and `executor`. `projectId` may be inherited from the connection. `reason` is written to the audit trail.

## Conflict and Retry Behavior

Existing work-item commands carry the approved revision. HEI reads the current revision before apply and returns `409 stale_revision` when it changed. Recommendation sources are marked `Stale` and require re-review.

Execution state stores completed command IDs, created Azure DevOps IDs, and current revisions. A repeated completed request returns the prior result. A retry after partial failure skips completed commands and resumes from the failed command, preventing duplicate work items and hierarchy links.

## Audit

The audit timeline records authorization, result or failure, actor, command, before and after values, resulting Azure DevOps revision, reason, correlation ID, and timestamp. Platform events report completion and failure for operational monitoring.
