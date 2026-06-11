"""Stage output guardrail checker.

Screens AI stage output before it is stored or shown to the user.

Checks
------
1. **Sensitive data leak** — patterns that look like API keys, secrets,
   connection strings, or passwords embedded in the model output.
2. **Scope explosion** — dev/test stages targeting an unreasonably large
   number of files (configurable, default 30).
3. **Unauthorized flow change** — the output attempts to change a flow
   that is marked as locked in the pipeline constraints.
4. **Prompt injection** — output contains instruction-injection patterns
   (e.g. "ignore previous instructions").

Each check returns a ``GuardrailViolation`` if it fires. All violations
are collected and returned together so callers see the full picture.

Severity levels
---------------
- ``block``  — output must not be stored or shown.
- ``warn``   — output can proceed but should be flagged to the human reviewer.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("ai_gen.guardrails")

# ---------------------------------------------------------------------------
# Sensitive data patterns
# ---------------------------------------------------------------------------
_SENSITIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("api_key_generic",    re.compile(r'(?i)(api[_-]?key|apikey)\s*[:=]\s*["\']?[A-Za-z0-9\-_]{16,}["\']?')),
    ("bearer_token",       re.compile(r'(?i)bearer\s+[A-Za-z0-9\-_.~+/]+=*')),
    ("aws_access_key",     re.compile(r'(?i)AKIA[0-9A-Z]{16}')),
    ("connection_string",  re.compile(r'(?i)(Server|Data Source|mongodb(\+srv)?|postgres|mysql)=.{10,}')),
    ("private_key_header", re.compile(r'-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----')),
    ("password_field",     re.compile(r'(?i)["\']?password["\']?\s*[:=]\s*["\'][^"\']{6,}["\']')),
    ("pat_token",          re.compile(r'(?i)(pat|personal.access.token)\s*[:=]\s*["\']?[A-Za-z0-9]{20,}["\']?')),
]

# ---------------------------------------------------------------------------
# Prompt injection phrases
# ---------------------------------------------------------------------------
_INJECTION_PHRASES: list[str] = [
    "ignore previous instructions",
    "ignore all instructions",
    "disregard the system prompt",
    "you are now",
    "act as if you are",
    "forget your instructions",
    "new system prompt",
    "override your",
]

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
_MAX_FILES_DEFAULT = 30


def _max_files() -> int:
    try:
        return max(1, int(os.getenv("AI_GEN_GUARD_MAX_FILES", str(_MAX_FILES_DEFAULT))))
    except ValueError:
        return _MAX_FILES_DEFAULT


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class GuardrailViolation:
    check: str
    severity: str          # "block" | "warn"
    message: str
    detail: str = ""
    stage: str = ""
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.check,
            "severity": self.severity,
            "message": self.message,
            "detail": self.detail,
            "stage": self.stage,
            "evidence": self.evidence,
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def guard_stage_output(
    stage: str,
    output: dict[str, Any],
    pipeline_constraints: list[str] | None = None,
) -> list[GuardrailViolation]:
    """Run all guardrail checks on *output* and return any violations.

    Parameters
    ----------
    stage:
        The pipeline stage name (e.g. ``"ba"``, ``"dev_packet"``).
    output:
        The raw dict returned by the stage assistant.
    pipeline_constraints:
        Optional list of constraint strings from the pipeline state
        (used for locked-flow detection).

    Returns
    -------
    list[GuardrailViolation]
        Empty list means clean. Non-empty means one or more checks fired.
    """
    violations: list[GuardrailViolation] = []
    raw_text = _flatten_to_text(output)

    violations.extend(_check_sensitive_data(stage, raw_text))
    violations.extend(_check_prompt_injection(stage, raw_text))
    violations.extend(_check_scope_explosion(stage, output))
    violations.extend(_check_locked_flow_change(stage, output, pipeline_constraints or []))

    if violations:
        severities = [v.severity for v in violations]
        logger.warning(
            "ai-gen guardrail: stage=%s violations=%d severities=%s",
            stage,
            len(violations),
            severities,
        )

    return violations


def has_blocking_violation(violations: list[GuardrailViolation]) -> bool:
    return any(v.severity == "block" for v in violations)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------
def _check_sensitive_data(stage: str, text: str) -> list[GuardrailViolation]:
    violations: list[GuardrailViolation] = []
    for name, pattern in _SENSITIVE_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            # Redact the actual match values before logging/storing
            redacted = [m[:6] + "***" if isinstance(m, str) else "***" for m in matches[:3]]
            violations.append(
                GuardrailViolation(
                    check=f"sensitive_data.{name}",
                    severity="block",
                    message=f"Stage output may contain sensitive data ({name}).",
                    detail="Output was not stored. Remove credentials from AI responses.",
                    stage=stage,
                    evidence=redacted,
                )
            )
    return violations


def _check_prompt_injection(stage: str, text: str) -> list[GuardrailViolation]:
    lowered = text.lower()
    violations: list[GuardrailViolation] = []
    for phrase in _INJECTION_PHRASES:
        if phrase in lowered:
            violations.append(
                GuardrailViolation(
                    check="prompt_injection",
                    severity="block",
                    message="Stage output contains a potential prompt injection phrase.",
                    detail=f"Detected phrase: '{phrase}'",
                    stage=stage,
                    evidence=[phrase],
                )
            )
            break  # one violation is enough; avoids duplicate blocks
    return violations


def _check_scope_explosion(stage: str, output: dict[str, Any]) -> list[GuardrailViolation]:
    """Warn when the dev stage targets too many files."""
    if stage not in {"dev_packet", "fix_packet", "task_planning", "task_analysis"}:
        return []
    files: list[str] = []
    for key in ("selected_files", "execution_files", "files", "target_files", "modified_files"):
        value = output.get(key)
        if isinstance(value, list):
            files.extend(str(f) for f in value)
    max_files = _max_files()
    if len(files) > max_files:
        return [
            GuardrailViolation(
                check="scope_explosion",
                severity="warn",
                message=f"Stage targets {len(files)} files which exceeds the limit of {max_files}.",
                detail="Review the execution packet — this may indicate scope creep.",
                stage=stage,
                evidence=[f"file_count={len(files)}", f"limit={max_files}"],
            )
        ]
    return []


def _check_locked_flow_change(
    stage: str,
    output: dict[str, Any],
    constraints: list[str],
) -> list[GuardrailViolation]:
    """Warn if output proposes changing a flow marked as locked in constraints."""
    locked_flows: list[str] = []
    for c in constraints:
        c_lower = str(c).lower()
        if "locked" in c_lower or "do not change" in c_lower or "readonly" in c_lower:
            locked_flows.append(c_lower)

    if not locked_flows:
        return []

    # Check if proposed base_flows or scope_hints touch a locked area
    proposed: list[str] = []
    for key in ("base_flows", "proposed_flows", "scope_hints", "modified_flows"):
        value = output.get(key)
        if isinstance(value, list):
            proposed.extend(str(v).lower() for v in value)

    flagged: list[str] = []
    for locked in locked_flows:
        for flow in proposed:
            if any(token in locked for token in flow.split("_")):
                flagged.append(f"'{flow}' conflicts with locked constraint: '{locked}'")

    if flagged:
        return [
            GuardrailViolation(
                check="locked_flow_change",
                severity="warn",
                message="Stage output proposes changes to a locked flow.",
                detail="Human reviewer must confirm before approving.",
                stage=stage,
                evidence=flagged[:5],
            )
        ]
    return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _flatten_to_text(obj: Any, _depth: int = 0) -> str:
    """Recursively flatten any JSON-serialisable object to a single string."""
    if _depth > 6:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return " ".join(_flatten_to_text(v, _depth + 1) for v in obj.values())
    if isinstance(obj, list):
        return " ".join(_flatten_to_text(item, _depth + 1) for item in obj)
    try:
        return json.dumps(obj)
    except Exception:
        return str(obj)
