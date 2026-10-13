# Requirement Planning Integration

## Boundary

Every new planning workflow starts in Requirement Intelligence. Planning Intelligence accepts a persisted, approved `RequirementSummary`; it does not accept free-form requirement text as a planning source.

```text
Requirement Source
  -> Requirement Ingestion
  -> Document or Transcript Parsing
  -> Engineering Discovery
  -> Requirement Analysis V2
  -> Repository Detection
  -> Engineering Memory Evidence
  -> Requirement Summary Review and Approval
  -> Planning Pack Generation
  -> Engineering Estimation
  -> Planning Preview
  -> Human Approval
  -> Approved Azure DevOps Automation
```

`RequirementAnalysisDocument` is the canonical planning input. It combines refined requirement intent with the evidence-backed Engineering Discovery report and keeps business understanding, repository impact, risks, questions, confidence, validation, and source lineage together in one versioned document.

`RequirementSummary` remains the compatibility and approval boundary shared by Requirement Intake, Context Orchestration, Planning Pack generation, and Engineering Estimation. It embeds the reviewed document as `canonicalRequirementAnalysis` and projects its approved fields for older consumers. Planning Context carries the same document as `requirement.analysisDocument`; Planning Recommendation reasoning receives that document directly through the Engineering Context prompt section.

## Requirement Analysis V2

- AI reasoning may improve business understanding and infer risks or assumptions.
- Repository, module, service, API, screen, Markdown, memory, and Azure DevOps findings come only from Engineering Discovery evidence.
- Business rules, constraints, and dependencies are retained only when source-provided or supported by discovered evidence.
- Business Goal explains why the outcome matters and is validated against Functional Requirements, which describe required behavior.
- Open Questions are retained only when selected evidence does not resolve them.
- Every section exposes its origin and evidence references. Empty sections explain why no supported value is available.
- The document validates actor identification, capability coverage, repository evidence lineage, semantic separation, and readiness explanation before approval.

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
