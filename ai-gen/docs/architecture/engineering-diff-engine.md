# Engineering Diff Engine

## Purpose

The Engineering Diff Engine compares engineering meaning across two Repository Snapshots and a structured Execution Result. It is not a Git diff and does not inspect working-tree content.

## Inputs

- `repositorySnapshotBefore`
- `repositorySnapshotAfter`
- `executionResult`

Repository snapshots may supply semantic facts directly or through snapshot metadata, parsed symbols, and Engineering Graph nodes and relationships. The Execution Result contributes only explicit interpreted artifact claims.

## Semantic projection

Each input is projected into stable semantic identities for:

- APIs
- modules
- services
- dependencies
- architecture
- tests
- security
- configuration
- database
- documentation

Identity, path, signature, source, evidence, and confidence are retained. A common identity with a changed signature is `Modified`; a common identity with a changed path is `Moved`. Snapshot graph nodes and edges are compared independently to expose dependency graph changes.

The engine does not fabricate repository evidence. Missing snapshot facts remain missing, and an Execution Result claim is marked as Execution Result evidence rather than repository evidence.

## Output

`EngineeringDiff` is an immutable, persisted, versioned result containing:

- new, modified, and removed APIs
- category-specific added, modified, removed, and moved changes
- refactoring and breaking-change claims
- dependency graph node and edge changes
- impact level and score
- evidence, confidence, warnings, summary, lineage, and diagnostics

Impact levels are `Low`, `Medium`, `High`, and `Critical`. Documentation-only changes remain low impact. API removals, architecture replacement, security changes, database changes, graph changes, and explicit breaking changes raise the score according to their engineering risk.

## Safety boundary

The engine:

- performs no Git operations
- reads no repository files
- writes no repository files
- invokes no AI provider
- invokes no Validation or QA service

Its only write is the immutable Engineering Diff record in the platform store.

## Events

- `EngineeringDiffCompleted`
- `EngineeringDiffFailed`

Events preserve the Execution Result session and correlation lineage when supplied.

## APIs

| Method | Route | Contract |
| --- | --- | --- |
| `POST` | `/engineering-diff` | Build and persist a semantic Engineering Diff. |
| `GET` | `/engineering-diff/{id}` | Retrieve an immutable Engineering Diff. |

## Runtime position

```text
Repository Snapshot Before
            +
Repository Snapshot After
            +
Structured Execution Result
            |
Semantic Projection
            |
Engineering Diff
            |
Future Validation and QA triggers
```
