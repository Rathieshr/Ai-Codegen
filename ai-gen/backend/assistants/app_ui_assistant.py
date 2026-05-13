"""App UI stage for the structured assistant pipeline."""

from __future__ import annotations


def run_app_ui_assistant(ba_output: dict, refinement: dict | None = None, review_context: dict | None = None) -> dict:
    """Generate structured UI guidance without generating code."""

    refinement = refinement or {}
    review_context = review_context or {}
    base_flow = _first(ba_output.get("flows", [])) or _first(refinement.get("base_flows", [])) or refinement.get("refined_base_flow") or "workflow"
    surface = _first(refinement.get("surfaces", [])) or refinement.get("refined_surface") or refinement.get("surface") or ""
    fields = _build_fields(ba_output, refinement, review_context)
    screen_type = _screen_type(surface, ba_output)
    screen_name = _screen_name(base_flow, screen_type)
    platform = _platform(surface, ba_output)
    skippable = screen_type == "unknown" and surface in {"service/auth", "api/controller"}
    reason = {
        "known": _known_ui_points(ba_output, refinement),
        "missing": [],
        "goal": "Turn the approved requirement into screen structure, fields, actions, and states.",
    }
    act = {
        "screen_name": screen_name,
        "screen_type": screen_type,
        "field_count": len(fields),
        "action_count": len(_actions(base_flow, screen_type, fields)),
    }
    observe = {
        "surface": surface or "unknown",
        "variant": _first(ba_output.get("variants", [])) or ba_output.get("variant") or _first(refinement.get("variants", [])) or refinement.get("refined_variant"),
        "skippable": skippable,
    }
    actions = _actions(base_flow, screen_type, fields)
    states = _states(screen_type)
    summary = _ui_summary(screen_name, fields, actions, states, base_flow, ba_output, refinement)
    output = {
        "assistant": "app_ui",
        "screen_name": screen_name,
        "screen_type": screen_type,
        "platform": platform,
        "user_goal": summary,
        "summary": summary,
        "layout": _layout(screen_type, fields),
        "fields": fields,
        "actions": actions,
        "states": states,
        "ux_notes": _ux_notes(ba_output, refinement),
        "accessibility_notes": _accessibility_notes(fields),
        "unknowns": _dedupe(
            list(refinement.get("refinement_unknowns", []))
            + [str(item.get("message", "")).strip() for item in review_context.get("critic_findings", [])]
        ),
        "skippable": skippable,
        "skip_reason": "No dedicated UI surface is required for this task." if skippable else "",
        "react": {
            "reason": reason,
            "act": act,
            "observe": observe,
            "decision": "ready_for_approval" if not skippable else "blocked",
        },
    }
    return output


def _build_fields(ba_output: dict, refinement: dict, review_context: dict) -> list[dict]:
    names = list(refinement.get("refined_fields", [])) or list(refinement.get("fields", []))
    validations = list(refinement.get("refined_validations", [])) or list(refinement.get("validations", []))
    previous_output = review_context.get("previous_output", {})
    if not names and isinstance(previous_output, dict):
        names = [field.get("name", "") for field in previous_output.get("fields", []) if field.get("name")]
    if not validations and isinstance(previous_output, dict):
        for field in previous_output.get("fields", []):
            validations.extend(field.get("validation", []))
    if not names:
        requirement = str(ba_output.get("refined_requirement", "")).lower()
        if "email" in requirement:
            names.append("email")
        if "password" in requirement:
            names.append("password")
        if "phone" in requirement:
            names.append("phone_number")
    output: list[dict] = []
    for name in _dedupe(names):
        output.append(
            {
                "name": name,
                "type": _field_type(name),
                "validation": _dedupe(validations)[:4],
            }
        )
    return output


def _screen_type(surface: str, ba_output: dict) -> str:
    lowered = f"{surface} {ba_output.get('refined_requirement', '')}".lower()
    if any(keyword in lowered for keyword in ["form", "validation", "login", "signup", "input"]):
        return "form"
    if any(keyword in lowered for keyword in ["dashboard", "widget", "stats", "overview"]):
        return "dashboard"
    if "settings" in lowered:
        return "settings"
    if any(keyword in lowered for keyword in ["detail", "profile"]):
        return "detail"
    if any(keyword in lowered for keyword in ["list", "table", "filter"]):
        return "list"
    return "unknown"


def _screen_name(base_flow: str, screen_type: str) -> str:
    if base_flow == "workflow":
        return "Workflow Screen"
    if screen_type == "dashboard":
        return f"{base_flow.title()} Dashboard"
    return f"{base_flow.title()} {screen_type.title()}".strip()


def _platform(surface: str, ba_output: dict) -> str:
    lowered = f"{surface} {ba_output.get('refined_requirement', '')}".lower()
    if any(keyword in lowered for keyword in ["mobile", "android", "ios"]):
        return "mobile"
    if any(keyword in lowered for keyword in ["web", "browser", "dashboard", "page"]):
        return "web"
    return "unknown"


def _user_goal(base_flow: str, screen_type: str) -> str:
    if screen_type == "dashboard":
        return f"Review {base_flow} information quickly and act on it."
    return f"Complete the {base_flow} task without confusion or extra steps."


def _ui_summary(
    screen_name: str,
    fields: list[dict],
    actions: list[str],
    states: list[str],
    base_flow: str,
    ba_output: dict,
    refinement: dict,
) -> str:
    field_names = [str(field.get("name", "")).strip() for field in fields if str(field.get("name", "")).strip()]
    variants = set(list(ba_output.get("variants", [])) + list(refinement.get("variants", [])) + list(refinement.get("refined_variants", [])))
    if base_flow == "login" and "phone_otp" in variants and {"phone_number", "otp"}.issubset(set(field_names)):
        return "Design login UI with phone number entry, OTP request, OTP verification state, validation and error handling."

    primary_fields = ", ".join(name.replace("_", " ") for name in field_names[:3]) if field_names else "primary components"
    main_actions = ", ".join(actions[:2]) if actions else "main actions"
    state_summary = ", ".join(state for state in states if state in {"loading", "error", "success"})
    if not state_summary:
        state_summary = "states"
    return (
        f"Design {screen_name} with {primary_fields}, {main_actions}, "
        f"{state_summary}, and validation and error handling."
    )


def _layout(screen_type: str, fields: list[dict]) -> list[str]:
    if screen_type == "dashboard":
        return ["summary header", "primary metrics row", "filter controls", "results area"]
    if screen_type == "form":
        items = ["title and helper text"]
        if fields:
            items.append("grouped input fields")
        items.extend(["primary action row", "inline validation and error area"])
        return items
    return ["primary content", "supporting actions"]


def _actions(base_flow: str, screen_type: str, fields: list[dict]) -> list[str]:
    if screen_type == "dashboard":
        return ["apply filters", "clear filters", "open item details"]
    actions = ["submit"]
    if fields:
        actions.append("update field state")
    if base_flow in {"login", "signup"}:
        actions.append("show validation errors")
    return _dedupe(actions)


def _states(screen_type: str) -> list[str]:
    states = ["default", "loading", "error", "success"]
    if screen_type in {"dashboard", "list"}:
        states.append("empty")
    return states


def _ux_notes(ba_output: dict, refinement: dict) -> list[str]:
    notes = ["Keep the first interaction path short and obvious."]
    if any(flow in {"login", "signup"} for flow in ba_output.get("flows", [])):
        notes.append("Keep validation messages clear without exposing sensitive auth details.")
    variants = list(refinement.get("refined_variants", [])) or list(refinement.get("variants", []))
    if "phone_otp" in variants or "phone_number" in variants:
        notes.append("Make the phone input and verification step easy to understand before submission.")
    return _dedupe(notes)


def _accessibility_notes(fields: list[dict]) -> list[str]:
    notes = ["Provide clear labels and error text for every interactive element."]
    if fields:
        notes.append("Ensure field validation can be understood without relying on color alone.")
    return notes


def _known_ui_points(ba_output: dict, refinement: dict) -> list[str]:
    items = list(ba_output.get("flows", []))
    items.extend(list(refinement.get("refined_fields", [])))
    items.extend(list(refinement.get("refined_validations", [])))
    return _dedupe([str(item) for item in items if str(item).strip()])[:6]


def _field_type(name: str) -> str:
    lowered = name.lower()
    if "password" in lowered:
        return "password_input"
    if "email" in lowered or "phone" in lowered:
        return "text_input"
    return "text_input"


def _first(values: list[str]) -> str:
    for value in values:
        normalized = str(value).strip()
        if normalized:
            return normalized
    return ""


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in output:
            output.append(normalized)
    return output
