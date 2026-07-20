"""Canonical models for meeting transcript intelligence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class TranscriptSourceType(str, Enum):
    TEAMS = "TeamsTranscript"
    ZOOM = "ZoomTranscript"
    TEXT = "TextTranscript"
    DOCX = "DOCX"
    TXT = "TXT"

    @classmethod
    def parse(cls, value: Any, *, file_name: str = "") -> "TranscriptSourceType":
        suffix = file_name.lower().rsplit(".", 1)[-1] if "." in file_name else ""
        if suffix == "docx":
            return cls.DOCX
        if suffix == "txt":
            return cls.TXT
        normalized = "".join(character for character in str(value or "") if character.isalnum()).lower()
        aliases = {
            "": cls.TEXT,
            "teams": cls.TEAMS,
            "teamstranscript": cls.TEAMS,
            "zoom": cls.ZOOM,
            "zoomtranscript": cls.ZOOM,
            "text": cls.TEXT,
            "texttranscript": cls.TEXT,
            "docx": cls.DOCX,
            "txt": cls.TXT,
        }
        if normalized not in aliases:
            raise ValueError("Unsupported transcript source. Use Teams, Zoom, text, DOCX, or TXT.")
        return aliases[normalized]


@dataclass(frozen=True)
class TranscriptFinding:
    finding_id: str
    text: str
    speaker: str = ""
    timestamp: str = ""
    confidence: float = 0.0
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _camel(asdict(self))


@dataclass(frozen=True)
class TranscriptAnalysis:
    meeting_title: str
    participants: list[str]
    meeting_date: str
    meeting_summary: str
    requirements: list[TranscriptFinding]
    action_items: list[TranscriptFinding]
    decisions: list[TranscriptFinding]
    risks: list[TranscriptFinding]
    open_questions: list[TranscriptFinding]
    dependencies: list[TranscriptFinding]
    ready_for_planning: bool
    ignored_lines: int
    duplicate_lines_removed: int
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "meetingTitle": self.meeting_title,
            "participants": list(self.participants),
            "date": self.meeting_date,
            "meetingSummary": self.meeting_summary,
            "requirements": [item.to_dict() for item in self.requirements],
            "actionItems": [item.to_dict() for item in self.action_items],
            "decisions": [item.to_dict() for item in self.decisions],
            "risks": [item.to_dict() for item in self.risks],
            "openQuestions": [item.to_dict() for item in self.open_questions],
            "dependencies": [item.to_dict() for item in self.dependencies],
            "readyForPlanning": self.ready_for_planning,
            "ignoredLines": self.ignored_lines,
            "duplicateLinesRemoved": self.duplicate_lines_removed,
            "warnings": list(self.warnings),
        }


def _camel(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key.split("_")[0] + "".join(part.capitalize() for part in key.split("_")[1:]): item
        for key, item in value.items()
    }
