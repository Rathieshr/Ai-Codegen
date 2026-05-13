"""Test-planning stage for the structured assistant pipeline."""

from __future__ import annotations


def run_test_assistant(ba_output: dict, dev_output: dict, ui_output: dict | None = None) -> dict:
    """Generate structured test ideas from approved BA and dev outputs."""

    acceptance = list(ba_output.get("acceptance_criteria", []))
    fields = [field.get("name", "") for field in (ui_output or {}).get("fields", []) if field.get("name")]
    flow = dev_output.get("flow") or _first(ba_output.get("flows", [])) or "feature"
    variants = list(dev_output.get("variants", [])) or list(ba_output.get("variants", []))
    test_cases = _dedupe_test_cases(
        [
            _test_case(
                title=f"{flow.title()} happy path works",
                case_type="positive",
                steps=[
                    f"Prepare the {flow} entry point with valid data.",
                    "Submit the primary action.",
                    "Verify the expected success outcome.",
                ],
                expected="The user completes the intended flow successfully.",
                linked=acceptance[:1],
            ),
            _test_case(
                title=f"{flow.title()} rejects invalid input",
                case_type="negative",
                steps=[
                    "Use invalid or incomplete input.",
                    "Submit the primary action.",
                    "Verify the validation or failure message.",
                ],
                expected="The change blocks invalid input without breaking the existing safety rules.",
                linked=acceptance[:1],
            ),
            _edge_case(flow, fields, acceptance, variants),
            _acceptance_case(acceptance, flow),
        ]
    )
    reason = {
        "known": _dedupe([flow] + acceptance[:2] + fields[:2]),
        "missing": list(ba_output.get("unknowns", []))[:4],
        "goal": "Cover the approved scope with positive, negative, edge, and acceptance tests.",
    }
    act = {
        "test_case_count": len(test_cases),
        "coverage": ["positive", "negative", "edge", "acceptance"],
    }
    observe = {
        "ui_context_used": bool(ui_output and not ui_output.get("skippable")),
        "field_count": len(fields),
    }
    return {
        "assistant": "test",
        "test_cases": test_cases,
        "coverage_notes": _coverage_notes(fields, acceptance),
        "unknowns": list(ba_output.get("unknowns", []))[:4],
        "react": {
            "reason": reason,
            "act": act,
            "observe": observe,
            "decision": "ready_for_approval" if test_cases else "needs_revision",
        },
    }


def _test_case(title: str, case_type: str, steps: list[str], expected: str, linked: list[str]) -> dict:
    return {
        "title": title,
        "type": case_type,
        "steps": steps,
        "expected": expected,
        "linked_acceptance_criteria": linked,
    }


def _edge_case(flow: str, fields: list[str], acceptance: list[str], variants: list[str]) -> dict:
    focus = fields[0] if fields else "input"
    if "phone_otp" in variants and "otp" in fields:
        focus = "otp"
    return _test_case(
        title=f"{flow.title()} handles boundary values for {focus}",
        case_type="edge",
        steps=[
            f"Prepare {focus} with a boundary value or maximum allowed length.",
            "Submit the action.",
            "Verify the boundary behavior stays within the expected rules.",
        ],
        expected="Boundary values are handled without unexpected errors or unsafe bypasses.",
        linked=acceptance[:1],
    )


def _acceptance_case(acceptance: list[str], flow: str) -> dict:
    linked = acceptance[:2]
    return _test_case(
        title=f"{flow.title()} meets approved acceptance criteria",
        case_type="acceptance",
        steps=[
            "Walk through the approved user path.",
            "Check each acceptance criterion against the observed behavior.",
        ],
        expected="The approved behavior matches the acceptance criteria.",
        linked=linked,
    )


def _coverage_notes(fields: list[str], acceptance: list[str]) -> list[str]:
    notes = ["Review both successful and failure paths before sign-off."]
    if fields:
        notes.append(f"Include validation coverage for: {', '.join(fields[:3])}.")
    if "otp" in fields:
        notes.append("Include OTP retry, expiry, and invalid-code coverage.")
    if not acceptance:
        notes.append("Acceptance criteria are thin, so manual review should confirm the intended user outcome.")
    return notes


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in output:
            output.append(normalized)
    return output


def _dedupe_test_cases(cases: list[dict]) -> list[dict]:
    seen: set[str] = set()
    output: list[dict] = []
    for case in cases:
        title = case.get("title", "").strip()
        if title and title not in seen:
            seen.add(title)
            output.append(case)
    return output


def _first(values: list[str]) -> str:
    for value in values:
        normalized = str(value).strip()
        if normalized:
            return normalized
    return ""
