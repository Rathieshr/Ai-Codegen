# Service Reference

All methods return `OperationResult<T>`, which contains the typed result and automatic request diagnostics. Methods accept an optional `RequestContext` for correlation and artifact lineage versions.

## Planning

- `analyzeRequirement`
- `createEpic`
- `createFeature`
- `createStory`
- `createTask`
- `estimateStory`
- `buildPlanningPackage`

## Repository

- `registerRepository`
- `listRepositories`
- `getRepository`
- `synchronize`
- `getSnapshot`
- `getEngineeringGraph`
- `searchFiles`
- `searchSymbols`
- `getRepositoryHealth`

## Context

- `buildContextCapsule`
- `getContextCapsule`
- `searchContext`
- `validateContext`

## Execution

- `buildExecutionPackage`
- `getExecutionPackage`
- `buildExecutionPlan`
- `getExecutionReadiness`

## Prompt

- `compilePrompt`
- `optimizePrompt`
- `estimateTokens`
- `generateExecutionPrompt`
- `selectProvider`
- `getModels`

## Runtime

- `startExecution`
- `submitResponse`
- `getExecutionStatus`
- `getExecutionTrace`
- `retryExecution`

## Validation

- `validateImplementation`
- `compareAcceptance`
- `architectureValidation`
- `regressionValidation`

## QA

- `generateTests`
- `generateRegression`
- `generateReleaseReadiness`

## Engineering Memory

- `searchMemory`
- `createCandidate`
- `approveMemory`
- `rejectMemory`
- `suggestReuse`

## Azure DevOps

- `analyzeWorkItem`
- `suggestStories`
- `analyzeSprint`
- `generatePRSummary`

## Platform

- `getHealth`
- `getRecentActivity`
- `getCapabilities`

## Lifecycle of one request

```text
Service Method
    -> Named Platform Operation
    -> Version-aware Cache Check
    -> Authentication Headers
    -> Correlation and SDK Metadata
    -> Retry Policy
    -> ITransport
    -> Typed Result or Typed Exception
    -> Diagnostics, Telemetry, and Events
```

HTTP methods and paths are intentionally absent from this reference.
