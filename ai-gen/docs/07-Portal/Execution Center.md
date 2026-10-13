# Execution Center

## Purpose

Execution Center is the read-only operational projection for an HEI engineering execution. It joins persisted artifacts from Planning, Execution Package, Execution Manifest, Prompt Compiler, AI Execution Runtime, Validation Trigger, QA Trigger, Engineering Memory candidates, and PR candidates.

It does not generate execution artifacts and does not own lifecycle transitions. Retry delegates to AI Execution Runtime recovery.

## Timeline

1. Planning
2. Execution Package
3. Execution Plan
4. Prompt
5. AI Runtime
6. Validation
7. QA
8. Memory
9. Completed

Missing persisted artifacts remain visible as `Missing` or `Not Started`; the projection does not infer IDs or fabricate traceability.

## Identity

Records are joined using, in order:

- Execution Package ID
- Execution Manifest and compiled prompt source IDs
- Runtime session ID
- Correlation ID
- Persisted source lineage

The Execution Center ID is the package ID when available, otherwise the runtime session ID.

## APIs

- `GET /execution`
- `GET /execution/{id}`
- `GET /execution/{id}/timeline`
- `GET /execution/{id}/diagnostics`
- `POST /execution/{id}/retry`

The retry route is an additive operation used by the workspace and invokes the existing runtime retry service.

## UI Boundary

Execution Center is the primary Execution workspace. Existing generation and implementation tools remain under the collapsed `Execution Intelligence Workspace` section for progressive disclosure.
