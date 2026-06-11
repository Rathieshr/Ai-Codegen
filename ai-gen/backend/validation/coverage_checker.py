"""Acceptance criteria coverage checker — separate module entry point.

Imports from ``backend.validation`` so callers can use either:

    from backend.validation import check_ac_coverage, CoverageReport
    from backend.validation.coverage_checker import check_ac_coverage

Both paths work identically.
"""

from backend.validation import (  # re-export
    AcItemResult,
    CoverageReport,
    check_ac_coverage,
)

__all__ = ["check_ac_coverage", "CoverageReport", "AcItemResult"]
