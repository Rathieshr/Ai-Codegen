# HEI Terminology

## Canonical product language

| Previous term | Canonical term | Meaning |
| --- | --- | --- |
| AI Gen | HEI Platform | The enterprise engineering platform |
| Planner | Planning Intelligence | Intent, capability, artifact, and approval intelligence |
| Dashboard | Engineering Command Center | Lifecycle status, next action, health, and blockers |
| Repository Scan | Repository Synchronization | Full or incremental repository evidence refresh |
| Memory | Engineering Memory | Approved, versioned, reusable engineering knowledge |
| Prompt Optimizer | Prompt Intelligence | Model adaptation, execution-prompt formatting, and provider diagnostics |
| Prompt Builder | Prompt Compiler | Converts an Execution Manifest into deterministic model-independent sections |
| Developer Prompt | Execution Prompt | Compatibility name for provider-ready implementation instructions |
| Package Builder | Execution Package Builder | Deterministically creates the canonical execution contract |

## Compatibility policy

Canonical terms apply to new product copy, documentation, events, and public contracts. Existing code and APIs may temporarily retain compatibility identifiers such as `DeveloperPrompt`, `PromptBuilder`, `build-dev-prompt`, and `AI_GEN_*` environment variables.

Compatibility identifiers must:

- Be documented as aliases, not presented as the preferred product term.
- Continue to behave as before until a versioned migration is published.
- Map to one canonical concept without creating a second implementation path.
- Be removed only through an ADR and a deprecation window.

## Artifact distinction

- **Context Capsule:** selected, bounded, versioned engineering context.
- **Execution Package:** canonical structured implementation specification.
- **Implementation Plan:** human-readable strategy derived from the package.
- **Execution Manifest:** immutable model-independent engineering execution specification derived from the package.
- **CompiledPrompt:** deterministic ordered sections produced from the Execution Manifest.
- **BudgetedPrompt:** immutable CompiledPrompt projection optimized for an explicit context and output budget without removing protected engineering evidence.
- **Token Intelligence:** deterministic estimation, output reservation, budget allocation, and whole-value context reduction before model adaptation.
- **Model Registry:** read-only catalog of versioned HEI model family profiles and declared capabilities.
- **ModelProfile:** adapter-independent metadata describing one supported model family.
- **Model Adapter:** deterministic model-family renderer that converts a BudgetedPrompt into an ExecutionPrompt without invoking a provider.
- **Execution Prompt:** provider-ready implementation instructions produced after budgeting and model adaptation.
- **Validation Report:** implementation alignment evidence.
- **QA Report:** release-readiness evidence.

An Execution Manifest never retrieves repository, knowledge, or memory context independently. Prompt Compiler never performs token optimization or model adaptation. Token Intelligence never selects or invokes a provider.
