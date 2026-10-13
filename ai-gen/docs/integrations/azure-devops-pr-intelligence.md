# Azure DevOps PR Intelligence

## Purpose

HEI PR Intelligence compares a real Azure DevOps pull request with the approved engineering intent that produced it. Azure DevOps remains the source of truth for the pull request, commits, linked work items, branches, and changed files. HEI stores the resulting intelligence report and an optional draft comment.

The service does not approve, complete, merge, or otherwise mutate a pull request.

## Context Resolution

Analysis resolves the following context in order:

1. Synchronized Azure DevOps pull request and linked work items.
2. Branches, commits, changed files, and before/after repository snapshots.
3. Execution Package and Execution Plan lineage.
4. Runtime Session and Engineering Diff.
5. Implementation Validation and QA result.
6. Engineering Memory candidates and PR Candidate.

Callers may provide context explicitly for controlled integrations and tests. Otherwise, the service resolves persisted artifacts by shared lineage identifiers such as work-item, story, task, package, session, diff, and pull-request IDs. Missing context is reported as a warning and lowers readiness; it is never fabricated.

## Readiness Status

Reports use only these statuses:

- `NotAnalyzed`
- `Analyzing`
- `NeedsReview`
- `ChangesRequired`
- `ReadyForReview`
- `ValidationFailed`
- `QAIncomplete`

`ReadyForReview` means the HEI evidence is sufficiently aligned for human review. It does not mean merge-ready. External builds, branch policies, required reviewers, and Azure DevOps checks remain authoritative.

## Analysis Output

The persisted report includes change intent, acceptance coverage, missing criteria, planned-versus-actual drift, unrelated or blocked-scope changes, architecture and security findings, missing tests, regression scope, risk, breaking changes, reviewer recommendations, resolved context identities, warnings, and correlation diagnostics.

Documentation-only changes are recognized without inventing code or test evidence. Stale repository snapshots are explicitly marked for review.

## Comment Approval Policy

Analysis always stores the report in HEI first. Comment flow is separate:

1. Generate a comment preview.
2. Review the exact Markdown content.
3. Submit explicit approval with approver identity and idempotency key.
4. Verify the registered connection has pull-request contribution permission.
5. Record authorization in the audit trail.
6. Post through the restricted PR-comment transport.

The transport exposes only comment-thread creation. It has no approve, complete, or merge operation. Replaying an approved request with the same idempotency key returns the prior receipt without posting a duplicate comment.

## Events

PR Intelligence subscribes to:

- `PullRequestCreated`
- `PullRequestUpdated`
- `PullRequestMerged`
- `AzureDevOpsPullRequestSynchronized`

It publishes:

- `PullRequestAnalysisRequested`
- `PullRequestAnalysisCompleted`
- `PullRequestCommentApprovalRequired`
- `PullRequestCommentPosted`

Webhook receipts make repeated event delivery idempotent. Analysis never posts a comment as a side effect of an event.

## APIs

- `POST /ado-intelligence/pull-requests/{id}/analyze`
- `GET /ado-intelligence/pull-requests/{id}/report`
- `POST /ado-intelligence/pull-requests/{id}/comment-preview`
- `POST /ado-intelligence/pull-requests/{id}/post-approved-comment`
- `POST /ado-intelligence/pull-requests/{id}/reanalyze`

Live context enrichment requires a connection ID, project ID, and repository ID when the synchronized cache does not already contain the PR. Comment posting additionally requires an approved preview, approver identity, permission, audit service, and idempotency key.

## Security Boundary

- No automatic PR approval or merge.
- No automatic blocking comment.
- No arbitrary PR patch endpoint.
- No plaintext credentials in HEI storage or API responses.
- Read operations use the centralized ADO integration service.
- Comment posting uses a distinct least-privilege client.
- Every approved post is correlated and audited.
