# Engineering Review and Approval

## Purpose

Engineering Review is the mandatory human gate between a versioned Planning
Proposal and Azure DevOps synchronization.

```text
Planning Proposal
  -> Engineering Review
  -> Comments and Change Requests
  -> Configured Approval Chain
  -> Approved and Frozen Proposal
  -> Azure DevOps Synchronization Authorization
```

The workflow does not create or update Azure DevOps work items. It produces an
authorization decision that a separate approved automation flow must verify.

## Version Boundary

Every review is pinned to:

- Planning Proposal ID and version;
- Engineering Context version;
- Knowledge Registry version;
- Planning Recommendation version.

Any proposal mutation creates a new proposal version and supersedes the active
review. Earlier comments and decisions remain searchable for audit, but cannot
authorize synchronization of the new version.

## Review Model

The review dashboard projects the proposal summary, risk, readiness, validation,
estimate, affected repositories, and affected teams. It includes nine review
sections:

1. Business Review
2. Architecture Review
3. Repository Review
4. Acceptance Criteria Review
5. Dependency Review
6. Estimate Review
7. Risk Review
8. Testing Review
9. Deployment Review

Comments may target an Epic, Feature, Story, Task, Acceptance Criterion,
Engineering Note, Estimate, Dependency, or Repository Mapping. Comments and
change requests retain the proposal version on which they were created.

## Approval Chain

The default chain is Product Owner, Engineering Lead, Architect, QA Lead, and
Delivery Manager. Organizations can provide a different ordered set of stages,
roles, required flags, and assigned reviewers when creating the review.

Stage decisions are:

- Approve;
- Approve with Comments;
- Request Changes;
- Reject;
- Save Draft Review.

Only the current stage can decide. Assigned reviewers take precedence over role
matching. Required stages must complete in order.

## Readiness Gate

Approval is blocked when:

- mandatory proposal validation fails;
- a Story has no approved Acceptance Criteria;
- a Story has no implementation Task;
- dependencies reference missing artifacts;
- repository mapping is incomplete;
- a change request remains open;
- architecture approval is missing;
- risk acceptance is missing.

After the last required stage passes, the proposal becomes Approved and
read-only. Editing requires an explicit **Create New Version** action; the new
draft increments the proposal version and supersedes all prior approvals.
Synchronization authorization additionally verifies that the approved review
and proposal versions match.

## APIs

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/engineering-reviews` | Start or load a review for the current proposal version |
| `GET` | `/engineering-reviews` | Search review work |
| `GET` | `/engineering-reviews/{id}` | Load the review dashboard |
| `GET` | `/engineering-reviews/proposal/{proposalId}` | Load the current review for a proposal |
| `POST` | `/engineering-reviews/{id}/assign` | Assign a stage reviewer |
| `POST` | `/engineering-reviews/{id}/comments` | Add an inline or section comment |
| `POST` | `/engineering-reviews/{id}/change-requests` | Track a requested proposal change |
| `POST` | `/engineering-reviews/{id}/decision` | Save or apply the current stage decision |
| `GET` | `/engineering-reviews/{id}/history` | Search comments, changes, and decisions |
| `GET` | `/engineering-reviews/{id}/report` | Export Markdown or PDF review and decision reports |
| `GET` | `/engineering-reviews/proposal/{proposalId}/synchronization-authorization` | Verify the mandatory gate |

Review events, notifications, and audit entries use the shared Platform
Foundation. Engineering Reviews also appear in the existing Approval Center.
