from __future__ import annotations


class CapabilityDiagnostics:
    def __init__(self) -> None:
        self.reasoning: list[str] = []

    def add(self, message: str) -> None:
        if message and message not in self.reasoning:
            self.reasoning.append(message)

