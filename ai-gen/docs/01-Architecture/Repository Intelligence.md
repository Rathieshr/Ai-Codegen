# Repository Intelligence Architecture

Repository Intelligence synchronizes repository evidence and publishes versioned snapshots.

`Registration -> Synchronization -> Snapshot -> Parse -> Engineering Graph -> File Ranking -> Context source`

Repository modes are `CodeIndexed`, `KnowledgeSnapshot`, and `Unavailable`. Only `CodeIndexed` permits direct file, API, symbol, and test evidence. Knowledge snapshots may expose modules, flows, standards, and architecture knowledge but never synthesize paths or symbols.

The implementation currently supports local/JSON persistence for foundation and test flows. Production-scale multi-writer persistence and remote synchronization workers remain deployment concerns.

## Repository Detection

Requirement Intelligence calls Repository Detection after normalization and analysis, before the mandatory Requirement Summary approval.

`Requirement Context -> Requirement Analysis -> Repository Detection -> Requirement Summary -> Approved Repository Mapping -> Planning`

Detection ranks only registered repositories. Its evidence can include requirement keywords, requested technology, business domain, indexed modules and languages, approved Engineering Memory, repository metadata, Azure DevOps project ownership, the current workspace, and prior human overrides. The response contains one suggested repository, confidence, an engineering reason, evidence, and ranked alternatives.

The recommendation does not silently alter a Requirement Context. The mapping is committed when the Requirement Summary is approved. A manual override is persisted immediately as a versioned context change, forces re-analysis, and becomes a bounded learning signal for similar requirements. Repository snapshots remain the source of truth; override learning cannot invent modules, files, symbols, or technologies.

Public endpoints:

- `POST /repositories/detect`
- `GET /repositories/suggestions`
- `POST /repositories/suggestions/{requirementId}/override`
