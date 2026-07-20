"""Deterministic requirement analysis before Planning Intelligence."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any
from uuid import uuid4

from .models import RequirementAnalysis, RequirementFinding


_HEADINGS = {
    "business goal": "business_goals", "business goals": "business_goals", "goal": "business_goals",
    "goals": "business_goals", "objective": "business_goals", "objectives": "business_goals",
    "functional requirement": "functional_requirements", "functional requirements": "functional_requirements",
    "requirements": "functional_requirements", "requirement": "functional_requirements",
    "non functional requirement": "non_functional_requirements", "non functional requirements": "non_functional_requirements",
    "non-functional requirements": "non_functional_requirements", "quality attributes": "non_functional_requirements",
    "acceptance criteria": "acceptance_criteria", "acceptance criterion": "acceptance_criteria",
    "actors": "actors", "personas": "actors", "users": "actors",
    "business rules": "business_rules", "rules": "business_rules",
    "constraints": "constraints", "dependencies": "dependencies", "risks": "risks",
    "open questions": "open_questions", "questions": "open_questions", "assumptions": "assumptions",
}
_NFR_TERMS = re.compile(r"\b(performance|latency|response time|availability|reliability|scalability|security|privacy|audit|accessibility|throughput|sla|milliseconds?|seconds?|concurrent|encryption)\b", re.I)
_AMBIGUOUS = re.compile(r"\b(appropriate|as needed|etc\.?|fast|easy|some|tbd|user[- ]friendly|various|quickly|robust|seamless|normal|sufficient|adequate)\b", re.I)
_FUNCTIONAL = re.compile(r"\b(must|shall|should|can|needs? to|allow|enable|display|show|create|update|view|search|filter|notify|calculate|validate|support|provide)\b", re.I)


class RequirementAnalysisEngine:
    """Extracts and validates engineering intent without an LLM."""

    def analyze(self, context: dict[str, Any]) -> RequirementAnalysis:
        title = _text(context.get("title"))
        content = _text(context.get("normalizedRequirement"))
        sections, sentences = _parse(content)
        values: dict[str, list[str]] = {name: [] for name in set(_HEADINGS.values())}
        for section, text in sections:
            target = _HEADINGS.get(section)
            if target:
                values[target].append(text)
                continue
            self._classify(text, values)

        if not values["functional_requirements"]:
            candidates = [item for item in sentences if item and not _is_heading(item)]
            if candidates:
                values["functional_requirements"].append(candidates[0])

        duplicate_candidates = values["functional_requirements"] + values["non_functional_requirements"] + values["acceptance_criteria"]
        for key in values:
            values[key] = _unique(values[key])

        actors = list(values["actors"])
        for sentence in sentences:
            match = re.search(r"\bas (?:an? )?([^,]+),\s*i\b", sentence, re.I)
            if match:
                actors.append(match.group(1).strip().title())
        values["actors"] = _unique(actors)

        analyzed_items = values["functional_requirements"] + values["non_functional_requirements"] + values["acceptance_criteria"]
        missing = self._missing_acceptance(values)
        ambiguous = self._ambiguities(analyzed_items)
        conflicts = self._conflicts(analyzed_items)
        duplicates = self._duplicates(duplicate_candidates)
        score = self._quality_score(title, values, ambiguous, conflicts, duplicates)
        readiness = self._readiness(values, score, missing, ambiguous, conflicts)
        confidence = self._confidence(values, content, ambiguous, conflicts)
        summary = self._summary(title, values)
        planning_requirement = self._planning_requirement(title, values, missing)
        counts = {key: len(item) for key, item in values.items()}
        metadata = context.get("metadata") if isinstance(context.get("metadata"), dict) else {}
        attributes = metadata.get("attributes") if isinstance(metadata.get("attributes"), dict) else {}
        documents = [item for item in context.get("documents") or [] if isinstance(item, dict)]
        repository_id = _text(metadata.get("repositoryId"))
        return RequirementAnalysis(
            analysis_id=f"requirement_analysis_{uuid4().hex}",
            requirement_id=_text(context.get("requirementId")),
            context_version=_text(context.get("contextVersion")) or "1.0",
            content_hash=_text(context.get("contentHash")),
            requirement_summary=summary,
            planning_requirement=planning_requirement,
            planning_readiness=readiness,
            requirement_quality_score=score,
            confidence=confidence,
            business_goals=values["business_goals"],
            functional_requirements=values["functional_requirements"],
            non_functional_requirements=values["non_functional_requirements"],
            acceptance_criteria=values["acceptance_criteria"],
            actors=values["actors"],
            business_rules=values["business_rules"],
            constraints=values["constraints"],
            dependencies=values["dependencies"],
            risks=values["risks"],
            open_questions=values["open_questions"],
            assumptions=values["assumptions"],
            missing_acceptance_criteria=missing,
            ambiguous_requirements=ambiguous,
            conflicting_requirements=conflicts,
            duplicate_requirements=duplicates,
            diagnostics={"engine": "DeterministicRequirementAnalysisV1", "sourceItemCount": len(sentences), "extractedCounts": counts},
            review_context={
                "source": _text(context.get("sourceType")) or "Unknown",
                "repository": {
                    "id": repository_id,
                    "name": _text(attributes.get("repositoryName")),
                    "status": "Selected" if repository_id else "Not Connected",
                },
                "documentType": _text(documents[0].get("documentType")) if documents else "Not Applicable",
                "engineeringMemory": {
                    "status": "Pending Planning Context",
                    "message": "Engineering Memory is resolved after this requirement is approved.",
                },
                "repositoryReuse": {
                    "status": "Pending Planning Context" if repository_id else "Repository Not Connected",
                    "message": "Repository reuse is calculated from ranked evidence during Planning.",
                },
            },
            analyzed_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _classify(text: str, values: dict[str, list[str]]) -> None:
        lowered = text.lower()
        if _NFR_TERMS.search(text):
            values["non_functional_requirements"].append(text)
        elif _FUNCTIONAL.search(text):
            values["functional_requirements"].append(text)
        if re.search(r"\b(goal|outcome|business value|so that)\b", lowered):
            values["business_goals"].append(text)
        if re.search(r"\b(only|must not|unless|policy|business rule)\b", lowered):
            values["business_rules"].append(text)
        if re.search(r"\b(constraint|cannot|limited to|at most|at least|maximum|minimum)\b", lowered):
            values["constraints"].append(text)
        if re.search(r"\b(depends on|dependent on|blocked by|requires? (?:the )?[\w -]+ (?:api|service|team|system))\b", lowered):
            values["dependencies"].append(text)
        if re.search(r"\b(risk|may fail|could fail|may delay|concern)\b", lowered):
            values["risks"].append(text)
        if "?" in text or re.search(r"\b(tbd|to be confirmed|need to confirm|open question)\b", lowered):
            values["open_questions"].append(text)
        if re.search(r"\b(assume|assumption|assuming|expected that)\b", lowered):
            values["assumptions"].append(text)

    @staticmethod
    def _missing_acceptance(values: dict[str, list[str]]) -> list[RequirementFinding]:
        if not values["acceptance_criteria"]:
            return [RequirementFinding("Acceptance criteria are missing.", "Planning needs testable completion conditions.", confidence=1.0)]
        findings = []
        for criterion in values["acceptance_criteria"]:
            if len(criterion.split()) < 4 or _AMBIGUOUS.search(criterion):
                findings.append(RequirementFinding(criterion, "Acceptance criterion is not sufficiently measurable or precise.", criterion, 0.9))
        return findings

    @staticmethod
    def _ambiguities(items: list[str]) -> list[RequirementFinding]:
        findings = []
        for item in items:
            terms = sorted({match.group(0) for match in _AMBIGUOUS.finditer(item)}, key=str.lower)
            if terms:
                findings.append(RequirementFinding(item, f"Ambiguous term(s): {', '.join(terms)}.", item, 0.95))
        return findings

    @staticmethod
    def _conflicts(items: list[str]) -> list[RequirementFinding]:
        findings: list[RequirementFinding] = []
        for index, left in enumerate(items):
            left_negative = bool(re.search(r"\b(must not|shall not|cannot|may not)\b", left, re.I))
            left_terms = _meaningful_terms(left)
            for right in items[index + 1:]:
                right_negative = bool(re.search(r"\b(must not|shall not|cannot|may not)\b", right, re.I))
                right_terms = _meaningful_terms(right)
                overlap = left_terms & right_terms
                semantic_overlap = len(overlap) / max(1, len(left_terms | right_terms))
                if left_negative != right_negative and len(overlap) >= 3 and semantic_overlap >= 0.75:
                    findings.append(RequirementFinding(f"{left} <> {right}", "Requirements make opposing statements about the same subject.", f"Shared terms: {', '.join(sorted(overlap))}", 0.9))
        return findings

    @staticmethod
    def _duplicates(items: list[str]) -> list[RequirementFinding]:
        findings: list[RequirementFinding] = []
        normalized: dict[str, str] = {}
        for index, item in enumerate(items):
            key = _normalize(item)
            if key in normalized:
                findings.append(RequirementFinding(item, "Exact duplicate requirement.", normalized[key], 1.0))
                continue
            normalized[key] = item
            for other in items[:index]:
                ratio = SequenceMatcher(None, key, _normalize(other)).ratio()
                if ratio >= 0.9:
                    findings.append(RequirementFinding(item, "Near-duplicate requirement.", other, round(ratio, 2)))
                    break
        return findings

    @staticmethod
    def _quality_score(title: str, values: dict[str, list[str]], ambiguities: list[Any], conflicts: list[Any], duplicates: list[Any]) -> int:
        score = 10 if title else 0
        score += 10 if values["business_goals"] else 0
        score += 20 if values["functional_requirements"] else 0
        score += 25 if values["acceptance_criteria"] else 0
        score += 10 if values["actors"] else 0
        score += 5 if values["non_functional_requirements"] else 0
        score += 5 if values["dependencies"] or values["constraints"] else 0
        score += 5 if not ambiguities else 0
        score += 5 if not conflicts else 0
        score += 5 if not duplicates else 0
        return max(0, min(100, score))

    @staticmethod
    def _readiness(values: dict[str, list[str]], score: int, missing: list[Any], ambiguities: list[Any], conflicts: list[Any]) -> dict[str, Any]:
        blockers = []
        warnings = []
        if not values["functional_requirements"]:
            blockers.append("No functional engineering intent was identified.")
        if conflicts:
            blockers.append("Conflicting requirements must be resolved before Planning.")
        if missing:
            warnings.append("Acceptance criteria need review.")
        if ambiguities:
            warnings.append("Ambiguous wording needs clarification.")
        status = "Blocked" if blockers else "Ready" if score >= 70 and not warnings else "NeedsReview"
        return {"status": status, "readyForPlanning": status == "Ready", "score": score, "blockers": blockers, "warnings": warnings}

    @staticmethod
    def _confidence(values: dict[str, list[str]], content: str, ambiguities: list[Any], conflicts: list[Any]) -> float:
        coverage = sum(bool(values[key]) for key in ("business_goals", "functional_requirements", "acceptance_criteria", "actors", "non_functional_requirements"))
        confidence = 0.45 + coverage * 0.09 + min(len(content) / 5000, 0.08) - len(ambiguities) * 0.03 - len(conflicts) * 0.08
        return round(max(0.25, min(0.98, confidence)), 2)

    @staticmethod
    def _summary(title: str, values: dict[str, list[str]]) -> str:
        goal = (values["business_goals"] or values["functional_requirements"] or ["Engineering intent requires clarification."])[0]
        return f"{title}: {goal}" if title and title.lower() not in goal.lower() else goal

    @staticmethod
    def _planning_requirement(title: str, values: dict[str, list[str]], missing: list[RequirementFinding]) -> str:
        sections: list[tuple[str, list[str]]] = [
            ("Business Goals", values["business_goals"]),
            ("Functional Requirements", values["functional_requirements"]),
            ("Non-Functional Requirements", values["non_functional_requirements"]),
            ("Acceptance Criteria", values["acceptance_criteria"]), ("Actors", values["actors"]),
            ("Business Rules", values["business_rules"]), ("Constraints", values["constraints"]),
            ("Dependencies", values["dependencies"]), ("Risks", values["risks"]),
            ("Open Questions", values["open_questions"]), ("Assumptions", values["assumptions"]),
        ]
        output = [f"Title: {title}"]
        for heading, items in sections:
            if items:
                output.extend([f"\n{heading}:", *(f"- {item}" for item in _unique(items))])
        if missing:
            output.extend(["\nPlanning Gaps:", *(f"- {item.text}" for item in missing)])
        return "\n".join(output).strip()


def _parse(content: str) -> tuple[list[tuple[str, str]], list[str]]:
    current = ""
    items: list[tuple[str, str]] = []
    sentences: list[str] = []
    for raw in content.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", raw).strip()
        if not line:
            continue
        inline = re.match(r"^([^:]{2,40}):\s+(.+)$", line)
        if inline and _heading(inline.group(1)):
            current = _heading(inline.group(1))
            line = inline.group(2).strip()
        heading = _heading(line)
        if heading:
            current = heading
            continue
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", line):
            sentence = sentence.strip()
            if sentence:
                items.append((current, sentence))
                sentences.append(sentence)
    return items, sentences


def _heading(value: str) -> str:
    cleaned = re.sub(r"^#{1,6}\s*", "", value).strip().rstrip(":").strip().lower()
    return cleaned if cleaned in _HEADINGS else ""


def _is_heading(value: str) -> bool:
    return bool(_heading(value))


def _unique(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = _normalize(item)
        if key and key not in seen:
            seen.add(key)
            result.append(item.strip())
    return result


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _meaningful_terms(value: str) -> set[str]:
    stop = {"the", "a", "an", "and", "or", "to", "of", "for", "is", "are", "must", "shall", "not", "can", "cannot", "user", "users"}
    return {term for term in _normalize(value).split() if len(term) > 2 and term not in stop}


def _text(value: Any) -> str:
    return str(value or "").strip()
