# Memory Candidate Generator

## Purpose

The Memory Candidate Generator proposes reusable Engineering Memory from completed engineering outcomes. It consumes structured runtime evidence and creates a review queue; it never writes to or indexes Engineering Memory.

## Inputs

- Execution Result
- Validation Result
- QA Result
- Engineering Diff
- Existing Engineering Memory for duplicate detection
- Organization memory policy
- Project and organization identity

## Candidate types

- Reusable Pattern
- Architecture Decision
- Bug Fix
- Implementation Pattern
- Reusable Test
- Lesson Learned

Candidate types are emitted only when their supporting evidence exists. For example, Architecture Decision requires architecture changes, Bug Fix requires an explicit bug-fix artifact or response type, and Reusable Test requires QA test evidence or semantic test changes.

## Candidate contract

Every candidate contains:

- confidence and reuse score
- suggested Engineering Memory category
- project scope
- policy-controlled organization scope eligibility
- approval-required status
- duplicate-detection result
- source lineage across Execution Result, Validation Result, QA Result, and Engineering Diff
- evidence and rejection reasons
- `stored: false` and `indexed: false`

Generated candidates start as `PendingApproval`. Duplicate, low-confidence, low-reuse, incomplete-source, failed-source, or policy-disallowed candidates start as `Rejected`. Execution must be completed, and Validation and QA outcomes must be explicitly passed, approved, completed, or ready.

## Approval boundary

```text
Execution Result + Validation Result + QA Result + Engineering Diff
                              |
                    Candidate Generation
                              |
              Pending Approval or Rejected
                              |
                       Human Approval
                              |
                 Approved Candidate Record
                              |
        Separate Engineering Memory Capture (future step)
```

Approval does not store or index memory. The candidate remains a review artifact until a separate Engineering Memory capture workflow consumes it.

## Duplicate detection

Duplicate checks use:

1. deterministic candidate fingerprint;
2. normalized title plus suggested category;
3. existing candidates and caller-supplied Engineering Memory.

A duplicate attempt is retained as a rejected review record and publishes `MemoryCandidateRejected`. It does not overwrite the original candidate or memory.

## Organization policy

Policy controls:

- whether generation is enabled;
- minimum confidence;
- minimum reuse score;
- blocked candidate types;
- whether organization scope is allowed;
- organization-scope confidence and reuse thresholds.

Project scope is always explicit. Organization scope is never inferred without policy permission and an organization identity.

## Events

- `MemoryCandidateCreated`
- `MemoryCandidateRejected`

Event payloads include candidate type, approval state, lineage, and explicit `stored: false` and `indexed: false` fields.

## APIs

| Method | Route | Contract |
| --- | --- | --- |
| `POST` | `/memory-candidates/generate` | Generate, gate, persist, and publish review candidates. |
| `GET` | `/memory-candidates` | List candidate review records, optionally by project. |
| `GET` | `/memory-candidates/{id}` | Retrieve one candidate. |
| `POST` | `/memory-candidates/{id}/approve` | Approve a candidate without storing memory. |
| `POST` | `/memory-candidates/{id}/reject` | Reject a pending candidate and publish rejection. |
