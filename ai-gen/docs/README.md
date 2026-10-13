# HEI Product Documentation

This directory is the canonical documentation home for the HEI Engineering Platform. Documentation follows the product lifecycle from vision through architecture, platform contracts, agents, integrations, testing, and operations.

Start with the [HEI Application Implementation, Scope, Architecture, and Roadmap](./HEI%20Application%20Implementation%20Architecture%20and%20Roadmap.md) for an end-to-end platform overview with visual architecture and lifecycle diagrams.

## Documentation map

| Area | Purpose |
| --- | --- |
| [00-Vision](./00-Vision/README.md) | Product direction, strategy, roadmap, and release intent |
| [01-Architecture](./01-Architecture/README.md) | Layered architecture, boundaries, contracts, events, agents, and security |
| [02-Product](./02-Product/README.md) | Epics, features, stories, journeys, personas, and requirements |
| [03-Platform](./03-Platform/README.md) | Foundation services and canonical engineering artifacts |
| [04-Agents](./04-Agents/README.md) | Agent Runtime and specialized agent responsibilities |
| [05-Repository Intelligence](./05-Repository%20Intelligence/README.md) | Repository synchronization, snapshots, graph, and evidence ranking |
| [06-Azure DevOps](./06-Azure%20DevOps/README.md) | Azure DevOps integration and automation contracts |
| [07-Portal](./07-Portal/README.md) | Engineering Command Center experience |
| [08-VSCode](./08-VSCode/README.md) | HEI Engineering Assistant and execution workspace |
| [09-Testing](./09-Testing/README.md) | Quality strategy, hardening, and regression suites |
| [10-Operations](./10-Operations/README.md) | Deployment, health, observability, and support |
| [ADR](./ADR/README.md) | Cross-cutting architecture decisions |

## Platform model

```text
Experience Layer
VS Code | Azure DevOps | Portal | SDK | APIs
                         |
Engineering Intelligence
Planning | Repository | Context | Execution | Prompt | Validation | QA | Memory
                         |
Agent Runtime
Planning | Repository | Execution | Validation | QA | Memory | Azure DevOps
                         |
Platform Foundation
Jobs | Events | Audit | Notifications | Activity | Health | Policies
                         |
Enterprise Systems
Azure DevOps | Git | Repositories | Knowledge Registry | AI Providers
```

## Documentation rules

- Use the canonical terms in [Terminology](./TERMINOLOGY.md).
- Mark compatibility names explicitly; do not silently mix old and new terminology.
- Repository Intelligence and the Knowledge Registry provide facts. Engineering Memory provides approved supporting evidence.
- Context Intelligence is the only context assembly authority.
- The Execution Package is the only downstream engineering execution contract.
- Agents orchestrate approved capabilities and never bypass policy or approval boundaries.

The earlier `architecture`, `specifications`, and `vision` folders remain as historical source documents during migration. New documents and links should target this structure.
