# Execution Manifest

Execution Manifest is the immutable, model-independent engineering execution specification derived from one Execution Package.

It contains objective, business goal, acceptance criteria, repository context, relevant files, dependencies, implementation guidance, validation guidance, QA guidance, engineering standards, risks, warnings, confidence, token estimates, and source lineage.

It does not retrieve context, format prompts, choose providers, or call an LLM. Prompt Intelligence compiles the manifest into a provider-targeted Execution Prompt as a separate step. Existing APIs may continue to accept the compatibility consumer identifier `DeveloperPrompt` during migration.

See [Execution Manifest Foundation](../architecture/execution-manifest.md) for the contract, immutability rules, API, and compatibility boundary.
