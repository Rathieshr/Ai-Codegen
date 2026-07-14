# Repository Intelligence Architecture

Repository Intelligence synchronizes repository evidence and publishes versioned snapshots.

`Registration -> Synchronization -> Snapshot -> Parse -> Engineering Graph -> File Ranking -> Context source`

Repository modes are `CodeIndexed`, `KnowledgeSnapshot`, and `Unavailable`. Only `CodeIndexed` permits direct file, API, symbol, and test evidence. Knowledge snapshots may expose modules, flows, standards, and architecture knowledge but never synthesize paths or symbols.

The implementation currently supports local/JSON persistence for foundation and test flows. Production-scale multi-writer persistence and remote synchronization workers remain deployment concerns.
