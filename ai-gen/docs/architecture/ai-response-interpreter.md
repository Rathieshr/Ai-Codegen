# AI Response Interpreter

## Purpose

The AI Response Interpreter converts a raw provider response into evidence-backed engineering artifacts. It is deterministic and provider-neutral. It performs no repository writes, validation, QA, provider calls, or LLM repair.

## Inputs

- Execution Session
- AI Provider Response
- Execution Manifest
- Repository Snapshot, when available

The Execution Manifest and Repository Snapshot are evidence and lineage inputs. Their contents are not treated as provider output and are not copied into the extracted result.

## Output

The persisted interpretation contains:

- Structured execution result and response type.
- Primary runtime artifacts, preserving Milestone 5.1 comparison compatibility.
- Rich engineering artifacts with confidence, evidence, source, reason, and repository evidence status.
- Category projections for files, folders, classes, interfaces, methods, APIs, database changes, configuration changes, documentation changes, tests added/modified/removed, TODOs, FIXMEs, breaking changes, warnings, risks, architecture notes, implementation notes, and unknown items.
- Manifest, repository snapshot, session, and correlation lineage.
- Interpretation diagnostics and explicit safety counters.

## Evidence rules

1. An artifact is extracted only when it is explicitly present in structured response data or identifiable response text.
2. A folder may be derived from an explicitly named file path, and its reason says so.
3. A supplied Repository Snapshot can mark a path `Matched` or `Unverified`.
4. Without a Repository Snapshot, paths remain provider claims marked `Unavailable` and confidence is reduced.
5. The interpreter never invents repository paths, symbols, APIs, or evidence.

## Response support

- OpenAI-compatible chat-completion envelopes.
- Provider envelopes using `message.content`, `response`, `content`, `text`, or `output`.
- Structured objects with artifacts, files, changes, and category fields.
- JSON strings and fenced JSON.
- Markdown and fenced code.
- Plain text.
- Unknown provider objects, retained as `NeedsReview` with warnings.

## Events

- `ResponseInterpreted`
- `ArtifactsExtracted`
- `ResponseInterpretationFailed`

All events retain the Execution Session correlation ID.

## Compatibility boundary

Milestone 5.1 consumes `artifacts`, containing primary change artifacts suitable for Engineering Diff comparison. Milestone 5.2 consumers use `engineeringArtifacts` and `extraction` for the richer engineering interpretation. This prevents classes, methods, warnings, and architecture notes from being misrepresented as changed repository files.
