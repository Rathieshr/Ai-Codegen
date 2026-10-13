# Azure DevOps Agent

> Phase 6.9 validation and operating guidance are also documented in [Azure DevOps Integration](azure-devops-integration.md), [Automation Policy](azure-devops-automation-policy.md), [Permissions](azure-devops-permissions.md), and [Troubleshooting](azure-devops-troubleshooting.md).

## Purpose

The Azure DevOps Agent prepares engineering intelligence and bounded Azure DevOps actions. It never approves its own work. Consequential writes remain behind a human-approved action pack.

## Runtime Flow

1. A supported platform event is received.
2. Event delivery is deduplicated and an `AzureDevOpsAgent` job is queued.
3. The Platform Agent Runtime records the run and correlation ID.
4. The agent uses HEI Platform SDK service contracts to prepare analysis, estimates, reports, and dry-run write previews.
5. The result is persisted as an `AzureDevOpsActionPack`.
6. A human approves or rejects the pack.
7. Apply rechecks expiry, source revisions, policy, permissions, and approval.
8. Approved operations are delegated to the existing Azure DevOps automation or approved PR-comment service.

The Job Framework provides retry handling. Activity and audit records preserve the same correlation ID across preparation, approval, and application.

## Supported Triggers

- Requirement received
- Planning Pack approved
- Work item changed
- Sprint started or nearing end
- Pull request created, updated, or merged
- Build failed
- Scheduled reconciliation
- Manual request

## Approval Boundary

Approval is required for work-item creation or updates, state and iteration changes, estimates, assignments, and PR comments unless an explicit informational-comment policy permits them. Approval packs expire and become stale when a tracked source revision changes.

The agent cannot approve or merge pull requests, delete work items, deploy software, or bypass repository policies. These operations are rejected by policy and have no apply handler.

## APIs

- `GET /ado-agent/runs`
- `GET /ado-agent/runs/{id}`
- `GET /ado-agent/action-packs`
- `GET /ado-agent/action-packs/{id}`
- `POST /ado-agent/action-packs/{id}/approve`
- `POST /ado-agent/action-packs/{id}/reject`
- `POST /ado-agent/action-packs/{id}/apply`

The same operations are available through `sdk.azureDevOps` so clients do not depend directly on REST routes.

## Persistence and Recovery

Runs, event receipts, and action packs use the Platform Foundation JSON stores. Duplicate events do not enqueue duplicate work. Partial application records every completed action and can resume with the same pack without repeating completed operations.

## Current Limitation

The milestone prepares and applies existing approved automation commands. It does not introduce arbitrary Azure DevOps patching, PR approval, merge, deletion, or deployment capabilities.
