# Agent Architecture

Agents are lightweight orchestrators over registered engineering capabilities.

`Event -> Agent Runtime -> Policy check -> Skill/service execution -> Artifact -> Approval checkpoint`

## Rules

- One primary responsibility per agent.
- Agents receive versioned workflow context and canonical artifacts.
- Agents may prepare, retry, notify, and recommend.
- Agents may not approve work, merge pull requests, modify repositories directly, or override governance.
- Failures produce traceable events and resumable workflow state.

Agent responsibilities are documented in [04-Agents](../04-Agents/README.md).
