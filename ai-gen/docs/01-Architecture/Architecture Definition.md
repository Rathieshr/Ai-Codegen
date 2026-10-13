# Architecture Definition

## System intent

HEI is a modular Engineering Intelligence Platform. It connects experience surfaces to deterministic engineering intelligence, governed agent workflows, shared platform services, and enterprise systems.

## Invariants

1. Repository Intelligence and the Knowledge Registry are factual authorities.
2. Engineering Memory contains only approved or validated reusable evidence.
3. Context Intelligence is the only context retrieval, selection, and budgeting authority.
4. The Execution Package Builder consumes only a Context Capsule and execution-local request data.
5. Prompt Intelligence compiles an Execution Manifest from the Execution Package; it does not retrieve context.
6. Validation and QA consume the Execution Package plus permitted runtime evidence.
7. Agents coordinate services but never approve, merge, or bypass policy.
8. Platform Foundation owns cross-cutting jobs, events, audit, notifications, activity, health, and policies.

## Architecture status

The converged backend implements these boundaries for Execution Manifest, Validation, QA, Engineering Memory Capture, Agent Runtime, and VS Code consumers. Azure DevOps automation, Portal, and SDK package-only migration remains incremental.
