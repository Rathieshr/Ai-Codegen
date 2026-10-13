"""Acceptance criteria coverage checker for ai-gen pipeline critic stage.

Checks whether the proposed engineering solution (stage output) actually
addresses each acceptance criterion listed on the work item.

Algorithm
---------
1. Tokenise each AC item into a set of significant keywords.
2. For each keyword set, scan the full stage output text for matches.
3. An AC item is "covered" if ≥ COVERAGE_THRESHOLD fraction of its
   keywords appear in the output.
4. Returns a ``CoverageReport`` with per-item verdicts and an overall score.

The check is intentionally lightweight — pure Python, no ML, no network.
The goal is to give the critic assistant a structured signal, not a perfect
semantic similarity score.
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Fraction of AC keywords that must appear in output to call an item "covered"
COVERAGE_THRESHOLD = 0.55

# Words too short or too common to be meaningful signals
_STOP_WORDS: frozenset[str] = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "in", "is", "are",
    "be", "that", "this", "it", "on", "with", "for", "as", "at",
    "by", "from", "user", "system", "should", "must", "shall", "can",
    "will", "have", "has", "been", "not", "when", "if", "then", "so",
    "all", "any", "each", "every", "given", "able", "their", "which",
})


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class AcItemResult:
    item: str                      # Original AC item text
    covered: bool
    matched_keywords: list[str]
    missing_keywords: list[str]
    coverage_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "item": self.item,
            "covered": self.covered,
            "matched_keywords": self.matched_keywords,
            "missing_keywords": self.missing_keywords,
            "coverage_ratio": round(self.coverage_ratio, 3),
        }


@dataclass
class CoverageReport:
    overall_score: float            # 0.0 – 1.0
    covered_count: int
    total_count: int
    items: list[AcItemResult] = field(default_factory=list)
    uncovered_items: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True when all AC items are covered."""
        return self.covered_count == self.total_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": round(self.overall_score, 3),
            "covered_count": self.covered_count,
            "total_count": self.total_count,
            "passed": self.passed,
            "items": [i.to_dict() for i in self.items],
            "uncovered_items": self.uncovered_items,
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_ac_coverage(
    acceptance_criteria: str | list[str],
    stage_output: dict[str, Any],
    threshold: float = COVERAGE_THRESHOLD,
) -> CoverageReport:
    """Check how much of *acceptance_criteria* is addressed in *stage_output*.

    Parameters
    ----------
    acceptance_criteria:
        Either a plain string (will be split on newlines / bullet markers)
        or an already-split list of individual AC items.
    stage_output:
        The raw dict returned by the pipeline stage (BA, dev_packet, etc.).
    threshold:
        Keyword match ratio required to count an item as covered.

    Returns
    -------
    CoverageReport
    """
    ac_items = _parse_ac_items(acceptance_criteria)
    if not ac_items:
        return CoverageReport(
            overall_score=1.0,
            covered_count=0,
            total_count=0,
        )

    output_tokens = _tokenise(_flatten_output(stage_output))
    results: list[AcItemResult] = []

    for item in ac_items:
        keywords = _significant_keywords(item)
        if not keywords:
            # Trivially covered — no meaningful content to check
            results.append(AcItemResult(
                item=item,
                covered=True,
                matched_keywords=[],
                missing_keywords=[],
                coverage_ratio=1.0,
            ))
            continue

        matched = [kw for kw in keywords if kw in output_tokens]
        missing = [kw for kw in keywords if kw not in output_tokens]
        ratio = len(matched) / len(keywords)
        results.append(AcItemResult(
            item=item,
            covered=ratio >= threshold,
            matched_keywords=matched,
            missing_keywords=missing,
            coverage_ratio=ratio,
        ))

    covered = sum(1 for r in results if r.covered)
    overall = covered / len(results) if results else 1.0
    uncovered = [r.item for r in results if not r.covered]

    return CoverageReport(
        overall_score=overall,
        covered_count=covered,
        total_count=len(results),
        items=results,
        uncovered_items=uncovered,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_ac_items(raw: str | list[str]) -> list[str]:
    """Split raw AC text into individual items."""
    if isinstance(raw, list):
        return [item.strip() for item in raw if str(item).strip()]

    # Split on common list delimiters: newlines, bullet markers, numbered lists
    pattern = re.compile(
        r"""
        (?:\r?\n)           # newline break
        |(?:^|\n)\s*[-•*]\s  # bullet: -, •, *
        |(?:^|\n)\s*\d+[.)]\s  # numbered: 1. or 1)
        """,
        re.VERBOSE,
    )
    parts = pattern.split(raw)
    return [p.strip() for p in parts if p.strip() and len(p.strip()) > 5]


def _significant_keywords(text: str) -> list[str]:
    """Extract meaningful lowercase keywords from text."""
    tokens = _tokenise(text)
    return [t for t in tokens if t not in _STOP_WORDS and len(t) > 2]


def _tokenise(text: str) -> set[str]:
    """Lowercase and split text into word tokens, stripping punctuation."""
    cleaned = text.lower().translate(
        str.maketrans(string.punctuation, " " * len(string.punctuation))
    )
    return set(cleaned.split())


def _flatten_output(obj: Any, _depth: int = 0) -> str:
    """Recursively flatten any JSON-serialisable object to a string."""
    if _depth > 5:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return " ".join(_flatten_output(v, _depth + 1) for v in obj.values())
    if isinstance(obj, list):
        return " ".join(_flatten_output(i, _depth + 1) for i in obj)
    return str(obj)
