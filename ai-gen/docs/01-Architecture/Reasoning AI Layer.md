# Reasoning AI Layer

## Purpose

The HEI Reasoning AI Layer converts canonical `EngineeringContext` facts into
explainable engineering judgment. Engineering Intelligence owns repository,
Azure DevOps, documentation, memory, dependency, and architecture facts.
Reasoning AI never discovers those facts independently.

```text
Engineering Intelligence
        |
        v
EngineeringContext
        |
        v
ReasoningEngine
  -> PromptBuilder
  -> Provider Registry
  -> Response Validator
  -> Confidence Calculator
  -> Decision Explainer
        |
        v
Workflow Result
```

Requirement Intelligence applies the mandatory
[AI Reasoning Governance](./AI%20Reasoning%20Governance.md) boundary after
provider reasoning and before Acceptance Criteria or canonical Requirement
Analysis finalization. Provider output is advisory until each statement has
been classified and its provenance recorded.

## Boundary

The public entry point is `backend.reasoning.ReasoningEngine`. It accepts only a
canonical `EngineeringContext` dictionary or model with `to_dict()`.

The layer must not:

- scan repositories or source files;
- query Azure DevOps;
- index markdown;
- search Engineering Memory directly;
- invent files, modules, APIs, dependencies, or work items.

Evidence references are created from Engineering Context. Provider references
that are not in that catalog are removed. A response with no valid evidence is
rejected.

## Providers

Providers implement `IReasoningProvider`:

- `analyze`
- `recommend`
- `summarize`
- `refine`
- `reason`

The registry supports Phi, GPT/OpenAI, Claude, Gemini, and local-model adapters.
Workflow code selects a provider by preference, but it never imports a provider.
Transport callables can be injected without changing the reasoning contract.

Selection order is:

1. request or configured provider;
2. configured fallback providers;
3. deterministic reasoning.

Phi is optional. An unavailable provider is reported as deterministic mode, not
as a workflow failure.

## Prompt Construction

Prompts are assembled from reusable, versioned workflow templates and structured
sections. The existing Prompt Budget Manager applies provider-specific context
limits and compression. Required sections and evidence remain visible in
diagnostics.

Supported templates include requirement analysis, planning recommendation,
planning proposal, execution package, validation, risk analysis, architecture
review, and code review.

## Response Safety

Provider output is normalized through the shared Provider Response Parser. The
validator requires:

- recommendation;
- reasoning;
- alternatives;
- evidence;
- confidence.

Malformed or invalid output receives one retry. A second failure returns an
evidence-backed deterministic result. Every result includes risks, trade-offs,
impact, confidence components, prompt version, provider/model, and telemetry.

## Privacy and Telemetry

Telemetry records provider, model, workflow, latency, token usage, estimated
cost, retries, confidence, prompt version, timestamp, and correlation ID.
Prompts are excluded unless `HEI_REASONING_LOG_PROMPTS=1`.

## Adoption

Existing provider-specific workflows remain available as compatibility wrappers.
New and migrated workflows must call `ReasoningEngine` and pass the
`EngineeringContext` produced by Engineering Intelligence. They must not call
provider clients directly.
