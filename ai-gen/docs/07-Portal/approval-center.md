# Approval Center

## Purpose

The Approval Center is the single human-review experience for HEI. It projects approval requests from their owning services and does not replace their lifecycle, policy, freshness, or write-safety rules.

## Sources

- Planning Packs from Planning Center artifacts
- Execution Plans from immutable Execution Manifests and Governance approval records
- Memory Candidates from the Runtime Memory Candidate service
- Azure DevOps Action Packs from the Azure DevOps Agent
- PR Comments from Azure DevOps PR Intelligence comment previews
- Validation Exceptions from Engineering Governance
- Work Item Recommendations from Azure DevOps Work Item Intelligence

## Decision Flow

```text
Source artifact
  -> Approval Center projection
  -> Human preview / compare / audit
  -> Approve or Reject
  -> Source-owned decision operation
  -> Approval Center audit event
```

The center does not apply an Azure DevOps Action Pack or post a PR comment. Those remain separate, explicit operations after approval. Source services continue to enforce expiration, stale revisions, policy, permissions, idempotency, and valid state transitions.

## Canonical Contract

Each projected record has a namespaced approval ID, source ID, category, title, summary, normalized status, requester, timestamps, expiration state, confidence, risk, and source data. The source ID is retained so audit records and downstream operations remain traceable.

Normalized actionable states are `Pending`, `NeedsReview`, `Draft`, and `Prepared`. Terminal states are `Approved`, `Rejected`, and `Expired`.

## API

- `GET /approvals`
- `GET /approvals/{id}`
- `POST /approvals/{id}/approve`
- `POST /approvals/{id}/reject`

List queries support category, status, search, offset, and limit filters. Decision requests require an authenticated actor and current HEI role.

## Permissions

Administrators and contributors may make decisions when the source service permits them. Viewers and Azure DevOps Readers receive a read-only experience. Backend enforcement remains authoritative even when UI controls are disabled.

## Audit

Source services retain their native audit events. Every successful decision through the center also records an `ApprovalCenterDecision` governance event containing the actor, reason, source artifact, previous source status, and canonical approval ID.
