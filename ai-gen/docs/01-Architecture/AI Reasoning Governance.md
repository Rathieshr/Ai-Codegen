# AI Reasoning Governance and Requirement Intelligence Reliability

## Purpose

AI Reasoning Governance is the mandatory trust boundary between provider
reasoning and the canonical Requirement Analysis document. It prevents model
output from silently becoming approved engineering scope.

The governance layer separates:

- user-provided facts;
- verified engineering evidence;
- bounded AI interpretations;
- optional AI suggestions; and
- information that remains unknown.

Engineering Intelligence continues to own facts. The Reasoning AI Layer
continues to produce engineering judgment. Requirement Governance decides how
each statement may be used downstream.

## Architecture

```text
Requirement Context
        |
        v
Requirement Extraction / Refinement
        |
        v
Engineering Intelligence
  - Repository Intelligence
  - Repository Markdown
  - Azure DevOps
  - Knowledge Registry
  - Engineering Memory
        |
        v
Engineering Discovery Report
        |
        +---------------------------+
        |                           |
        v                           v
Reasoning AI Layer          Verified evidence catalog
  - provider-neutral                 |
  - budget managed                   |
  - deterministic fallback           |
        |                           |
        +-------------+-------------+
                      |
                      v
          Requirement Governance Engine
          - classify each statement
          - validate evidence references
          - reject unsupported scope
          - preserve suggestions
          - record provenance
                      |
                      v
          Governed Requirement Analysis
                      |
                      v
       Acceptance Criteria Intelligence
                      |
                      v
       Canonical Requirement Analysis V2
                      |
                      v
            Review and Planning Context
```

The ordering is intentional. Acceptance Criteria generation runs only after
governance has removed unsupported Functional Requirements.

## Module Ownership

| Module | Responsibility |
| --- | --- |
| Requirement Intake | Stores and normalizes the original requirement source. |
| Requirement Refinement | Improves wording while preserving source intent. |
| Engineering Intelligence | Retrieves bounded repository, Markdown, ADO, knowledge, and memory facts. |
| Reasoning AI Layer | Produces provider-neutral interpretations and recommendations. |
| Requirement Governance | Classifies statements and enforces evidence and scope rules. |
| Acceptance Criteria Intelligence | Generates criteria from governed inputs only. |
| Requirement Analysis Document Builder | Produces the immutable planning input and validates it. |
| Planning Intelligence | Consumes the reviewed canonical document; it does not reinterpret raw provider output. |

## Statement Classification

Every governed statement has exactly one classification.

| Classification | Meaning | Downstream use |
| --- | --- | --- |
| `SOURCE` | Directly stated or faithfully paraphrased from the requirement. | May enter the canonical requirement and Acceptance Criteria generation. |
| `EVIDENCE` | Verified by selected repository, Markdown, ADO, knowledge, or memory evidence. | May enter the canonical requirement and Acceptance Criteria generation. |
| `AI_INFERRED` | Scope-preserving interpretation that does not add functionality. | May explain intent and may be used where the consumer explicitly permits inference. |
| `AI_SUGGESTION` | Optional enhancement, quality recommendation, or unsupported provider addition. | Visible for review but excluded from canonical functional scope until explicitly approved. |
| `UNKNOWN` | Cannot be determined from the source or selected evidence. | Presented as missing information or a clarification question. |

### Functional Requirement Gate

Functional Requirements are accepted only when they are supported by the
source or selected engineering evidence. Common patterns are not requirements.

The gate explicitly protects against unsupported additions such as:

- rollback;
- retry behavior;
- authentication or authorization;
- permissions and role management;
- audit behavior;
- notifications;
- CRUD expansion; and
- other implementation or architecture choices.

If one of these behaviors is explicitly present in the source or verified
evidence, it can be classified as `SOURCE` or `EVIDENCE`. Otherwise it is moved
to `AI_SUGGESTION` with `requiresConfirmation: true`.

## Provenance Contract

Every governed statement uses the following transport shape:

```json
{
  "id": "statement_<uuid>",
  "category": "Functional Requirement",
  "text": "Install firmware on an offline device.",
  "classification": "SOURCE",
  "source": "User Requirement",
  "provider": "",
  "model": "",
  "promptVersion": "",
  "confidence": 1.0,
  "evidenceReferences": ["source:requirement"],
  "generatedAt": "2026-08-04T00:00:00+00:00",
  "approvedStatus": "NotRequired",
  "why": "Directly stated or faithfully paraphrased by the requirement source."
}
```

AI-generated statements additionally record provider, model, and prompt
version. Suggestions use `PendingReview` and remain outside accepted scope.

## Business Understanding Rules

### Business Goal

The Business Goal explains why the requested outcome matters. It must not
repeat a Functional Requirement. When the source does not provide an explicit
goal, HEI may infer a likely operational outcome and classify it as
`AI_INFERRED`.

### Problem Statement

The Problem Statement describes the current limitation or operational pain. It
must not restate the requested solution.

### Business Value

Business Value states the expected improvement, such as reduced downtime,
reduced manual investigation, or faster operational decisions. A reasonable
bounded inference is preferred over an empty "requires clarification" value.

### Candidate Actors

Explicit actors remain source facts. When an actor is not supplied, governance
may infer a likely candidate such as Maintenance Engineer or Operations User.
The inferred actor is visible in the canonical document with provenance but
does not overwrite the source-extracted actor collection.

## Non-Functional Requirements

Source-provided Non-Functional Requirements remain governed source statements.
Evidence-backed quality statements retain their evidence references.
Provider-generated performance, security, availability, scalability, or
responsiveness ideas are `AI_SUGGESTION` values until reviewed.

They are displayed as candidates and are not silently promoted into accepted
requirements.

## Runtime Sequence

`RequirementAnalysisService.analyze()` executes the following sequence:

1. Load the persisted Requirement Context.
2. Resolve accepted Requirement Refinement when available.
3. Run deterministic requirement extraction.
4. Build Requirement Intent.
5. Detect the relevant repository.
6. Build canonical Engineering Context.
7. Run provider-neutral requirement reasoning or deterministic fallback.
8. Merge the reasoned response into a temporary analysis draft.
9. Build Engineering Discovery from selected facts.
10. Run `RequirementGovernanceEngine.govern()`.
11. Replace temporary Functional Requirements with governed accepted values.
12. Preserve unsupported content in `suggestedEnhancements`.
13. Run Acceptance Criteria understanding against governed values.
14. Build and validate `RequirementAnalysisDocument`.
15. Persist analysis, lineage, diagnostics, and governance data.

The canonical document builder never re-merges the raw provider Functional
Requirement list. This prevents a rejected suggestion from leaking back after
governance.

## Acceptance Criteria Boundary

Acceptance Criteria Intelligence receives the analysis only after statement
governance. Its Functional Requirement input therefore contains accepted
source- or evidence-backed behavior.

The document validation rule
`suggestionsExcludedFromFunctionalRequirements` verifies that a statement
classified as `AI_SUGGESTION` is absent from the canonical Functional
Requirements list.

Existing Acceptance Criteria records continue to carry their own origin,
confidence, evidence, mapping, and review status. Suggested criteria remain
subject to the existing approval workflow.

## Engineering Discovery

Engineering Discovery returns actual findings for each source, not only
aggregate counts. Each source group contains:

- title;
- evidence type;
- source reference;
- selection reason; and
- confidence.

For example:

```json
{
  "source": "Repository Intelligence",
  "count": 1,
  "findings": [
    {
      "title": "FirmwareUpdateService",
      "type": "Service",
      "sourceReference": "repository:repo-1:v4:firmware-update-service",
      "reason": "Matched the offline firmware requirement.",
      "confidence": 91
    }
  ]
}
```

`DiscoveryPending` means a source has not completed synchronization.
`NoRelevantEvidence` means discovery completed without a relevant match. HEI
does not invent evidence to fill either state.

## Planning Readiness

Planning Readiness leads with an explanation rather than a percentage.

The document exposes:

- `status`;
- `strengths`;
- `needsAttention`;
- `blockers`;
- `warnings`;
- `explanation`; and
- a secondary supporting score and dimensions.

Suggestions waiting for approval appear under `needsAttention` and do not
silently block or expand the accepted scope.

## UI Implementation

The Requirement Analysis V2 view displays governed statements individually.
Each item shows:

- classification badge;
- statement confidence;
- evidence count;
- review-required state; and
- the generation rationale as hover text.

The view includes a separate Suggested Enhancements section. Engineering
Discovery lists actual selected findings and source names. Planning Readiness
shows strengths and attention items before its supporting score.

The UI retains compatibility fallback rendering for older cached documents.
Older analyses are regenerated because the analysis cache requires
`hei-statement-governance-v1`.

## Implementation Map

| File | Implementation |
| --- | --- |
| `backend/requirement_analysis/governance.py` | Classifier, unsupported-pattern guard, provenance generation, business interpretation, and suggestion quarantine. |
| `backend/requirement_analysis/service.py` | Mandatory governance orchestration before Acceptance Criteria and document finalization. |
| `backend/requirement_analysis/document.py` | Canonical document projection, suggestion leak prevention, readiness explanation, and validation. |
| `backend/requirement_analysis/models.py` | Governance and suggestion fields on Requirement Analysis V2. |
| `backend/engineering_intelligence/services/discovery_service.py` | Actual discovery findings grouped by engineering source. |
| `backend/reasoning/services/prompt_builder.py` | Provider-neutral `suggestedEnhancements` response contract. |
| `backend/reasoning/services/prompt_templates.py` | Explicit prompt instructions separating requirements from unsupported patterns. |
| `azure-devops-extension/src/newRequirementWorkspace.tsx` | Statement badges, confidence, evidence, suggestions, findings, and readiness explanations. |
| `azure-devops-extension/src/storyPlanner.css` | Compact governed-statement and provenance presentation. |

## Persistence and Compatibility

Governance is stored inside each Requirement Analysis result as
`statementGovernance`. The canonical document repeats the governed statement
collection needed by downstream consumers and review surfaces.

The governance schema version is `hei-statement-governance-v1`. Analyses that
do not contain this version are treated as stale and rebuilt. Existing public
Requirement Analysis APIs remain compatible; the new fields are additive.

Source-extracted fields retain their established semantics. Inferred actors,
business goals, and business value are stored in governance and the canonical
document rather than being written back as source facts.

## Failure and Fallback Behavior

Provider failure does not bypass governance. Deterministic reasoning output is
classified by the same engine.

If evidence is unavailable:

- repository claims are not fabricated;
- unsupported Functional Requirements become suggestions;
- unresolved information is classified as `UNKNOWN`;
- readiness explains the evidence gap; and
- the user can continue only according to existing readiness and approval
  rules.

## Tests

Primary regression coverage is located in:

- `tests/test_requirement_reasoning_governance.py`;
- `tests/test_requirement_analysis_v2.py`; and
- `tests/test_requirement_analysis_engine.py`.

The tests cover:

- unsupported rollback and authorization suggestions;
- evidence-supported guarded behavior;
- distinct business goal, problem statement, and business value;
- candidate actor inference;
- complete statement provenance;
- raw provider suggestion leak prevention;
- canonical Requirement Analysis compatibility;
- Acceptance Criteria generation from governed requirements; and
- existing Requirement Intelligence behavior.

Recommended verification commands:

```bash
python3 -m compileall backend tests
python3 -m unittest discover -s tests -p 'test_requirement*.py' -v
cd azure-devops-extension
npm run build
```

## Extension Rules

New reasoning workflows that contribute to Requirement Analysis must:

1. return provider-neutral structured output;
2. include unsupported enhancements under `suggestedEnhancements`;
3. pass every generated statement through Requirement Governance;
4. preserve evidence references from Engineering Context;
5. avoid direct repository, ADO, knowledge, or memory lookups;
6. keep suggestions outside canonical scope until approval; and
7. add regression coverage for source, evidence, inference, suggestion, and
   unknown classifications.

No future provider or model adapter may bypass this boundary.
