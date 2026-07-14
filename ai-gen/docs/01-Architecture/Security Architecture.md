# Security Architecture

## Controls

- Azure DevOps groups map to HEI roles where available.
- Project and repository boundaries apply to context, memory, graph, and artifact retrieval.
- Secrets remain in environment or managed secret stores and are never written to diagnostics.
- Provider requests receive budgeted, purpose-specific context rather than unrestricted project data.
- Audit records capture actor, action, target, correlation ID, and before/after state where appropriate.
- Agents and skills enforce permissions and policy before execution.
- Error responses are bounded and do not expose raw stack traces or credentials.

Security-sensitive changes require an ADR and explicit validation coverage.
