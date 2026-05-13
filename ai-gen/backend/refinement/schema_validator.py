"""Strict validation and normalization for model-suggested refinement JSON."""

from __future__ import annotations

from typing import Any

from backend.refinement.normalizer import normalize_refinement


def validate_task_refinement(raw: dict) -> dict:
    """Normalize and sanitize model refinement JSON."""

    return normalize_refinement(raw if isinstance(raw, dict) else {})
