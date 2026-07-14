# Prompt Cache

## Purpose

Prompt Cache prevents deterministic prompt regeneration when the complete engineering lineage and selected route are unchanged.

```text
Execution Manifest
  + Execution Package Version
  + Repository Snapshot
  + Knowledge Version
  + Engineering Memory Version
  + Model
  + Execution Mode
  + Routing Target
  -> Prompt Cache
     -> Hit: reuse ProviderRoutingResult
     -> Miss: Provider Router generates and caches the prompt
```

The cache sits inside `ProviderRouterService`. Existing callers continue using `POST /provider-router/route`; no second prompt-generation path is introduced.

## Canonical Key

Every key includes:

- Execution Manifest schema version and immutable identity
- Execution Package ID and version
- Repository Snapshot version
- Knowledge version
- Engineering Memory version
- selected model ID
- normalized Execution Mode
- routing target

The immutable manifest identity protects against two different manifests sharing the same schema version. The routing target prevents prompts for UI, architecture, documentation, and coding from colliding.

## Invalidation

A changed key is always a cache miss. Related active entries are marked `Invalidated` when the package lineage is stable and any of these dimensions change:

- Execution Manifest
- Execution Package version
- Repository Snapshot
- Knowledge version
- Engineering Memory version
- model
- Execution Mode
- routing target

Manual invalidation is available for operational changes. Invalidated entries remain persisted for diagnostics but are never returned as hits.

## Metrics

Prompt Cache persists:

- requests, hits, misses, and hit rate
- writes and invalidations
- generations avoided
- estimated prompt tokens saved
- estimated generation milliseconds saved
- active and invalidated entry counts

Savings are estimates based on the cached prompt token count and the original deterministic generation duration. No provider call or provider cost is implied.

## APIs

- `GET /prompt-cache/metrics`
- `GET /prompt-cache/entries/{cacheKey}`
- `POST /prompt-cache/invalidate`

Prompt Cache performs no provider invocation, network request, retrieval, or LLM operation.
