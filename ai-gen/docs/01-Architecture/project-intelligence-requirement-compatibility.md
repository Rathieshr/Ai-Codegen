# Project Intelligence Requirement Compatibility

## Capability inventory

The stabilized Project Intelligence implementation is not a standalone requirement engine. Its reusable capability is distributed across `ProjectIntelligenceService` and its established helpers:

- `ProjectIntelligenceService.get_profile()` and `get_knowledge_cache()` provide approved project and Knowledge Registry context.
- `_project_phi_json()` and `_project_phi_probe()` provide provider selection, Phi health checks, adaptive retries, prompt-budget enforcement, response normalization, diagnostics, and deterministic fallback metadata.
- `_project_summary_context()` and the prompt-budget pipeline select and compress repository, flow, module, application, standard, and context-capsule evidence.
- `_reject_generic_acceptance_criteria()`, `_acceptance_criteria_categories()`, and `_acceptance_criteria_quality_score()` provide the stabilized acceptance-quality gate.
- Existing provider metadata records model, token, latency, fallback, prompt-budget, and health diagnostics.

The older workflow did not expose a requirement-specific public contract. Calling its private helpers from Requirement Intelligence would couple the new workflow to implementation details.

## Compatibility boundary

`ProjectIntelligenceService` exposes a narrow requirement-analysis facade that delegates to the stabilized pipeline. `ProjectIntelligenceRequirementAnalyzer` translates between current Requirement Analysis models and that facade.

```text
Requirement Intake
  -> Engineering Context
  -> ProjectIntelligenceRequirementAnalyzer
  -> ProjectIntelligenceService requirement facade
  -> stabilized Phi, context, budget, and quality pipeline
  -> current Requirement Analysis and Acceptance Criteria models
```

The adapter does not scan repositories, select providers, assemble raw prompts, or generate deterministic Acceptance Criteria. It preserves the current UI, approval workflow, and Planning contracts.

## Primary and fallback behavior

- Project Intelligence plus Phi is the primary path when it returns valid, evidence-backed output.
- The existing deterministic `IntelligentAcceptanceCriteriaEngine` remains a degraded fallback only.
- Fallback output is labelled `Deterministic Fallback`, carries reduced confidence, and remains reviewable and retryable.
- Source criteria remain `Source Derived`; approved imported criteria remain `Imported`; user changes remain `User Edited`.
- Provider-generated criteria are labelled `Project Intelligence Generated` and include provider, model, prompt version, context version, knowledge version, repository revision, evidence mapping, and confidence basis.

## Migration

The facade can run in shadow mode using `AI_GEN_REQUIREMENT_PI_SHADOW_MODE`. Shadow mode records Project Intelligence diagnostics while preserving the current result. Once regression comparisons pass, Project Intelligence is primary and deterministic generation remains available only for degraded operation.
