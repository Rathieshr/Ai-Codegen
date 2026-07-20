"""Deterministic extraction of engineering findings from meeting transcripts."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable

from .models import TranscriptAnalysis, TranscriptFinding


NOISE_PATTERNS = (
    r"^(?:meeting\s+)?title\s*:.+$",
    r"^(?:meeting\s+)?date\s*:.+$",
    r"^participants?\s*:.+$",
    r"^(?:hi|hello|hey|good (?:morning|afternoon|evening))(?:\s+(?:all|everyone|team))?[.! ]*$",
    r"^(?:thanks|thank you)(?:\s+(?:all|everyone|team))?[.! ]*$",
    r"^(?:can you hear me|you are on mute|let'?s get started|shall we start)[?!. ]*$",
    r"^\[(?:music|noise|inaudible|silence|applause)\]$",
    r"^(?:um+|uh+|okay|ok|right|yeah|yes|no)[.! ]*$",
)

RULES = {
    "decisions": (r"\b(?:we (?:decided|agreed|approved|chose|selected)|decision(?: is)?|approved|will proceed|agreed action|selected approach|confirmed that)\b",),
    "requirements": (r"\b(?:must|shall|needs? to|require[sd]?|requirement|should (?:allow|support|provide|display|prevent|validate|notify|capture|show|include)|user(?:s)? (?:can|must|should))\b",),
    "action_items": (r"\b(?:action item|to[- ]?do|follow up|will (?:create|update|investigate|confirm|document|send|review|implement)|assigned to|owner(?: is)?)\b",),
    "risks": (r"\b(?:risk|concern|blocker|may fail|might fail|could delay|security issue|performance issue)\b",),
    "open_questions": (r"\?$", r"\b(?:open question|need to confirm|needs clarification|unclear|to be decided|tbd)\b"),
    "dependencies": (r"\b(?:depends? on|dependency|requires? (?:the )?(?:[a-z0-9_-]+\s+){0,3}(?:api|service|team|approval|data|module)|waiting on|blocked by|prerequisite)\b",),
}


@dataclass(frozen=True)
class Utterance:
    text: str
    speaker: str = ""
    timestamp: str = ""


class TranscriptAnalyzer:
    def analyze(self, text: str, *, title: str = "", meeting_date: str = "") -> TranscriptAnalysis:
        utterances = _utterances(text)
        participants = _participants(utterances, text)
        inferred_date = meeting_date.strip() or _extract_date(text)
        inferred_title = title.strip() or _extract_title(text) or "Engineering Meeting"

        ignored = 0
        duplicates = 0
        seen: set[str] = set()
        findings: dict[str, list[TranscriptFinding]] = {name: [] for name in RULES}
        useful: list[Utterance] = []
        for utterance in utterances:
            if _is_noise(utterance.text):
                ignored += 1
                continue
            normalized = _dedupe_key(utterance.text)
            if not normalized:
                ignored += 1
                continue
            if normalized in seen:
                duplicates += 1
                continue
            seen.add(normalized)
            useful.append(utterance)
            for category, patterns in RULES.items():
                if any(re.search(pattern, utterance.text, flags=re.IGNORECASE) for pattern in patterns):
                    findings[category].append(_finding(category, utterance))

        requirements = findings["requirements"]
        decisions = findings["decisions"]
        warnings: list[str] = []
        if not requirements:
            warnings.append("No explicit engineering requirements were found. Review the transcript before Planning.")
        summary = _summary(inferred_title, requirements, decisions, findings["action_items"], useful)
        return TranscriptAnalysis(
            meeting_title=inferred_title,
            participants=participants,
            meeting_date=inferred_date,
            meeting_summary=summary,
            requirements=requirements,
            action_items=findings["action_items"],
            decisions=decisions,
            risks=findings["risks"],
            open_questions=findings["open_questions"],
            dependencies=findings["dependencies"],
            ready_for_planning=bool(requirements),
            ignored_lines=ignored,
            duplicate_lines_removed=duplicates,
            warnings=warnings,
        )


def _utterances(text: str) -> list[Utterance]:
    cleaned = re.sub(r"<v\s+([^>]+)>(.*?)</v>", r"\1: \2", str(text or ""), flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    result: list[Utterance] = []
    pending_timestamp = ""
    pending_speaker = ""
    for raw in cleaned.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line or line.upper() == "WEBVTT" or "-->" in line:
            if "-->" in line:
                pending_timestamp = line.split("-->", 1)[0].strip()
            continue
        line = re.sub(r"^From\s+(.+?)\s+to\s+(?:Everyone|All):\s*", r"\1: ", line, flags=re.IGNORECASE)
        speaker_header = re.match(r"^(?P<speaker>[A-Za-z][A-Za-z0-9 ._'-]{0,60})\s+(?P<timestamp>\d{1,2}:\d{2}(?::\d{2})?)$", line)
        if speaker_header:
            pending_speaker = speaker_header.group("speaker").strip()
            pending_timestamp = speaker_header.group("timestamp")
            continue
        match = re.match(r"^(?:\[(?P<t1>\d{1,2}:\d{2}(?::\d{2})?)\]|(?P<t2>\d{1,2}:\d{2}(?::\d{2})?))?\s*(?P<speaker>[A-Za-z][A-Za-z0-9 ._'-]{0,60}):\s*(?P<text>.+)$", line)
        if match:
            result.append(Utterance(match.group("text").strip(), match.group("speaker").strip(), match.group("t1") or match.group("t2") or pending_timestamp))
            pending_timestamp = ""
            pending_speaker = ""
        else:
            result.append(Utterance(line, speaker=pending_speaker, timestamp=pending_timestamp))
            pending_timestamp = ""
            pending_speaker = ""
    return result


def _participants(utterances: Iterable[Utterance], text: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    declared = re.search(r"^participants?\s*:\s*(.+)$", text, flags=re.IGNORECASE | re.MULTILINE)
    if declared:
        for name in re.split(r"[,;]|s+and\s+", declared.group(1), flags=re.IGNORECASE):
            value = name.strip()
            if value and value.casefold() not in seen:
                seen.add(value.casefold())
                values.append(value)
    for item in utterances:
        key = item.speaker.casefold()
        if item.speaker and key not in {"title", "meeting title", "date", "meeting date", "participant", "participants"} and key not in seen:
            seen.add(key)
            values.append(item.speaker)
    return values


def _is_noise(text: str) -> bool:
    return any(re.match(pattern, text.strip(), flags=re.IGNORECASE) for pattern in NOISE_PATTERNS)


def _dedupe_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _finding(category: str, utterance: Utterance) -> TranscriptFinding:
    evidence = " · ".join(value for value in [utterance.speaker, utterance.timestamp] if value) or "Transcript statement"
    digest = hashlib.sha256(f"{category}|{_dedupe_key(utterance.text)}".encode("utf-8")).hexdigest()[:12]
    return TranscriptFinding(
        finding_id=f"{category.rstrip('s')}_{digest}",
        text=utterance.text,
        speaker=utterance.speaker,
        timestamp=utterance.timestamp,
        confidence=0.9 if utterance.speaker else 0.82,
        evidence=evidence,
    )


def _extract_title(text: str) -> str:
    match = re.search(r"^(?:meeting\s+)?title\s*:\s*(.+)$", text, flags=re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else ""


def _extract_date(text: str) -> str:
    match = re.search(r"\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]20\d{2})\b", text)
    if match:
        return match.group(1)
    named = re.search(r"\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+20\d{2})\b", text, flags=re.IGNORECASE)
    return named.group(1) if named else ""


def _summary(title: str, requirements: list[TranscriptFinding], decisions: list[TranscriptFinding], actions: list[TranscriptFinding], useful: list[Utterance]) -> str:
    if requirements or decisions:
        parts = [f"{title} captured {len(requirements)} engineering requirement{'s' if len(requirements) != 1 else ''}"]
        if decisions:
            parts.append(f"{len(decisions)} business decision{'s' if len(decisions) != 1 else ''}")
        if actions:
            parts.append(f"{len(actions)} action item{'s' if len(actions) != 1 else ''}")
        return ", ".join(parts) + "."
    if useful:
        return f"{title} was analyzed, but no explicit engineering requirement was identified."
    return f"{title} did not contain analyzable engineering discussion."
