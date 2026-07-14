# Model Adapters

## Purpose

Model Adapters transform one immutable `BudgetedPrompt` into a model-oriented `ExecutionPrompt`. They reorder already-approved sections and tune deterministic wording for a model family. They do not retrieve context, remove engineering evidence, call an LLM, or invoke provider APIs. Prompt Optimizer is the downstream owner of mode-specific emphasis, instruction merging, appendix placement, and prompt quality scoring.

## Pipeline

```text
Execution Manifest
  -> Prompt Compiler
  -> CompiledPrompt
  -> Token Intelligence
  -> BudgetedPrompt
  -> Model Adapter
  -> ExecutionPrompt
  -> Prompt Optimizer
  -> OptimizedExecutionPrompt
```

Token Intelligence remains between Prompt Compiler and Model Adapter because section reduction must happen before model-specific rendering. An adapter blocks an incompatible budget; it does not silently trim protected context.

## Supported Adapters

Milestone 4.5 provides adapters for:

- GPT
- Codex
- Claude
- Gemini
- GLM
- Qwen
- Ollama

DeepSeek and Phi remain Model Registry profiles but do not have adapters in this milestone.

## Contract

Every adapter consumes:

- an immutable, ready `BudgetedPrompt`
- the matching `ModelProfile`

Every adapter produces an immutable `ExecutionPrompt` containing:

- execution prompt ID
- prompt version
- model and provider identity
- source BudgetedPrompt and CompiledPrompt lineage
- system prompt when supported
- rendered prompt
- reordered sections with original structured content
- estimated tokens and available model input
- status and warnings
- adapter and capability diagnostics

## Adaptation Rules

Adapters may:

- reorder sections
- rename section headings
- add concise model-oriented objectives
- add instructions supported by declared model capabilities
- separate the system prompt when supported

Adapters may not:

- retrieve repository, knowledge, memory, planning, or graph context
- alter structured section content
- remove acceptance criteria or repository evidence
- perform token reduction
- exceed the model profile context window silently
- select credentials or deployments
- call providers

If the BudgetedPrompt or rendered prompt cannot fit, the adapter returns `Blocked` and directs the caller to rerun Token Intelligence with a smaller supported budget.

## Model-Specific Ordering

Each adapter uses a deterministic order suited to its operating profile. Codex is repository and instruction first, Claude is constraint first, Gemini emphasizes grounded context, Qwen is implementation first, and Ollama uses compact local-model wording. Section content remains traceable to the same BudgetedPrompt.

## Public Python API

```python
from backend.model_adapters import compile_execution_prompt

execution_prompt = compile_execution_prompt(budgeted_prompt, "codex")
```

No provider HTTP API is introduced by this milestone.
