"""Evidence-driven Acceptance Criteria intelligence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any
from uuid import uuid4


_ACTION_PATTERN = re.compile(
    r"\b(view|show|display|search|filter|create|update|delete|submit|review|"
    r"approve|reject|notify|calculate|export|import|open|select|identify|"
    r"detect|monitor|receive|access|manage|configure|generate|compare|load|respond)\b",
    re.I,
)
_TRIGGER_PATTERN = re.compile(r"\b(when|after|before|upon|once|if)\b", re.I)
_GENERIC_RULES = {
    "authorization": re.compile(r"\b(authoriz(?:e|ed|ation)|permission|access restriction|restricted access)\b", re.I),
    "authentication": re.compile(r"\b(authenticat(?:e|ed|ion)|login|sign[ -]?in|identity)\b", re.I),
    "validation": re.compile(r"\b(validat(?:e|ion)|invalid|required input|mandatory field)\b", re.I),
    "role management": re.compile(r"\b(role management|assign role|manage roles?)\b", re.I),
    "crud": re.compile(r"\b(create|read|update|delete|crud)\b", re.I),
    "audit trail": re.compile(r"\b(audit|traceab(?:le|ility)|recorded action)\b", re.I),
    "session management": re.compile(r"\b(session|token refresh|session expiry)\b", re.I),
    "error messages": re.compile(r"\b(error message|failure message|validation message)\b", re.I),
}

ACCEPTANCE_CRITERIA_PROMPT_RULES = (
    "Act as an experienced Product Owner and Business Analyst. Derive Acceptance Criteria "
    "only from supplied evidence. Never invent functionality or generic enterprise scenarios. "
    "Do not assume authentication, authorization, validation, CRUD, audit, permissions, session "
    "management, or error handling unless explicitly supported. Attach evidence to every "
    "criterion. Represent unavailable evidence as Missing Information and low-confidence "
    "inference as an AI Assumption. Generate only specific, business-observable, "
    "implementation-independent behavior."
)


@dataclass(frozen=True)
class RequirementEvidence:
    requirement_sentence: str
    matched_phrase: str
    confidence: float
    source: str = "Requirement"

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        return {
            "requirementSentence": value["requirement_sentence"],
            "matchedPhrase": value["matched_phrase"],
            "confidence": round(value["confidence"], 2),
            "source": value["source"],
        }


@dataclass(frozen=True)
class RequirementFacts:
    business_goal: list[str] = field(default_factory=list)
    functional_goal: list[str] = field(default_factory=list)
    actor: list[str] = field(default_factory=list)
    primary_capability: str = ""
    entities: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    business_rules: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        return {
            key.split("_")[0] + "".join(part.capitalize() for part in key.split("_")[1:]): item
            for key, item in value.items()
        }


class IntelligentAcceptanceCriteriaEngine:
    """Builds traceable criteria without inventing unsupported enterprise behavior."""

    def understand(
        self,
        analysis: dict[str, Any],
        requirement: dict[str, Any],
    ) -> dict[str, Any]:
        facts = self._facts(analysis)
        source_criteria = [
            self._criterion(
                text=str(text),
                origin="Imported" if requirement.get("sourceType") == "AzureDevOpsWorkItem" else "Source Derived",
                status="Approved",
                functional=self._best_functional_match(str(text), facts.functional_goal),
                evidence=self._source_evidence(str(text), requirement),
                order=index + 1,
            )
            for index, text in enumerate(analysis.get("acceptanceCriteria") or [])
            if str(text).strip()
        ]
        missing = self._missing_information(
            facts,
            bool(source_criteria),
            bool(analysis.get("nonFunctionalRequirements")),
        )
        coverage = self.validate_coverage(facts.functional_goal, source_criteria, analysis)
        return {
            "requirementFacts": facts.to_dict(),
            "acceptanceCriteriaRecords": source_criteria,
            "missingInformation": missing,
            "aiAssumptions": self._assumptions(facts),
            "acceptanceCoverage": coverage,
            "acceptanceEvidence": [
                evidence
                for criterion in source_criteria
                for evidence in criterion.get("evidence") or []
            ],
            "acceptanceDiagnostics": {
                "engine": "IntelligentAcceptanceCriteriaV1",
                "genericTemplateGuard": "Enabled",
                "promptRulesVersion": "EvidenceOnlyV1",
                "functionalRequirementCount": len(facts.functional_goal),
                "sourceCriterionCount": len(source_criteria),
            },
        }

    def generate(
        self,
        analysis: dict[str, Any],
        requirement: dict[str, Any],
    ) -> list[dict[str, Any]]:
        facts = self._facts(analysis)
        evidence_corpus = self._evidence_corpus(analysis, requirement)
        suggestions: list[dict[str, Any]] = []
        candidates = [
            (functional, "Functional", functional)
            for functional in facts.functional_goal
        ]
        candidates.extend(
            (rule, "Business Rule", self._best_functional_match(rule, facts.functional_goal))
            for rule in facts.business_rules
        )
        candidates.extend(
            (quality, "Non-Functional", self._best_functional_match(quality, facts.functional_goal))
            for quality in analysis.get("nonFunctionalRequirements") or []
            if re.search(r"\b\d+(?:\.\d+)?\s*(?:ms|milliseconds?|seconds?|minutes?|%|percent)\b", str(quality), re.I)
        )
        for statement, criterion_type, functional in candidates:
            action = self._action(statement)
            if not action:
                continue
            generic_category = self._unsupported_generic_category(statement, evidence_corpus)
            if generic_category:
                continue
            actor = self._matching_actor(statement, facts.actor)
            matched_phrase = self._matched_phrase(statement, action)
            outcome = self._observable_outcome(statement, action)
            if criterion_type == "Business Rule" and re.search(r"\bonly authorized\b", statement, re.I):
                target = re.sub(rf"^{re.escape(action)}\s+", "", matched_phrase, flags=re.I)
                text = (
                    f"Scenario: {self._title(statement)}\n"
                    "Given a user is not authorized by the stated business rule\n"
                    f"When the user attempts to {action} {target}\n"
                    f"Then {target} is not available to that user."
                )
            elif criterion_type == "Non-Functional":
                limit = re.search(
                    r"\bwithin\s+\d+(?:\.\d+)?\s*(?:ms|milliseconds?|seconds?|minutes?)\b",
                    statement,
                    re.I,
                )
                text = (
                    f"Scenario: {self._title(statement)}\n"
                    "Given the stated operating conditions\n"
                    f"When {matched_phrase}\n"
                    f"Then the outcome completes {limit.group(0) if limit else 'within the stated limit'}."
                )
            else:
                given = (
                    f"Given {actor}" if actor
                    else f"Given the stated {criterion_type.lower()} context"
                )
                text = f"Scenario: {self._title(statement)}\n{given}\nWhen {matched_phrase}\nThen {outcome}."
            suggestions.append(self._criterion(
                text=text,
                origin="AI Inferred",
                status="PendingReview",
                functional=functional,
                evidence=[RequirementEvidence(
                    requirement_sentence=statement,
                    matched_phrase=matched_phrase,
                    confidence=0.93,
                ).to_dict()],
                order=len(suggestions) + 1,
                criterion_type=criterion_type,
            ))
        return suggestions

    def validate_coverage(
        self,
        functional_requirements: list[str],
        criteria: list[dict[str, Any]],
        analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        mappings = []
        covered = 0
        for index, requirement in enumerate(functional_requirements):
            matches = [
                str(item.get("criterionId") or "")
                for item in criteria
                if self._same_requirement(requirement, str(item.get("mappedFunctionalRequirement") or ""))
            ]
            status = "Covered" if matches else "Uncovered"
            covered += int(bool(matches))
            mappings.append({
                "functionalRequirementId": f"fr_{index + 1}",
                "functionalRequirement": requirement,
                "criterionIds": matches,
                "status": status,
            })
        total = len(functional_requirements)
        analysis = analysis or {}
        areas = [
            self._coverage_area("Business Goals", len(analysis.get("businessGoals") or [])),
            {
                "area": "Functional Requirements",
                "count": total,
                "coveredCount": covered,
                "status": "Covered" if total and covered == total else "Uncovered",
            },
            self._coverage_area("Acceptance Criteria", len(criteria)),
            self._coverage_area("Business Rules", len(analysis.get("businessRules") or []), required=False),
            self._coverage_area("Dependencies", len(analysis.get("dependencies") or []), required=False),
            self._coverage_area("Non-Functional Requirements", len(analysis.get("nonFunctionalRequirements") or []), required=False),
            {
                "area": "Open Questions",
                "count": len(analysis.get("openQuestions") or []),
                "coveredCount": 0,
                "status": "Open" if analysis.get("openQuestions") else "None",
            },
        ]
        return {
            "functionalRequirementCount": total,
            "coveredFunctionalRequirementCount": covered,
            "coveragePercent": round((covered / total) * 100) if total else 0,
            "status": "Complete" if total and covered == total else "Incomplete",
            "mappings": mappings,
            "uncoveredFunctionalRequirements": [
                item["functionalRequirement"] for item in mappings if item["status"] == "Uncovered"
            ],
            "areas": areas,
            "uncoveredAreas": [
                item["area"] for item in areas if item["status"] == "Uncovered"
            ],
        }

    def refresh_projection(self, analysis: dict[str, Any]) -> None:
        records = list(analysis.get("acceptanceCriteriaRecords") or [])
        suggestions = list(analysis.get("acceptanceCriteriaSuggestions") or [])
        active = records or suggestions
        analysis["acceptanceCoverage"] = self.validate_coverage(
            list(analysis.get("functionalRequirements") or []),
            active,
            analysis,
        )
        analysis["acceptanceEvidence"] = [
            evidence
            for criterion in active
            for evidence in criterion.get("evidence") or []
        ]

    def normalize_edited(
        self,
        value: dict[str, Any],
        *,
        text: str,
        order: int,
    ) -> dict[str, Any]:
        functional = str(value.get("mappedFunctionalRequirement") or "")
        evidence = list(value.get("evidence") or [])
        return {
            **self._criterion(
                text=text,
                origin="User Added",
                status="PendingReview",
                functional=functional,
                evidence=evidence,
                order=order,
                criterion_id=str(value.get("criterionId") or ""),
            ),
            "editedFrom": str(value.get("origin") or "AI Inferred"),
        }

    @staticmethod
    def _facts(analysis: dict[str, Any]) -> RequirementFacts:
        functional = [str(item).strip() for item in analysis.get("functionalRequirements") or [] if str(item).strip()]
        actions = _unique(
            match.group(1).lower()
            for text in functional
            for match in _ACTION_PATTERN.finditer(text)
        )
        entities = _unique(
            phrase.strip(" .")
            for text in functional
            for phrase in re.findall(
                r"\b(?:view|show|display|search|filter|review|identify|detect|monitor|receive|access|manage)\s+"
                r"(?:the |a |an )?([A-Za-z][A-Za-z0-9 -]{2,45})",
                text,
                re.I,
            )
        )
        outputs = _unique(
            text for text in functional
            if re.search(r"\b(show|display|return|provide|notify|generate|calculate|export)\b", text, re.I)
        )
        return RequirementFacts(
            business_goal=list(analysis.get("businessGoals") or []),
            functional_goal=functional,
            actor=list(analysis.get("actors") or []),
            primary_capability=actions[0].title() if actions else "",
            entities=entities,
            actions=actions,
            outputs=outputs,
            constraints=list(analysis.get("constraints") or []),
            business_rules=list(analysis.get("businessRules") or []),
            dependencies=list(analysis.get("dependencies") or []),
            assumptions=list(analysis.get("assumptions") or []),
            open_questions=list(analysis.get("openQuestions") or []),
        )

    @staticmethod
    def _missing_information(
        facts: RequirementFacts,
        has_criteria: bool,
        has_non_functional: bool,
    ) -> list[dict[str, Any]]:
        checks = [
            ("Actor", facts.actor, "Identify who performs or receives the capability."),
            ("Trigger", [item for item in facts.functional_goal if _TRIGGER_PATTERN.search(item)], "Define when the behavior starts."),
            ("Observable Output", facts.outputs, "Define the business-visible result."),
            ("Business Rules", facts.business_rules, "Confirm whether business rules constrain the outcome."),
            ("Constraints", facts.constraints, "Confirm applicable limits or operating constraints."),
            ("Acceptance Criteria", ["present"] if has_criteria else [], "Review evidence-driven suggested criteria."),
            ("Non-Functional Requirements", ["present"] if has_non_functional else [], "Confirm performance, reliability, security, or accessibility expectations."),
        ]
        return [
            {
                "field": name,
                "status": "Missing",
                "reason": reason,
                "blocksGeneration": name in {"Actor", "Observable Output"} and not facts.functional_goal,
            }
            for name, value, reason in checks
            if not value
        ]

    @staticmethod
    def _assumptions(facts: RequirementFacts) -> list[dict[str, Any]]:
        return [
            {
                "assumptionId": f"assumption_{index + 1}",
                "text": text,
                "reason": "The source labels this statement as an assumption; it is not Acceptance Criteria.",
                "confidence": 0.9,
                "status": "NeedsReview",
                "origin": "Source Derived",
            }
            for index, text in enumerate(facts.assumptions)
        ]

    @staticmethod
    def _criterion(
        *,
        text: str,
        origin: str,
        status: str,
        functional: str,
        evidence: list[dict[str, Any]],
        order: int,
        criterion_id: str = "",
        criterion_type: str = "Functional",
    ) -> dict[str, Any]:
        return {
            "criterionId": criterion_id or f"ac_{uuid4().hex}",
            "title": IntelligentAcceptanceCriteriaEngine._title(text),
            "text": text.strip(),
            "type": criterion_type,
            "origin": origin,
            "status": status,
            "confidence": round(min((item.get("confidence", 0.8) for item in evidence), default=0.75), 2),
            "mappedFunctionalRequirement": functional,
            "requirementCoverage": "Mapped" if functional else "Unmapped",
            "evidence": evidence,
            "quality": {
                "atomic": True,
                "independent": True,
                "verifiable": True,
                "implementationIndependent": not bool(re.search(r"\b(class|method|database table|framework|library)\b", text, re.I)),
                "traceable": bool(evidence),
            },
            "order": order,
        }

    @staticmethod
    def _source_evidence(text: str, requirement: dict[str, Any]) -> list[dict[str, Any]]:
        return [RequirementEvidence(
            requirement_sentence=text,
            matched_phrase=text,
            confidence=1.0,
            source=str(requirement.get("sourceType") or "Requirement"),
        ).to_dict()]

    @staticmethod
    def _best_functional_match(text: str, functional: list[str]) -> str:
        ranked = sorted(functional, key=lambda item: len(_terms(text) & _terms(item)), reverse=True)
        return ranked[0] if ranked and _terms(text) & _terms(ranked[0]) else ""

    @staticmethod
    def _same_requirement(left: str, right: str) -> bool:
        if not left or not right:
            return False
        return left == right or len(_terms(left) & _terms(right)) >= max(2, min(len(_terms(left)), len(_terms(right))) // 2)

    @staticmethod
    def _action(text: str) -> str:
        match = _ACTION_PATTERN.search(text)
        return match.group(1).lower() if match else ""

    @staticmethod
    def _matched_phrase(text: str, action: str) -> str:
        match = re.search(rf"\b{re.escape(action)}\b.+", text, re.I)
        return (match.group(0) if match else text).strip().rstrip(".")

    @staticmethod
    def _observable_outcome(text: str, action: str) -> str:
        phrase = IntelligentAcceptanceCriteriaEngine._matched_phrase(text, action)
        if action in {"view", "show", "display", "review", "open", "access"}:
            subject = re.sub(rf"^{re.escape(action)}\s+", "", phrase, flags=re.I)
            return f"{subject} is available for the described business purpose"
        if action == "filter":
            subject = re.sub(r"^filter\s+", "", phrase, flags=re.I)
            return f"the results contain only {subject} matching the requested filter"
        if action == "search":
            subject = re.sub(r"^search\s+", "", phrase, flags=re.I)
            return f"matching {subject} are returned"
        if action in {"identify", "detect", "monitor"}:
            subject = re.sub(rf"^{re.escape(action)}\s+", "", phrase, flags=re.I)
            verb = {"identify": "identified", "detect": "detected", "monitor": "monitored"}[action]
            return f"{subject} can be {verb} from the observable result"
        return f"the stated outcome for '{phrase}' is observable and complete"

    @staticmethod
    def _matching_actor(functional: str, actors: list[str]) -> str:
        for actor in actors:
            if str(actor).lower() in functional.lower():
                return str(actor)
        return str(actors[0]) if len(actors) == 1 else ""

    @staticmethod
    def _title(text: str) -> str:
        cleaned = re.sub(r"(?i)^(scenario:\s*)", "", text).splitlines()[0].strip(" .")
        words = cleaned.split()
        return " ".join(words[:8]).title() or "Acceptance Criterion"

    @staticmethod
    def _evidence_corpus(analysis: dict[str, Any], requirement: dict[str, Any]) -> str:
        values = [
            str(requirement.get("normalizedRequirement") or ""),
            *(str(item) for key in (
                "businessRules", "constraints", "nonFunctionalRequirements", "dependencies",
            ) for item in analysis.get(key) or []),
        ]
        return "\n".join(values)

    @staticmethod
    def _unsupported_generic_category(functional: str, evidence_corpus: str) -> str:
        for category, pattern in _GENERIC_RULES.items():
            if pattern.search(functional) and not pattern.search(evidence_corpus):
                return category
        return ""

    @staticmethod
    def _coverage_area(area: str, count: int, *, required: bool = True) -> dict[str, Any]:
        return {
            "area": area,
            "count": count,
            "coveredCount": count,
            "status": "Covered" if count else ("Uncovered" if required else "Not Provided"),
        }


def _terms(value: str) -> set[str]:
    return {
        item.lower()
        for item in re.findall(r"[A-Za-z][A-Za-z0-9-]+", value)
        if len(item) > 2 and item.lower() not in {
            "the", "and", "for", "with", "must", "shall", "should", "user", "users",
            "when", "then", "given", "that", "this", "from", "into",
        }
    }


def _unique(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result
