"""Execution Runtime enumerations."""

SESSION_STATUSES = frozenset({
    "AwaitingResponse", "Interpreting", "PartialResponse", "Completed",
    "Failed", "TimedOut", "Cancelled",
})
TERMINAL_SESSION_STATUSES = frozenset({"Completed", "Failed", "TimedOut", "Cancelled"})
RECOVERABLE_SESSION_STATUSES = frozenset({"Failed", "TimedOut", "PartialResponse", "Cancelled"})
FAILURE_TYPES = frozenset({"ProviderFailure", "NetworkFailure", "RuntimeFailure", "Timeout"})
ARTIFACT_TYPES = frozenset({
    "Code", "Test", "Documentation", "Configuration", "Migration", "API",
    "Architecture", "Refactoring", "BugFix", "Unknown", "File", "Folder",
    "Class", "Interface", "Method", "DatabaseChange", "ConfigurationChange",
    "DocumentationChange", "Todo", "Fixme", "BreakingChange", "Warning",
    "Risk", "ArchitectureNote", "ImplementationNote",
})
RESPONSE_TYPES = frozenset({"StructuredJson", "ProviderEnvelope", "Markdown", "PlainText"})
