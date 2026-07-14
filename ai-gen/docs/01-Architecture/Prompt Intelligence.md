# Prompt Intelligence Architecture

Prompt Intelligence starts from an immutable Execution Manifest.

`Execution Manifest -> Prompt Cache -> Prompt Compiler -> CompiledPrompt -> Token Intelligence -> BudgetedPrompt -> Model Adapter -> Execution Prompt -> Prompt Optimizer -> Optimized Execution Prompt -> Prompt Cache -> Prompt Diagnostics`

Provider Router is the deterministic entry point when a caller has not selected a model. It consumes the Execution Manifest plus routing signals, selects an eligible ModelProfile, and then runs the same Compiler, Token Intelligence, Adapter, and Optimizer stages. It records a decision but never invokes the selected provider.

Prompt Cache wraps Provider Router without creating another generation path. It reuses a routed prompt only when manifest identity, package version, repository snapshot, knowledge version, memory version, model, execution mode, and routing target all match. Changes to any dimension produce a miss and preserve the stale entry only for diagnostics.

Token Intelligence supports explicit budgets from 1,024 through 128,000 tokens. It preserves acceptance criteria, repository evidence, and validation guidance, and removes only complete lower-value JSON values. Provider-specific formatting and final transport safeguards remain downstream.

Prompt Compiler deterministically splits and deduplicates model-independent sections. It performs no token optimization or model adaptation. Token Intelligence creates the bounded artifact. Model Adapter then applies the selected ModelProfile, section ordering, model-oriented wording, system-prompt handling, and context validation to produce the ExecutionPrompt. Prompt Optimizer applies the requested engineering mode, merges repeated instructions, protects repository/implementation/acceptance content, moves secondary context to an appendix, and produces quality and confidence scores. Prompt Diagnostics records immutable lineage, model and size metadata, file inclusion decisions, warnings, and truthful operational estimates. The older Prompt Budget Manager remains only as a compatibility transport safeguard until legacy consumers migrate.

The current implementation retains the internal `DeveloperPrompt` compatibility consumer name. It follows the canonical pipeline and is not a second implementation path.

## Production Readiness

Milestone 4.10 adds a provider-free hardening harness around the complete deterministic pipeline. It validates repository evidence boundaries, every registered adapter, every token budget, cache reuse, routing decisions, diagnostics lineage, deterministic regression fingerprints, and local performance targets.

A constrained token budget is considered safe when it either produces a bounded prompt or returns a structured `Blocked` result with protected JSON intact. Production hardening never treats truncation, invented repository evidence, incomplete lineage, or silent routing fallback as success.

See [Prompt Intelligence Hardening](../testing/prompt-intelligence-hardening.md) and the generated [benchmark report](../testing/prompt-intelligence-benchmark.md).
