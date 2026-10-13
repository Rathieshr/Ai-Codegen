# Prompt Compiler

## Purpose

Prompt Compiler converts one immutable Execution Manifest into a deterministic, model-independent `CompiledPrompt`. It organizes engineering intent into stable sections before any provider, token budget, or final prompt formatting decision is made.

```text
Execution Package
        |
        v
Execution Manifest
        |
        v
Prompt Compiler
        |
        v
CompiledPrompt
        |
        v
Prompt Budget Manager
        |
        v
Model Adapter
        |
        v
Execution Prompt
```

## Ordered sections

The compiler always emits these sections in this order:

1. Business Objective
2. Repository Context
3. Implementation Guidance
4. Validation
5. QA
6. Constraints
7. Instructions

Input order, dictionary order, manifest size, and repository mode do not change this sequence.

## Compilation rules

- Normalize whitespace and stable dictionary ordering.
- Remove duplicate list values without truncating unique content.
- Keep acceptance criteria with Validation.
- Move dependencies, engineering standards, blocked scope, architecture constraints, risks, and warnings into Constraints.
- Keep implementation steps and boundaries in Implementation Guidance.
- Add model-neutral execution instructions only.
- Do not estimate or optimize tokens.
- Do not select a provider or model.
- Do not format a final prompt.
- Do not call an LLM.

## Repository modes

`CodeIndexed` may include selected files, APIs, services, modules, flows, and graph references.

`KnowledgeSnapshot` may include knowledge-level modules and flows, but the compiler removes file, API, and service evidence and records a warning.

`Unavailable` contains no repository evidence and records an explicit warning. The Instructions section tells downstream systems not to invent repository evidence.

## Persistence and identity

`CompiledPrompt` is content-addressed from compiler version, manifest lineage, ordered sections, and warnings. Recompiling the same manifest returns the existing immutable artifact. Large manifests are not truncated by Prompt Compiler. Token Intelligence is the downstream owner of deterministic estimation, output reservation, and whole-value context reduction.

## API

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/prompt-compiler/compile` | Compile from `executionManifest` or `executionManifestId` |
| `GET` | `/prompt-compiler/{id}` | Retrieve the immutable compiled prompt sections |

The compatibility `DeveloperPrompt` package consumer now follows Package -> Manifest -> CompiledPrompt -> BudgetedPrompt -> provider/model adapter -> Execution Prompt.
