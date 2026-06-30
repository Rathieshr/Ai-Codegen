"""Provider response parse errors."""

from __future__ import annotations


class ProviderParseError(ValueError):
    """Raised when a provider response cannot be normalized into JSON."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        raw_preview: str = "",
        source_format: str = "unknown",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.raw_preview = raw_preview
        self.source_format = source_format
