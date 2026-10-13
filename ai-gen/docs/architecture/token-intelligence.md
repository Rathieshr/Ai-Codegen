# Token Intelligence

## Purpose

Token Intelligence converts one immutable `CompiledPrompt` into an immutable, budget-safe `BudgetedPrompt`. It owns deterministic token estimation, output reservation, input allocation, and low-value context removal. It does not select a provider, adapt model syntax, format prose, or call an LLM.

## Pipeline

```text
Execution Package
  -> Execution Manifest
  -> Prompt Compiler
  -> CompiledPrompt
  -> Token Budget Engine
  -> BudgetedPrompt
  -> Model Adapter
  -> Execution Prompt
```

The older provider-aware Prompt Budget Manager remains a downstream adapter safeguard while consumers migrate. It is not the canonical Token Intelligence artifact builder.

## Supported Budgets

Token Intelligence accepts total context budgets of:

- 1,024
- 2,048
- 4,096
- 8,192
- 16,000
- 32,000
- 128,000 tokens

Each profile reserves output tokens before calculating the available input budget. A caller may override the output reserve, but it must remain smaller than the requested total budget.

## Preservation Rules

The following context is protected:

- every acceptance criterion
- the complete repository evidence selected by Prompt Compiler
- validation guidance

The engine may remove complete lower-value values from QA background, risks, warnings, assumptions, repeated implementation detail, and other optional context. It never slices strings or serialized JSON. All seven compiler sections remain in deterministic order.

If protected context cannot fit the input budget, the result is `Blocked` with `protected_context_exceeds_input_budget`. Protected content remains intact so a caller can choose a larger supported budget.

## Diagnostics

Every `BudgetedPrompt` reports:

- estimated tokens before and after optimization
- provider-reported actual tokens when supplied
- reserved output and remaining input budget
- section token estimates before and after
- every removed JSON path, reason, token estimate, preview, and content hash
- acceptance, repository, and validation preservation checks
- JSON integrity and truncation status
- budget block reason and overflow

The estimator uses canonical compact JSON and HEI's deterministic four-characters-per-token heuristic. Actual usage remains provider telemetry and is never fabricated.

## API

### Optimize

`POST /token-intelligence/optimize`

```json
{
  "compiledPromptId": "compiledprompt_123",
  "budgetTokens": 4096,
  "reservedOutputTokens": 768,
  "actualTokens": 2710,
  "correlationId": "corr-123"
}
```

The request may provide an inline `compiledPrompt` instead of its identifier.

### Retrieve

`GET /token-intelligence/{budgetedPromptId}`

Budgeted prompts are content-addressed, persisted, immutable, and reusable.
