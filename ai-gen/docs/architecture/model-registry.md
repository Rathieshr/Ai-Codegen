# Model Registry

## Purpose

Model Registry is the canonical read-only catalog of AI model families supported by HEI. It centralizes model identity and declared capabilities without creating a provider adapter, selecting a model, checking provider health, or changing runtime routing.

## Boundary

```text
Model Registry
  -> ModelProfile metadata
ModelProfile
  -> Model Adapter
  -> ExecutionPrompt

Future provider milestone:
ExecutionPrompt
  -> Provider Runtime
```

Milestone 4.4 implements only the registry boundary. Milestone 4.5 adds deterministic adapters for selected profiles while provider configuration and execution remain unchanged.

## ModelProfile

Each profile contains:

- stable model family ID and display name
- provider
- context window
- reasoning support
- maximum output
- tool support
- vision support
- streaming support
- temperature support
- JSON support
- system prompt support
- capability tags
- enabled state
- registry version

Profiles represent versioned HEI operational baselines, not live provider discovery or a guarantee that every vendor deployment exposes every capability. Deployment-specific overrides and provider runtimes remain future concerns.

## Supported Profiles

The initial registry contains:

- GPT
- Codex
- Claude
- Gemini
- GLM
- Qwen
- Ollama
- DeepSeek
- Phi

IDs are lowercase and stable: `gpt`, `codex`, `claude`, `gemini`, `glm`, `qwen`, `ollama`, `deepseek`, and `phi`.

## API

### List models

`GET /models`

Returns profiles in deterministic registry order with a total count.

### Get model

`GET /models/{id}`

Lookup is case-insensitive. An unknown ID returns `404 Model profile not found`.

## Registry Non-goals

The registry itself does not implement:

- provider clients
- deployment discovery
- provider health
- credentials
- routing or fallback
- model selection
- runtime capability negotiation

Model Adapters consume defensive copies of these profiles. They do not mutate registry data.
