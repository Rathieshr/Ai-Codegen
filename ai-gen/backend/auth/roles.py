"""Role-based approval definitions for ai-gen pipeline stages.

Each stage has a set of roles that are allowed to approve it.
If ``AI_GEN_ROLE_ENFORCEMENT`` is not set to ``"1"`` the role check
is advisory only (logged but not blocking) so existing integrations
keep working without changes.
"""

from __future__ import annotations

import logging
import os
from enum import Enum
from typing import Any

logger = logging.getLogger("ai_gen.auth.roles")


class ApprovalRole(str, Enum):
    """Named roles that can approve pipeline stages."""

    PRODUCT = "product"
    DEVELOPER = "developer"
    QA = "qa"
    LEAD = "lead"
    ADMIN = "admin"
    # Generic fallback — used by ADO extension / VS Code when no role is specified
    SYSTEM = "system"


# ---------------------------------------------------------------------------
# Stage → allowed approver roles
# ---------------------------------------------------------------------------
STAGE_REQUIRED_ROLES: dict[str, set[ApprovalRole]] = {
    # Business analysis: product owner or tech lead
    "ba": {ApprovalRole.PRODUCT, ApprovalRole.LEAD, ApprovalRole.ADMIN},
    # UI plan: product + developer sign-off
    "ui": {ApprovalRole.PRODUCT, ApprovalRole.DEVELOPER, ApprovalRole.LEAD, ApprovalRole.ADMIN},
    "ui_optional": {ApprovalRole.PRODUCT, ApprovalRole.DEVELOPER, ApprovalRole.LEAD, ApprovalRole.ADMIN},
    "ui_plan": {ApprovalRole.PRODUCT, ApprovalRole.DEVELOPER, ApprovalRole.LEAD, ApprovalRole.ADMIN},
    # Dev packet: developer or lead
    "dev_packet": {ApprovalRole.DEVELOPER, ApprovalRole.LEAD, ApprovalRole.ADMIN},
    "fix_packet": {ApprovalRole.DEVELOPER, ApprovalRole.LEAD, ApprovalRole.ADMIN},
    "task_analysis": {ApprovalRole.DEVELOPER, ApprovalRole.LEAD, ApprovalRole.ADMIN},
    "task_planning": {ApprovalRole.DEVELOPER, ApprovalRole.LEAD, ApprovalRole.ADMIN},
    # Testing: QA or lead
    "test_checklist": {ApprovalRole.QA, ApprovalRole.LEAD, ApprovalRole.ADMIN},
    "test_planning": {ApprovalRole.QA, ApprovalRole.LEAD, ApprovalRole.ADMIN},
    "test_design": {ApprovalRole.QA, ApprovalRole.LEAD, ApprovalRole.ADMIN},
    "regression_tests": {ApprovalRole.QA, ApprovalRole.LEAD, ApprovalRole.ADMIN},
    # Critic: lead or admin only (highest gate)
    "critic": {ApprovalRole.LEAD, ApprovalRole.ADMIN},
    # Epic / planning stages
    "epic_analysis": {ApprovalRole.PRODUCT, ApprovalRole.LEAD, ApprovalRole.ADMIN},
    "feature_generation": {ApprovalRole.PRODUCT, ApprovalRole.LEAD, ApprovalRole.ADMIN},
    "story_generation": {ApprovalRole.PRODUCT, ApprovalRole.LEAD, ApprovalRole.ADMIN},
    "review": {ApprovalRole.PRODUCT, ApprovalRole.LEAD, ApprovalRole.ADMIN},
    # Bug / spike / research stages
    "bug_analysis": {ApprovalRole.DEVELOPER, ApprovalRole.LEAD, ApprovalRole.ADMIN},
    "impact_analysis": {ApprovalRole.DEVELOPER, ApprovalRole.LEAD, ApprovalRole.ADMIN},
    "research_plan": {ApprovalRole.DEVELOPER, ApprovalRole.LEAD, ApprovalRole.ADMIN},
    "findings": {ApprovalRole.DEVELOPER, ApprovalRole.LEAD, ApprovalRole.ADMIN},
    "recommendation": {ApprovalRole.LEAD, ApprovalRole.ADMIN},
}

# Stages not listed above allow any authenticated role
_DEFAULT_ALLOWED: set[ApprovalRole] = {r for r in ApprovalRole}


def allowed_roles_for_stage(stage: str) -> set[ApprovalRole]:
    return STAGE_REQUIRED_ROLES.get(stage, _DEFAULT_ALLOWED)


def _role_enforcement_enabled() -> bool:
    return os.getenv("AI_GEN_ROLE_ENFORCEMENT", "0") == "1"


def validate_approver_role(stage: str, role_str: str | None) -> dict[str, Any]:
    """Check whether *role_str* is permitted to approve *stage*.

    Returns a dict with:
      - ``allowed`` (bool)
      - ``role`` (str | None) — normalized role value
      - ``required_roles`` (list[str])
      - ``enforced`` (bool) — False means advisory only
    """
    enforced = _role_enforcement_enabled()
    allowed_set = allowed_roles_for_stage(stage)
    required = sorted(r.value for r in allowed_set)

    if not role_str or not role_str.strip():
        result = {
            "allowed": not enforced,  # open if not enforced
            "role": None,
            "required_roles": required,
            "enforced": enforced,
            "reason": "No role provided — " + ("blocked (enforcement on)" if enforced else "advisory warning only"),
        }
        if enforced:
            logger.warning("ai-gen roles: stage=%s rejected — no role provided", stage)
        else:
            logger.debug("ai-gen roles: stage=%s — no role provided (advisory)", stage)
        return result

    # Normalize: strip, lowercase, map aliases
    normalized = role_str.strip().lower()
    _aliases = {
        "pm": ApprovalRole.PRODUCT,
        "product_manager": ApprovalRole.PRODUCT,
        "product owner": ApprovalRole.PRODUCT,
        "dev": ApprovalRole.DEVELOPER,
        "engineer": ApprovalRole.DEVELOPER,
        "tester": ApprovalRole.QA,
        "tech lead": ApprovalRole.LEAD,
        "tech_lead": ApprovalRole.LEAD,
        "administrator": ApprovalRole.ADMIN,
    }
    try:
        role = _aliases.get(normalized) or ApprovalRole(normalized)
    except ValueError:
        role = ApprovalRole.SYSTEM

    is_allowed = role in allowed_set
    if not is_allowed:
        msg = f"ai-gen roles: stage={stage} role={role.value} not in required={required}"
        if enforced:
            logger.warning(msg)
        else:
            logger.debug(msg + " (advisory)")

    return {
        "allowed": is_allowed or not enforced,
        "role": role.value,
        "required_roles": required,
        "enforced": enforced,
        "reason": "approved" if is_allowed else (
            f"Role '{role.value}' is not permitted for stage '{stage}'"
        ),
    }
