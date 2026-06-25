# CONTEXT_CAPSULE_SPEC.md

# HEI (Hubbell Engineering Intelligence)

## Context Capsule Specification

**Document Version:** 1.0

**Product Version:** HEI v1.0

**Status:** Draft

**Implementation Status:** Planned

**Owner:** AI Gen Platform Team

**Dependencies**

* AI_GEN_ARCHITECTURE.md
* PROJECT_INTELLIGENCE.md
* REPOSITORY_INTELLIGENCE.md
* KNOWLEDGE_REGISTRY.md

**Consumers**

* Planning Engine
* Execution Package Builder
* QA Engine
* Connector Framework
* AI Providers
* Future Agent Framework

---

# 1. Purpose

A Context Capsule is a lightweight, task-specific engineering context assembled from the Knowledge Registry.

It contains only the information required to perform a specific engineering activity.

Context Capsules eliminate redundant prompts, reduce AI token usage, improve consistency, and provide deterministic engineering context.

They are transient working objects and are not intended to replace the Knowledge Registry.

---

# 2. Objectives

Context Capsules should:

* Reduce AI token consumption.
* Eliminate duplicate context.
* Provide deterministic engineering context.
* Be reusable across AI providers.
* Support multiple engineering workflows.
* Be version-aware.
* Be generated on demand.

---

# 3. Guiding Principles

## Task Specific

Each capsule serves one engineering activity.

---

## Minimal Context

Include only relevant information.

---

## Knowledge Driven

Capsules are assembled from the Knowledge Registry.

---

## Immutable

Generated capsules should not be manually edited.

---

## Disposable

Capsules can be regenerated whenever project knowledge changes.

---

# 4. Context Capsule Lifecycle

```text
Knowledge Registry

↓

Request Context

↓

Context Selection

↓

Context Optimization

↓

Context Capsule

↓

Execution Package / AI Provider

↓

Discard
```

Context Capsules are generated when required.

---

# 5. Context Capsule Types

## Project Capsule

Contains

* Project Summary
* Technology Stack
* Applications
* Standards
* Architecture Summary

---

## Feature Capsule

Contains

* Parent Epic
* Feature Description
* Business Goals
* Modules
* Flows
* Dependencies

---

## Story Capsule

Contains

* Parent Feature
* Story
* Acceptance Criteria
* Relevant Modules
* Relevant Flows
* Architecture Rules
* Standards

---

## Task Capsule

Contains

* Parent Story
* Selected Task
* Relevant Files
* Dependencies
* Coding Standards
* Architecture Constraints

---

## Execution Capsule

Contains

* Story Capsule
* Task Capsule
* Relevant Repository Knowledge
* Ranked Files
* Execution Constraints

---

## QA Capsule

Contains

* Story
* Acceptance Criteria
* Test Scenarios
* Quality Rules
* Regression Scope

---

# 6. Capsule Structure

Each capsule contains

* Capsule ID
* Capsule Type
* Source Knowledge Version
* Generated Date
* Expiration
* Context Sections
* Confidence
* Token Estimate

---

# 7. Context Sections

Possible sections include

Project

Story

Task

Modules

Flows

Dependencies

Architecture Rules

Standards

Relevant Files

Known Risks

Acceptance Criteria

Repository Snapshot

Only relevant sections are included.

---

# 8. Context Optimization

Before a capsule is produced, HEI performs:

* Context Ranking
* Duplicate Removal
* Token Budgeting
* Working Set Selection
* Section Prioritization

The goal is to provide the smallest useful context.

---

# 9. Token Budgeting

Every capsule estimates token usage.

Example

Estimated Tokens

650

Target Model

GPT-5

Maximum Allowed

4000

If the estimated size exceeds the configured budget:

* Lower-priority sections are removed.
* Large summaries are compressed.
* Repository context is reduced to ranked artifacts.

---

# 10. Context Priorities

Highest Priority

* Current Task
* Story
* Acceptance Criteria

Medium Priority

* Modules
* Flows
* Dependencies

Lower Priority

* Repository Summary
* Related Features
* Historical Information

Lowest Priority

* Older Activity
* Diagnostics

Lower-priority sections are removed first.

---

# 11. Knowledge Version

Every capsule references the Knowledge Registry version.

Example

Knowledge Version

v14

Repository Snapshot

v8

If newer knowledge exists, the capsule is marked

Refresh Recommended.

---

# 12. Context Freshness

Capsules maintain freshness.

States

* Current
* Stale
* Refresh Recommended
* Outdated

Freshness is determined by comparing the capsule against the current Knowledge Registry version.

---

# 13. AI Provider Independence

Context Capsules are provider-independent.

The same capsule may be consumed by:

* OpenAI
* Azure OpenAI
* Local Models
* Future Enterprise Models

Only the final prompt assembly is model-specific.

---

# 14. Relationship to Execution Packages

Execution Packages are generated from Context Capsules.

Workflow

```text
Knowledge Registry

↓

Context Capsule

↓

Execution Package

↓

Developer Prompt

↓

AI Provider
```

Execution Packages should never bypass Context Capsules.

---

# 15. Context Refresh

Context Capsules are regenerated when:

* Repository Knowledge changes
* Story changes
* Acceptance Criteria changes
* Standards change
* Architecture changes

Capsules should not update automatically during active execution.

User approval is required.

---

# 16. Non-Goals

Context Capsules do not:

* Store permanent knowledge.
* Replace the Knowledge Registry.
* Generate code.
* Modify repositories.
* Execute prompts.
* Persist engineering decisions.

---

# 17. Future Enhancements

Planned capabilities

* Delta Capsules
* Conversation Capsules
* Multi-Agent Capsules
* User Preference Capsules
* Team Capsules
* Cross-Repository Capsules
* Automatic Capsule Refresh
* Capsule Caching
* Capsule Sharing

---

# 18. Success Metrics

Average Capsule Size

Token Reduction

Prompt Accuracy

Context Reuse Rate

Execution Success Rate

Capsule Generation Time

Knowledge Freshness

Provider Compatibility

---

# 19. Architecture Relationships

```text
Project Intelligence

↓

Repository Intelligence

↓

Knowledge Registry

↓

Context Capsule

↓

Execution Package

↓

Prompt Builder

↓

AI Provider
```

Context Capsules form the working context layer between engineering knowledge and AI execution.

---

# 20. Example

## Story Capsule

```
Capsule Type

Story

Story

Open Critical Fault Event Details

Acceptance Criteria

6

Relevant Modules

Fault Monitoring

Telemetry

Device Management

Relevant Flows

Fault Event Review

Device Health Review

Architecture Rules

MVVM

Repository Pattern

Role-Based Access

Relevant Files

FaultEventService.cs

FaultRepository.cs

EventDetailsViewModel.cs

Knowledge Version

v14

Estimated Tokens

780
```

This capsule becomes the input for the Execution Package Builder rather than querying the entire Knowledge Registry.

---

# Revision History

| Version | Date       | Author               | Description                           |
| ------- | ---------- | -------------------- | ------------------------------------- |
| 1.0     | 2026-06-25 | AI Gen Platform Team | Initial Context Capsule Specification |
