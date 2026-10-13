# HEI 3.4 Context Consumer Migration Report

The authoritative migration inventory is maintained in [platform-convergence.md](./platform-convergence.md#consumer-migration-inventory). Initial convergence covers Developer Prompt, Validation, QA, Engineering Memory Capture, Agent Runtime, and VS Code. Azure DevOps automation, Portal, and SDK are explicitly reserved as future package consumers.

Static architecture guards in `tests/test_platform_convergence.py` prevent the convergence package, Developer Prompt, and migrated QA entry point from importing Repository Intelligence, Engineering Memory retrieval, Project Intelligence, or Context Orchestration sources. Runtime tests verify consumer events, activity, diagnostics, and package-only projections.
