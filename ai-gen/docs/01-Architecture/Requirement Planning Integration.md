# Requirement Planning Integration

## Boundary

Every new planning workflow starts in Requirement Intelligence. Planning Intelligence accepts a persisted, approved `RequirementSummary`; it does not accept free-form requirement text as a planning source.

```text
Requirement Source
  -> Requirement Ingestion
  -> Document or Transcript Parsing
  -> Requirement Analysis
  -> Repository Detection
  -> Engineering Memory Evidence
  -> Requirement Summary Review and Approval
  -> Planning Pack Generation
  -> Engineering Estimation
  -> Planning Preview
  -> Human Approval
  -> Approved Azure DevOps Automation
```

`RequirementSummary` is the canonical boundary shared by Requirement Intake, Context Orchestration, Planning Pack generation, and Engineering Estimation. It contains the approved requirement categories, planning readiness, repository mapping, memory evidence summary, source lineage, context version, and correlation ID.

## Safety Rules

- Raw `title` or `content` fields cannot start planning through the Planning Integration APIs.
- Requirement Analysis must be approved for the current content hash and context version.
- Repository Detection is committed during Requirement Summary approval; Planning does not silently select another repository.
- Planning Pack generation is idempotent for the same approved analysis and Requirement Context version.
- Editing or re-analyzing a requirement invalidates the existing preview until the new summary is approved and regenerated.
- Planning Packs remain draft artifacts. Azure DevOps writes continue through the separate preview, approval, idempotency, and revision-protected automation layer.

## APIs

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/planning/from-requirement` | Enter Planning from an approved Requirement Summary. |
| `POST` | `/planning/generate` | Generate or reuse the Planning Pack and Engineering Estimation. |
| `POST` | `/planning/preview` | Load the current reviewable Planning Preview. |

All three routes require `requirementId` or a previously generated `planningPackId` where applicable. The legacy `/requirements/intake` route remains available for older clients, but new experiences must use `/planning/from-requirement`.

## Source Coverage

The integration is source-neutral after ingestion and supports pasted requirements, uploaded PRD/BRD documents, meeting transcripts, and synchronized Azure DevOps work items through the same approved summary contract.
