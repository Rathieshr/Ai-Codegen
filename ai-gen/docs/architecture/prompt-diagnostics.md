# Prompt Diagnostics

## Purpose

Prompt Diagnostics explains one immutable `OptimizedExecutionPrompt` without rebuilding context or invoking a provider.

```text
Execution Package
  -> Execution Manifest
  -> Prompt Compiler
  -> Token Intelligence
  -> Model Adapter
  -> Prompt Optimizer
  -> OptimizedExecutionPrompt
  -> Prompt Diagnostics
```

Diagnostics is an observer of this lineage. It does not alter the prompt, retrieve Repository Intelligence, query Knowledge Registry or Engineering Memory, or send the prompt to a model.

## Artifact

Each content-addressed `PromptDiagnostics` artifact records:

- Execution Manifest ID and version
- Execution Package ID and version
- repository snapshot
- knowledge version
- engineering-memory version
- model ID, name, provider, registry version, and context window
- prompt character, byte, and line counts
- estimated input tokens and source prompt tokens
- optimization ratio and percentage reduction
- Prompt Confidence and Prompt Quality Score
- warnings
- included files with confidence, source, and reason
- excluded files with source and rejection/removal reason
- estimated cost
- estimated duration

The artifact retains immutable hashes for both the optimized prompt and Execution Manifest so a diagnostic result cannot be attached to unrelated lineage.

## File Explainability

Included files come only from the optimized prompt's repository section. Excluded files are derived from:

1. Execution Manifest files absent from the final prompt.
2. Token Intelligence removal diagnostics when a matching value hash is available.
3. Execution Package excluded or rejected file context.

No file path is invented by Prompt Diagnostics.

## Cost And Duration

The Model Registry currently describes capabilities and context limits, not commercial pricing or runtime throughput. Prompt Diagnostics therefore returns `Unavailable` estimates by default instead of inventing values.

Callers may supply a versioned operational estimation profile containing:

- input cost per million tokens
- output cost per million tokens
- expected output tokens
- currency
- tokens per second

With that profile, Prompt Diagnostics computes deterministic estimates and labels them as estimates whose actual provider billing and runtime may differ.

## APIs

- `POST /prompt-diagnostics/build`
- `GET /prompt-diagnostics/{diagnosticsId}`
- `GET /prompt-diagnostics/{diagnosticsId}/summary`
- `GET /prompt-diagnostics/prompts/{optimizedPromptId}`

The build endpoint accepts an immutable optimized prompt and resolves its Execution Manifest and Execution Package through persisted IDs when available. No UI is included in Milestone 4.7.
