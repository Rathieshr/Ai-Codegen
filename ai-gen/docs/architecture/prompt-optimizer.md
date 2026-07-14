# Prompt Optimizer

## Purpose

Prompt Optimizer converts one immutable `ExecutionPrompt` into an immutable, mode-aware `OptimizedExecutionPrompt`. It improves emphasis and removes repeated instructions after model adaptation without rebuilding project context or invoking an AI provider.

```text
Execution Package
  -> Execution Manifest
  -> Prompt Compiler
  -> CompiledPrompt
  -> Token Intelligence
  -> BudgetedPrompt
  -> Model Adapter
  -> ExecutionPrompt
  -> Prompt Optimizer
  -> OptimizedExecutionPrompt
  -> Provider transport
```

The optimizer is downstream from Model Adapter because it uses the selected model's objective, system-prompt behavior, and model instructions. It is not a second token-budget stage: Token Intelligence remains responsible for fitting approved structured context into a budget.

## Contract

Input:

- one immutable `ExecutionPrompt`
- one supported execution mode

Output:

- immutable lineage to the source ExecutionPrompt, BudgetedPrompt, and CompiledPrompt
- optimized main sections
- an appendix containing retained lower-priority context
- Prompt Quality Score from 0 to 100
- Prompt Confidence from 0.0 to 1.0
- explainable diagnostics

The optimizer never queries Repository Intelligence, Knowledge Registry, Engineering Memory, or raw work items. It never calls an LLM or provider.

## Protected Engineering Content

The first three main sections always consist of:

- repository evidence
- implementation guidance
- acceptance and validation

Modes can change the relative order of those three sections, but cannot move them to the appendix or alter their structured content. Diagnostics prove that acceptance, repository evidence, and implementation guidance remain unchanged.

## Modes

Supported modes are:

- Implementation
- Bug Fix
- Refactor
- Architecture
- Review
- Documentation
- Testing
- Optimization

Each mode supplies a deterministic objective, focused instructions, section priority, and appendix policy. For example, Bug Fix emphasizes root cause and regression prevention, while Testing emphasizes acceptance, repository placement, and QA coverage.

## Repetition and Appendix Rules

Exact repeated values are removed from non-protected structured sections. Exact or strongly similar instruction strings are merged, retaining the more specific form. Protected engineering evidence is never deduplicated by this stage.

Lower-priority whole sections are moved to the appendix, not deleted. The final prompt remains complete while its main body emphasizes the requested engineering operation.

## Scoring

Prompt Quality Score is an explainable sum of:

- structure
- clarity
- repository grounding
- acceptance coverage
- actionability

Prompt Confidence combines:

- source prompt readiness
- repository evidence quality
- acceptance evidence
- implementation evidence
- Prompt Quality Score

Unavailable repository context lowers both values and returns `NeedsReview`. A blocked source prompt or a final context overflow remains `Blocked`; optimization never hides an upstream budget failure.

## Diagnostics

Diagnostics include:

- execution mode
- source and optimized token estimates
- repetitions removed
- instructions merged
- sections moved to appendix and reasons
- main and appendix order
- quality and confidence breakdowns
- protected-content preservation checks
- context-limit status
- provider/network/LLM usage flags
