# QA Trigger Engine

## Purpose

The QA Trigger Engine determines the verification activities required after Implementation Validation. It consumes an Engineering Diff, Validation Result, and immutable Execution Manifest, then produces a deterministic `QAExecutionPlan`.

The engine plans QA work only. It does not generate tests, invoke QA Intelligence, call an AI provider, inspect repository files, or modify an Execution Manifest.

## Inputs

- Engineering Diff
- Validation Result
- Execution Manifest

## Output

`QAExecutionPlan` contains:

- decision: `Requested` or `Skipped`
- required flags for unit, integration, regression, permission, performance, security, smoke, and UI tests
- ordered required activities with priority, reason, and evidence
- rules used and confidence
- Engineering Diff, Validation Result, Execution Manifest, session, and correlation lineage
- change and validation summaries
- diagnostics proving that QA and providers were not invoked

Plans are immutable and reusable for identical inputs.

## Activity rules

| Change evidence | Required QA activities |
| --- | --- |
| API | Unit, integration, regression, permission, smoke |
| Database | Integration, regression, performance, smoke |
| UI | Unit, UI, regression, smoke |
| Configuration | Smoke and regression; permission and security when access-sensitive |
| Architecture | Integration, regression, performance, smoke |
| Security | Security, permission, regression |
| Module, service, refactoring | Unit, integration, regression |
| Dependency or graph | Integration, regression, smoke |
| Test | Regression |
| Breaking change | Unit, integration, regression, smoke |

Validation violations and recommendations can add targeted permission, security, or performance coverage. A failed, blocked, rejected, or cancelled Validation Result skips QA until validation is resolved. Documentation-only, comments-only, and no-change results are also skipped.

UI detection uses explicit UI change metadata, recognized UI file extensions, or focused UI evidence. Broad words such as `view` and `page` are not sufficient because they create false positives in documentation and domain names.

## Events

- `QARequested`
- `QASkipped`

`QARequested` means QA work has been planned. It does not mean tests were generated or QA Intelligence ran. Event payloads explicitly record `invoked: false`.

## APIs

| Method | Route | Contract |
| --- | --- | --- |
| `POST` | `/qa-trigger/evaluate` | Evaluate and persist a QA Execution Plan. |
| `GET` | `/qa-trigger/{id}` | Retrieve an immutable QA Execution Plan. |

## Pipeline position

```text
Engineering Diff
      +
Validation Result
      +
Execution Manifest
      |
QA Trigger Rules
      |
QAExecutionPlan
      |
QARequested | QASkipped
```
