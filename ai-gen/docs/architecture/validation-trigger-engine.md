# Validation Trigger Engine

## Purpose

The Validation Trigger Engine determines whether Validation Intelligence should execute after an Engineering Diff is available. It is deterministic: it does not run validation, invoke a provider, inspect repository files, or reinterpret engineering artifacts.

## Inputs

- Engineering Diff
- Structured Execution Result
- Execution Manifest
- Optional manual override
- Optional trigger policy
- Existing Engineering Governance result

## Output

`ValidationTriggerDecision` contains:

- decision: `Required`, `Skipped`, or `Blocked`
- validation-required flag
- reason and confidence
- ordered rules used
- Engineering Diff, Execution Result, Execution Manifest, session, and correlation lineage
- manual override and policy evidence
- change summary and deterministic diagnostics

The persisted decision is immutable and reusable for identical inputs.

## Rule precedence

Rules execute in this order:

1. Governance or trigger-policy block.
2. Policy prohibition of manual skip.
3. Policy-required validation.
4. Manual override.
5. Failed, cancelled, or blocked Execution Result.
6. Critical or high Engineering Diff impact.
7. API, module, service, dependency, architecture, test, security, database, refactoring, breaking-change, or dependency-graph change.
8. Conditional configuration rule.
9. Documentation-only or comments-only skip.
10. No semantic change skip.
11. Conservative default validation.

Policy therefore cannot be bypassed by a manual override. A permitted manual override can supersede normal engineering rules and is retained with actor and reason.

## Configuration rule

Configuration-only changes require validation when:

- the affected configuration is security, authentication, authorization, credential, connection, database, permission, production, secret, or token related; or
- Execution Manifest validation guidance explicitly requires validation; or
- an active policy requires it.

Other configuration-only changes are skipped with lower confidence and a visible reason.

## Events

- `ValidationRequested`
- `ValidationSkipped`
- `ValidationBlocked`

`ValidationRequested` is a request event, not proof that Validation Intelligence ran. Event payloads explicitly record `invoked: false`.

## APIs

| Method | Route | Contract |
| --- | --- | --- |
| `POST` | `/validation-trigger/evaluate` | Evaluate and persist a Validation Trigger decision. |
| `GET` | `/validation-trigger/{id}` | Retrieve an immutable decision. |

## Pipeline position

```text
Engineering Diff
      +
Execution Result
      +
Execution Manifest
      |
Governance and Trigger Rules
      |
Validation Trigger Decision
      |
Requested | Skipped | Blocked
```
