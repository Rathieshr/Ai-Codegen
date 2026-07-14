# Execution Manifest Foundation

## Purpose

Execution Manifest is HEI's canonical, model-independent engineering execution specification. It is a deterministic projection of one persisted Execution Package and carries engineering intent without prompt syntax, model instructions, or provider selection.

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
Model Adapter
        |
        v
Execution Prompt
```

## Responsibility boundary

The Execution Manifest builder may:

- project approved execution intent from one Execution Package;
- preserve package, capsule, repository, knowledge, planning, and memory versions;
- normalize acceptance criteria, repository evidence, standards, risks, warnings, confidence, and token estimates;
- calculate a content hash and immutable identity.

It may not:

- query Repository Intelligence, Knowledge Registry, Engineering Memory, or the Engineering Graph;
- rebuild a Context Capsule or Execution Package;
- select an AI provider or model;
- format a prompt;
- call an LLM.

Prompt Compiler is a downstream Prompt Intelligence concern. It accepts one immutable Execution Manifest and emits deterministic, model-independent `CompiledPrompt` sections. Prompt Budget Manager and Model Adapter then produce the Execution Prompt. The compatibility consumer identifier `DeveloperPrompt` remains supported while clients migrate.

## Canonical contract

Every manifest contains:

- `manifestId`, `manifestVersion`, `immutable`, `immutableHash`, and `generatedAt`;
- `sourcePackageId` and source artifact versions;
- objective and business goal;
- acceptance criteria and their implementation/validation mapping;
- repository context, relevant files, and dependencies;
- implementation, validation, and QA guidance;
- engineering standards, risks, warnings, confidence, and token estimates;
- diagnostics proving that no retrieval, prompt formatting, provider selection, or LLM call occurred.

## Immutability and persistence

The manifest identity is content-addressed from its canonical engineering fields. Building the same package projection returns the existing manifest. A changed package produces a new manifest identity. There is no update or delete API. Stored values and API responses are copied so callers cannot mutate persisted content in process.

The current store is local JSON through the platform storage abstraction. The contract is storage-neutral and can move to an enterprise store without changing callers.

## API

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/execution-manifests/build` | Build or reuse a manifest from `executionPackage` or `executionPackageId` |
| `GET` | `/execution-manifests/{id}` | Retrieve the complete immutable manifest |
| `GET` | `/execution-manifests/{id}/summary` | Retrieve the compact engineering summary |
| `GET` | `/execution-manifests/{id}/diagnostics` | Retrieve lineage, immutability, counts, timing, and token diagnostics |

## Consumer compatibility

Validation, QA, memory capture, agents, and VS Code remain Execution Package consumers. Only prompt generation follows the additional manifest step:

`Execution Package -> Execution Manifest -> Prompt Compiler -> CompiledPrompt -> Token Intelligence -> BudgetedPrompt -> Model Adapter -> Execution Prompt`

This avoids forcing prompt concerns into the package while preserving the package as the canonical context boundary for non-prompt consumers.
