"""Deterministic Azure DevOps work item optimization for execution prompts."""

from __future__ import annotations

import re


SURFACE_KEYWORDS = {
    "ui_validation": (
        "regex",
        "validation",
        "validate",
        "max length",
        "limit",
        "input",
        "field",
        "placeholder",
        "form",
        "email",
        "password",
    ),
    "api/controller": (
        "api",
        "endpoint",
        "controller",
        "response",
        "request body",
        "payload",
    ),
    "service/auth": (
        "service",
        "logic",
        "token",
        "session",
        "auth lifecycle",
        "credential",
    ),
    "ui_screen": (
        "screen",
        "page",
        "dashboard",
        "layout",
        "widget",
        "component",
    ),
}


def optimize_work_item_request(
    title: str,
    description: str | None = None,
    acceptance_criteria: str | None = None,
    tags: list[str] | None = None,
    work_item_type: str | None = None,
    area_path: str | None = None,
    iteration_path: str | None = None,
) -> dict:
    """Convert raw work item text into a compact engineering request."""

    combined_text = _clean_text(
        "\n".join(
            value
            for value in [
                title,
                description or "",
                acceptance_criteria or "",
                work_item_type or "",
                area_path or "",
                iteration_path or "",
                " ".join(tags or []),
            ]
            if value
        )
    )
    surface = infer_work_item_surface(combined_text, tags)
    scope = infer_work_item_scope(combined_text, surface)
    task_summary = build_work_item_task_summary(
        title=title,
        description=description,
        acceptance_criteria=acceptance_criteria,
        surface=surface,
    )
    focus_rules = _focus_rules(surface, combined_text)
    return {
        "task_summary": task_summary,
        "technical_surface": surface,
        "likely_scope": scope,
        "inferred_focus_rules": focus_rules,
        "normalized_query": task_summary,
    }


def infer_work_item_surface(text: str, tags: list[str] | None = None) -> str | None:
    """Infer the likely technical surface using simple keyword scoring."""

    normalized = _normalize_for_match(" ".join([text, " ".join(tags or [])]))
    best_surface: str | None = None
    best_score = 0
    for surface, keywords in SURFACE_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in normalized)
        if score > best_score:
            best_surface = surface
            best_score = score
    return best_surface if best_score > 0 else None


def infer_work_item_scope(text: str, surface: str | None) -> list[str]:
    """Return a small first-pass implementation scope for the inferred surface."""

    normalized = _normalize_for_match(text)
    domain = _domain_label(normalized)
    scopes_by_surface = {
        "ui_validation": [
            f"{domain} form input validation",
            "email/password field validators" if "email" in normalized or "password" in normalized else "field validation rules",
            "shared auth form validation helpers" if domain == "login" else "shared form validation helpers",
        ],
        "ui_screen": [
            f"{domain} screen/page component",
            "view model / form binding",
            "input state handlers",
        ],
        "api/controller": [
            f"{domain} controller",
            "request validation",
            "API response shaping",
        ],
        "service/auth": [
            "auth service",
            "credential verification logic",
            "session/token handling",
        ],
    }
    fallback = [f"{domain} implementation path", "smallest relevant code surface"]
    return _dedupe(scopes_by_surface.get(surface or "", fallback))[:4]


def build_work_item_task_summary(
    title: str,
    description: str | None = None,
    acceptance_criteria: str | None = None,
    surface: str | None = None,
) -> str:
    """Rewrite work item wording into a concise engineering objective."""

    text = _clean_text(" ".join(value for value in [title, description or "", acceptance_criteria or ""] if value))
    normalized = _normalize_for_match(text)
    action = "Fix" if _has_any(normalized, ("fix", "bug", "issue", "error")) else "Implement"
    domain = _domain_label(normalized)

    if surface == "ui_validation":
        fields = _field_phrase(normalized)
        rules = _validation_rule_phrase(normalized)
        return f"{action} {domain} form validation so {fields} enforce {rules}."
    if surface == "ui_screen":
        return f"{action} {domain} screen behavior with the requested UI changes."
    if surface == "api/controller":
        return f"{action} {domain} API handling for the requested request and response behavior."
    if surface == "service/auth":
        return f"{action} {domain} service logic while preserving existing auth/session behavior."

    compact = _strip_filler(text)
    if not compact:
        compact = title.strip() or "Update the requested work item behavior"
    return _sentence(compact[:180])


def _focus_rules(surface: str | None, text: str) -> list[str]:
    normalized = _normalize_for_match(text)
    rules: list[str] = []
    if surface == "ui_validation":
        rules.extend(
            [
                "Check the UI/input validation layer before widening to backend auth logic.",
                "Start with the smallest validation-related scope.",
            ]
        )
    elif surface == "ui_screen":
        rules.extend(
            [
                "Check the screen/component layer before widening to service logic.",
                "Verify form state and bindings before changing business logic.",
            ]
        )
    elif surface == "api/controller":
        rules.extend(
            [
                "Check request validation and controller behavior before changing services.",
                "Keep response changes narrow and compatible.",
            ]
        )
    elif surface == "service/auth":
        rules.append("Check auth service behavior before changing UI or data models.")
    else:
        rules.append("Start with the smallest code path that explains the work item.")

    if _has_any(normalized, ("login", "auth", "password", "session", "token")):
        rules.append("Preserve existing credential validation and session/token behavior.")
    rules.append("Do not widen scope unless the first-pass surface is insufficient.")
    return _dedupe(rules)


def _field_phrase(normalized: str) -> str:
    if "email" in normalized and "password" in normalized:
        return "email and password fields"
    if "email" in normalized:
        return "email fields"
    if "password" in normalized:
        return "password fields"
    return "input fields"


def _validation_rule_phrase(normalized: str) -> str:
    rules: list[str] = []
    if _has_any(normalized, ("regex", "@", "format", "email")):
        rules.append("valid format")
    if _has_any(normalized, ("limit", "max length", "text limit", "cap", "length")):
        rules.append("length limits")
    if not rules:
        rules.append("the required validation rules")
    return " and ".join(rules)


def _domain_label(normalized: str) -> str:
    if _has_any(normalized, ("login", "signin", "sign in", "auth", "password", "credential")):
        return "login"
    if _has_any(normalized, ("signup", "register", "create account", "onboarding")):
        return "signup"
    if _has_any(normalized, ("payment", "checkout", "invoice", "transaction")):
        return "payment"
    if "dashboard" in normalized:
        return "dashboard"
    if _has_any(normalized, ("profile", "account", "settings")):
        return "profile"
    return "target"


def _strip_filler(text: str) -> str:
    value = _clean_text(text)
    value = re.sub(r"\b(please|just|should|needs to|need to|as a user|i want to)\b", "", value, flags=re.I)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return _sentence(value)


def _sentence(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    return value if value.endswith((".", "!", "?")) else f"{value}."


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _normalize_for_match(value: str) -> str:
    return _clean_text(value).lower()


def _has_any(value: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in value for keyword in keywords)


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in output:
            output.append(cleaned)
    return output
