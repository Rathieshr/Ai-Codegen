# Provider Router

## Purpose

Provider Router selects an appropriate registered AI model and produces a deterministic optimized prompt. It records a routing decision only; it never invokes a model or provider API.

```text
Execution Manifest
  + Execution Mode
  + Repository Mode
  + Target Task
  + User Preference
  + Available Models
  -> Provider Router
  -> Prompt Compiler
  -> Token Intelligence
  -> Model Adapter
  -> Prompt Optimizer
  -> Prompt Cache
  -> ProviderRoutingResult
```

The Execution Manifest remains the prompt's only engineering-context input. Repository Mode supplied by the caller is advisory; when it conflicts with the manifest, the manifest value remains authoritative and the mismatch is recorded.

## Routing Rules

| Target | Priority |
|---|---|
| Coding | Codex, then Claude Code through the Claude model profile |
| Architecture | GPT |
| UI | Gemini |
| Documentation | GPT |
| Large Context | Claude |
| Local | Ollama |

The router first resolves the target from explicit Target Task metadata, then task language, then Execution Mode, and finally defaults to Coding. A valid user model preference may lead the candidate order, but it must still be available, enabled, adapter-backed, and able to fit a supported token budget.

## Eligibility And Fallback

Every candidate is checked for:

- membership in the request's available-model set
- an enabled Model Registry profile
- a deterministic Model Adapter
- a supported token budget within the model context window
- successful adapter context validation
- non-blocked Prompt Optimizer output

Failed candidates and reasons are retained in diagnostics. The router tries the next candidate rather than hiding the failure. If no candidate is eligible, routing fails visibly and no prompt is returned.

If `availableModels` is omitted, enabled Model Registry profiles are considered. An explicitly empty list means no models are available.

## Output

`ProviderRoutingResult` is immutable and content-addressed. It includes:

- selected model, provider, and context window
- routing target and normalized execution mode
- selected token budget
- whether user preference or fallback was applied
- the complete optimized prompt
- human-readable reasons and warnings
- the routing-rule catalog
- candidate order, rejected models, and every budget attempt
- complete prompt lineage IDs
- provider/network/LLM usage flags fixed to false/zero

## APIs

- `POST /provider-router/route`
- `GET /provider-router/decisions/{routingId}`
- `GET /provider-router/decisions/{routingId}/diagnostics`

No provider transport or UI is included in Milestone 4.8.

From Milestone 4.9, `ProviderRouterService` checks Prompt Cache before compiling. A complete lineage and route match returns the persisted immutable routing result; a miss runs the existing deterministic pipeline and records the result. Cache metadata is transient response information and does not alter the routing artifact's immutable hash.
