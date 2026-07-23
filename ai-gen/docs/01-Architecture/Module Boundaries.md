# Module Boundaries

## Engineering Intelligence

`backend/engineering_intelligence` is the reusable orchestration boundary for
engineering evidence. It composes Repository Intelligence, synchronized Azure
DevOps data through the HEI Platform SDK, Engineering Memory, and existing
planning similarity logic into the canonical `EngineeringContext`.

The module does not own repository scanning, ADO transport, memory storage, or
planning generation. Requirement, Planning, Execution, Validation, Approval,
and future agents consume its context or bounded projections instead of
querying those providers independently. The legacy Project Intelligence module
remains a compatibility service for existing project-profile and artifact
APIs.

| Module | Owns | Must not own |
| --- | --- | --- |
| Planning Intelligence | Intent, capabilities, artifact generation, lineage, approvals | Repository scanning or prompt delivery |
| Repository Intelligence | Synchronization, snapshots, symbols, graph, file ranking | Planning decisions or invented code evidence |
| Context Intelligence | Retrieval, normalization, ranking, filtering, token budget, capsule | Artifact generation or provider reasoning |
| Execution Intelligence | Deterministic Execution Package and implementation plan | Independent context retrieval |
| Prompt Intelligence | Provider profile, prompt sections, budget, Execution Manifest | Repository or memory queries |
| Validation Intelligence | Acceptance, scope, repository, standards, and test alignment | Planning regeneration |
| QA Intelligence | Coverage, test gaps, regression, risk, release recommendation | Story/task mutation |
| Engineering Memory | Approved reusable patterns and decisions | Raw prompts, rejected artifacts, repository truth |
| Agent Runtime | Events, sequencing, retries, approval checkpoints | Approval or direct repository modification |
| Platform Foundation | Jobs, events, audit, activity, notifications, health, policies | Domain intelligence |

Compatibility adapters may translate shapes but may not cross these authority boundaries.
