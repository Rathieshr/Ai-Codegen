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
    "goals": "business_goals", "business value": "business_goals", "objective": "business_goals",
    "objectives": "business_goals",
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
_CONTEXT_HEADINGS = {
    "requirement summary": "__classify__",
    "description": "__classify__",
    "expected features": "__ignore__",
    "planning recommendations": "__ignore__",
    "missing information": "__ignore__",
    "area and iteration": "__ignore__",
    "source metadata": "__ignore__",
}
_INLINE_HEADING = re.compile(
    r"(?i)(?<![\w-])(" + "|".join(
        re.escape(value) for value in sorted(_HEADINGS, key=len, reverse=True)
    ) + r")\s*:\s*"
)
_NFR_TERMS = re.compile(r"\b(performance|latency|response time|availability|reliability|scalability|security|privacy|audit|accessibility|throughput|sla|milliseconds?|seconds?|concurrent|encryption)\b", re.I)
_AMBIGUOUS = re.compile(r"\b(appropriate|as needed|etc\.?|fast|easy|some|tbd|user[- ]friendly|various|quickly|robust|seamless|normal|sufficient|adequate)\b", re.I)
_FUNCTIONAL = re.compile(r"\b(must|shall|should|can|needs? to|allow|enable|display|show|create|update|view|search|filter|notify|calculate|validate|support|provide)\b", re.I)
_BUSINESS_OUTCOME = re.compile(r"\b(reduce|increase|improve|minimi[sz]e|maximi[sz]e|accelerate|prevent|avoid)\b", re.I)
_REQUIREMENT_NOISE = {
    "requirement summary",
    "planning recommendations",
    "description",
    "expected features",
    "area and iteration",
    "no acceptance criteria were provided in the source requirement",
    "acceptance criteria require definition",
}


class RequirementAnalysisEngine:
    """Extracts and validates engineering intent without an LLM."""

    def analyze(self, context: dict[str, Any]) -> RequirementAnalysis:
        title = _text(context.get("title"))
        content = _text(context.get("normalizedRequirement"))
        sections, sentences = _parse(content)
        values: dict[str, list[str]] = {name: [] for name in set(_HEADINGS.values())}
        for section, text in sections:
            if section == "__ignore__" or _is_requirement_noise(text):
                continue
            target = _HEADINGS.get(section)
            if target:
                values[target].append(text)
                continue
            self._classify(text, values)

        if _text(context.get("sourceType")) == "AzureDevOpsWorkItem":
            values["business_goals"] = [
                item for item in values["business_goals"]
                if _is_imported_business_goal(item)
            ]
            values["functional_requirements"] = [
                item for item in values["functional_requirements"]
                if _is_imported_functional_requirement(item)
            ]

        # ADO descriptions often express the observable behavior under Business
        # Goals instead of a Functional Requirements section. Preserve lineage
        # by promoting that exact source sentence rather than inventing a new one.
        if not values["functional_requirements"]:
            values["functional_requirements"].extend(
                item for item in values["business_goals"] if _FUNCTIONAL.search(item)
            )

        if not values["functional_requirements"]:
            candidates = [
                item for item in sentences
                if item and not _is_heading(item) and not _is_requirement_noise(item)
            ]
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
            enabled_actor = re.search(
                r"\b(?:allow|enable)\s+([A-Z][A-Za-z -]+?)\s+to\s+"
                r"(?:view|show|display|search|filter|create|update|manage|monitor|review|access)\b",
                sentence,
                re.I,
            )
            if enabled_actor:
                actors.append(enabled_actor.group(1).strip().title())
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
        source_origin = "Imported" if _text(context.get("sourceType")) == "AzureDevOpsWorkItem" else "Source"
        field_origins = {
            key: source_origin
            for key in (
                "businessGoals", "functionalRequirements", "nonFunctionalRequirements",
                "acceptanceCriteria", "risks", "dependencies", "businessRules",
                "actors", "openQuestions", "constraints", "assumptions",
            )
            if values[_camel_to_snake(key)]
        }
        acceptance_state = {
            "state": "SourceProvided" if values["acceptance_criteria"] else "Missing",
            "origin": source_origin if values["acceptance_criteria"] else "",
            "status": "Approved" if values["acceptance_criteria"] else "Missing",
            "description": (
                "Acceptance Criteria were found in the source requirement."
                if values["acceptance_criteria"]
                else "No Acceptance Criteria were provided in the source requirement."
            ),
        }
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
            acceptance_criteria_state=acceptance_state,
            field_origins=field_origins,
            missing_acceptance_criteria=missing,
            ambiguous_requirements=ambiguous,
            conflicting_requirements=conflicts,
            duplicate_requirements=duplicates,
            diagnostics={"engine": "DeterministicRequirementAnalysisV2", "sourceItemCount": len(sentences), "extractedCounts": counts},
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
            return [RequirementFinding(
                "No Acceptance Criteria were provided in the source requirement.",
                "Generate AI Suggested Acceptance Criteria or continue with reduced testability.",
                evidence="Source requirement contains no Acceptance Criteria section.",
                confidence=1.0,
            )]
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
        # Completeness is weighted by planning impact. Missing Acceptance Criteria
        # lowers testability, but is not treated as an intelligence failure.
        score = 5 if title else 0
        score += 20 if values["business_goals"] else 0
        score += 25 if values["functional_requirements"] else 0
        score += 15 if values["acceptance_criteria"] else 0
        score += 5 if values["actors"] else 0
        score += 8 if values["non_functional_requirements"] else 0
        score += 4 if values["dependencies"] else 0
        score += 3 if values["risks"] else 0
        score += 3 if values["business_rules"] else 0
        score += 2 if values["constraints"] else 0
        score += 4 if not ambiguities else 0
        score += 4 if not conflicts else 0
        score += 2 if not duplicates else 0
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
            warnings.append("Acceptance Criteria were not provided by the source. HEI can generate suggestions for review.")
        if ambiguities:
            warnings.append("Ambiguous wording needs clarification.")
        if blockers:
            status = "Blocked"
        elif ambiguities or not values["business_goals"]:
            status = "NeedsUserInput"
        elif warnings:
            status = "ReadyWithRecommendations"
        else:
            status = "Ready"
        return {
            "status": status,
            "readyForPlanning": status in {"Ready", "ReadyWithRecommendations"},
            "score": score,
            "blockers": blockers,
            "warnings": warnings,
        }

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
            output.extend(["\nPlanning Recommendations:", *(f"- {item.text}" for item in missing)])
        return "\n".join(output).strip()


def _camel_to_snake(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def _parse(content: str) -> tuple[list[tuple[str, str]], list[str]]:
    current = ""
    items: list[tuple[str, str]] = []
    sentences: list[str] = []
    for raw in content.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", raw).strip()
        if not line:
            continue
        inline_sections = _inline_sections(line)
        if inline_sections:
            for section, text in inline_sections:
                current = section
                if text:
                    _append_sentences(items, sentences, current, text)
            continue
        heading = _section_heading(line)
        if heading is not None:
            current = heading
            continue
        _append_sentences(items, sentences, current, line)
    return items, sentences


def _inline_sections(line: str) -> list[tuple[str, str]]:
    """Split one line containing one or more recognized ``Heading: value`` pairs."""
    matches = list(_INLINE_HEADING.finditer(line))
    if not matches:
        return []
    prefix = line[:matches[0].start()].strip()
    if prefix:
        return []
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
        sections.append((_heading(match.group(1)), line[match.end():end].strip(" -\t")))
    return sections


def _append_sentences(
    items: list[tuple[str, str]], sentences: list[str], section: str, text: str,
) -> None:
    for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", text):
        sentence = sentence.strip()
        if sentence:
            items.append((section, sentence))
            sentences.append(sentence)


def _heading(value: str) -> str:
    cleaned = re.sub(r"^#{1,6}\s*", "", value).strip().rstrip(":").strip().lower()
    return cleaned if cleaned in _HEADINGS else ""


def _section_heading(value: str) -> str | None:
    cleaned = re.sub(r"^#{1,6}\s*", "", value).strip().rstrip(":").strip().lower()
    if cleaned in _HEADINGS:
        return cleaned
    return _CONTEXT_HEADINGS.get(cleaned)


def _is_heading(value: str) -> bool:
    return _section_heading(value) is not None


def _is_requirement_noise(value: str) -> bool:
    normalized = _normalize(value)
    if normalized in _REQUIREMENT_NOISE:
        return True
    return bool(re.match(
        r"^(?:area|iteration|state|assigned to|work item type|tags?|revision)\s*:",
        value.strip(),
        re.I,
    ))


def _is_imported_business_goal(value: str) -> bool:
    if _is_requirement_noise(value):
        return False
    words = _normalize(value).split()
    return bool(_FUNCTIONAL.search(value) or _BUSINESS_OUTCOME.search(value) or len(words) >= 6)


def _is_imported_functional_requirement(value: str) -> bool:
    if _is_requirement_noise(value):
        return False
    return bool(_FUNCTIONAL.search(value))


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
