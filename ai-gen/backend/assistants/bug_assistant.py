"""Bug work item assistant for ai-gen pipeline.

Routes when:
  a) work_item_type == 'Bug'  (explicit ADO type)
  b) critic stage produces a blocking finding tagged as a bug candidate

Produces a structured bug artifact with:
  - reproduction_steps     (numbered list)
  - expected_behaviour     (what should happen)
  - actual_behaviour       (what is happening / what was reported)
  - root_cause_hypothesis  (best guess; can be 'Unknown')
  - severity               (critical / high / medium / low)
  - affected_area          (inferred from title + description)
  - description            (ADO-ready HTML block)
  - acceptance_criteria    (what "fixed" means — testable)
  - open_questions         (list of strings blocking root cause clarity)
  - suggested_labels       (tags to apply in ADO)
"""

from __future__ import annotations

import re
from typing import Any


# ── Severity heuristics ────────────────────────────────────────────────────────

_CRITICAL_SIGNALS = frozenset({
    "crash", "data loss", "security", "breach", "injection", "corruption",
    "infinite loop", "unresponsive", "broken", "payment", "authentication",
    "cannot login", "can't login", "500", "503",
})
_HIGH_SIGNALS = frozenset({
    "not working", "fails", "failure", "broken", "blocked", "error",
    "exception", "wrong result", "incorrect", "missing data",
})
_MEDIUM_SIGNALS = frozenset({
    "slow", "performance", "delay", "timeout", "flickering", "layout",
    "ui issue", "display", "overlap", "truncated",
})

# Signals that suggest an open question is needed before root cause is clear
_AMBIGUITY_SIGNALS: list[tuple[str, str]] = [
    (r"\btbd\b", "What is the expected behaviour in this case?"),
    (r"\bunknown\b", "What is the confirmed root cause?"),
    (r"\bintermittent\b", "Can this be reproduced consistently? What are the exact conditions?"),
    (r"\bsometimes\b", "Under what specific conditions does this occur?"),
    (r"\boccasionally\b", "How frequently does this occur and in which environment?"),
    (r"\bnot sure\b", "Please confirm the exact expected outcome before development starts."),
    (r"\bmaybe\b", "Can the reporter confirm the exact reproduction steps?"),
    (r"\bpossibly\b", "Has the root cause been isolated to a specific component?"),
]


def run_bug_assistant(
    work_item: dict,
    critic_findings: list[dict] | None = None,
    review_context: dict | None = None,
    effective_context: dict | None = None,
    question_answers: dict[str, str] | None = None,
) -> dict:
    """Generate a structured bug artifact.

    Parameters
    ----------
    work_item:
        The ADO Bug work item dict.
    critic_findings:
        Blocking/warning findings from the critic stage that triggered this bug.
        If provided (Option C — critic-generated bug), used to populate
        root_cause_hypothesis and suggested dev scope.
    review_context:
        Pipeline review feedback from previous iterations.
    effective_context:
        Built by work_item_context_builder (includes team_comments, epic_context).
    question_answers:
        Dict of {question_text: answer_text} from user responses to open_questions.
    """
    review_context = review_context or {}
    effective_context = effective_context or {}
    critic_findings = critic_findings or []
    question_answers = question_answers or {}

    title = _text(work_item, "title")
    description = _text(work_item, "description")
    acceptance_text = _text(work_item, "acceptanceCriteria", "acceptance_criteria")
    effective_text = str(effective_context.get("effective_text") or "").strip()
    team_comments = effective_context.get("team_comments", [])
    epic_context = effective_context.get("epic_context", {})

    combined = " ".join(
        part for part in [title, description, acceptance_text, effective_text] if part
    ).lower()

    # ── Core fields ──────────────────────────────────────────────────────────
    severity = _infer_severity(combined, critic_findings)
    affected_area = _infer_affected_area(combined, work_item)
    reproduction_steps = _build_reproduction_steps(
        title, description, effective_text, team_comments, question_answers
    )
    expected_behaviour = _infer_expected_behaviour(
        description, acceptance_text, effective_text, epic_context
    )
    actual_behaviour = _infer_actual_behaviour(title, description, effective_text, critic_findings)
    root_cause_hypothesis = _build_root_cause_hypothesis(combined, critic_findings, question_answers)

    # ── AC: what "fixed" means ───────────────────────────────────────────────
    ac_from_ado = _parse_ac_items(acceptance_text)
    ac_generated = _generate_fix_ac(
        title, expected_behaviour, actual_behaviour, reproduction_steps
    )
    acceptance_criteria = _dedupe(ac_from_ado + ac_generated)

    # ── Open questions ───────────────────────────────────────────────────────
    open_questions = _detect_open_questions(combined, question_answers, critic_findings)

    # ── ADO-ready description HTML ───────────────────────────────────────────
    ado_description = _build_ado_description(
        title=title,
        reproduction_steps=reproduction_steps,
        expected_behaviour=expected_behaviour,
        actual_behaviour=actual_behaviour,
        root_cause_hypothesis=root_cause_hypothesis,
        affected_area=affected_area,
        severity=severity,
        epic_context=epic_context,
    )

    # ── Labels ───────────────────────────────────────────────────────────────
    suggested_labels = _suggest_labels(severity, affected_area, critic_findings)

    return {
        "assistant": "bug",
        "title": title,
        "severity": severity,
        "affected_area": affected_area,
        "reproduction_steps": reproduction_steps,
        "expected_behaviour": expected_behaviour,
        "actual_behaviour": actual_behaviour,
        "root_cause_hypothesis": root_cause_hypothesis,
        "acceptance_criteria": acceptance_criteria,
        "open_questions": open_questions,
        "description": ado_description,
        "suggested_labels": suggested_labels,
        "from_critic": bool(critic_findings),
        "react": {
            "reason": {
                "known": [title, f"severity:{severity}", f"area:{affected_area}"],
                "missing": open_questions[:3],
                "goal": "Define reproduction steps, expected vs actual behaviour, and a clear fix definition.",
            },
            "act": {
                "severity": severity,
                "open_question_count": len(open_questions),
                "ac_count": len(acceptance_criteria),
            },
            "observe": {
                "from_critic": bool(critic_findings),
                "affected_area": affected_area,
            },
            "decision": "awaiting_input" if open_questions else "ready_for_approval",
        },
    }


# ── Private helpers ────────────────────────────────────────────────────────────

def _text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _infer_severity(combined: str, critic_findings: list[dict]) -> str:
    """Determine severity from text signals and critic findings."""
    blocking = any(f.get("severity") == "blocking" for f in critic_findings)
    if blocking:
        return "critical"
    for signal in _CRITICAL_SIGNALS:
        if signal in combined:
            return "critical"
    for signal in _HIGH_SIGNALS:
        if signal in combined:
            return "high"
    for signal in _MEDIUM_SIGNALS:
        if signal in combined:
            return "medium"
    return "medium"


def _infer_affected_area(combined: str, work_item: dict) -> str:
    """Guess the affected feature area from tags and text."""
    tags = work_item.get("tags", [])
    if isinstance(tags, list) and tags:
        return str(tags[0]).strip()
    # Fall back to first noun-ish phrase in title
    title = _text(work_item, "title")
    words = [w for w in title.split() if len(w) > 3 and w[0].isupper()]
    return " ".join(words[:3]) if words else "Unknown"


def _build_reproduction_steps(
    title: str,
    description: str,
    effective_text: str,
    team_comments: list[dict],
    question_answers: dict[str, str],
) -> list[str]:
    """Extract or generate numbered reproduction steps."""
    # Check if description already has steps
    if description:
        numbered = re.findall(r"(?:^|\n)\s*\d+\.\s+(.+)", description)
        bullets = re.findall(r"(?:^|\n)\s*[-*]\s+(.+)", description)
        existing = [s.strip() for s in (numbered or bullets) if s.strip()]
        if len(existing) >= 2:
            return existing[:8]

    # Build from available context
    steps: list[str] = []

    # Add any reproduction detail from team comments
    for comment in team_comments[:3]:
        body = str(comment.get("body") or comment.get("text") or "").strip()
        if body and len(body) > 20:
            steps.append(f"Reported: {body[:120]}")

    # Add answers to reproduction-related questions
    for question, answer in question_answers.items():
        if answer.strip():
            steps.append(f"{answer.strip()[:120]}")

    if not steps:
        # Generic steps based on title
        action = title.lower().replace("bug:", "").replace("fix:", "").strip()
        steps = [
            f"Navigate to the feature/area related to: {action[:80]}",
            "Perform the action that triggers the reported issue.",
            "Observe the error or unexpected behaviour.",
        ]

    return steps


def _infer_expected_behaviour(
    description: str,
    acceptance_text: str,
    effective_text: str,
    epic_context: dict,
) -> str:
    """Extract expected behaviour from AC or description."""
    # Acceptance criteria is the best source
    if acceptance_text and len(acceptance_text) > 15:
        return acceptance_text.split("\n")[0][:200].strip()
    # Pull from epic context
    epic_ac = str(epic_context.get("acceptance_criteria") or "").strip()
    if epic_ac:
        return f"Per Epic AC: {epic_ac[:160]}"
    # First sentence of description
    if description:
        first = description.split(".")[0].strip()
        if len(first) > 10:
            return first[:200]
    return "The system should behave as per the original acceptance criteria."


def _infer_actual_behaviour(
    title: str,
    description: str,
    effective_text: str,
    critic_findings: list[dict],
) -> str:
    """Extract actual (broken) behaviour from available context."""
    # Critic findings are the most precise source
    for finding in critic_findings:
        msg = str(finding.get("message") or "").strip()
        if msg and len(msg) > 15:
            return msg[:200]
    # Second paragraph of description
    paras = [p.strip() for p in description.split("\n\n") if p.strip()]
    if len(paras) >= 2:
        return paras[1][:200]
    return f"Reported issue: {title[:150]}"


def _build_root_cause_hypothesis(
    combined: str,
    critic_findings: list[dict],
    question_answers: dict[str, str],
) -> str:
    """Build a root cause hypothesis from findings and answers."""
    hypotheses: list[str] = []
    for finding in critic_findings:
        if finding.get("type") in {"risk", "conflict", "missing_critical_field"}:
            hypotheses.append(str(finding.get("message") or ""))
    for answer in question_answers.values():
        if answer.strip():
            hypotheses.append(answer.strip()[:120])
    if not hypotheses:
        return "Unknown — reproduction steps needed to isolate root cause."
    return " | ".join(h for h in hypotheses[:3] if h)


def _parse_ac_items(ac_text: str) -> list[str]:
    if not ac_text:
        return []
    numbered = re.findall(r"(?:^|\n)\s*\d+\.\s+(.+)", ac_text)
    bullets = re.findall(r"(?:^|\n)\s*[-*]\s+(.+)", ac_text)
    items = [s.strip() for s in (numbered or bullets or ac_text.split("\n")) if s.strip()]
    return [item for item in items if len(item) > 5][:8]


def _generate_fix_ac(
    title: str,
    expected: str,
    actual: str,
    reproduction_steps: list[str],
) -> list[str]:
    """Generate acceptance criteria that describe when the bug is fixed."""
    ac: list[str] = []
    if expected and expected != actual:
        ac.append(f"The system correctly produces: {expected[:120]}")
    if reproduction_steps:
        ac.append(f"Following the reproduction steps no longer results in the reported failure.")
    ac.append(f"Regression test passes: '{title[:80]}'")
    return ac


def _detect_open_questions(
    combined: str,
    question_answers: dict[str, str],
    critic_findings: list[dict],
) -> list[str]:
    """Surface ambiguity as open questions, filtering already-answered ones."""
    questions: list[str] = []
    for pattern, question in _AMBIGUITY_SIGNALS:
        if re.search(pattern, combined, re.IGNORECASE):
            if question not in question_answers:
                questions.append(question)
    # Unresolved critic findings also become questions
    for finding in critic_findings:
        if finding.get("type") == "ambiguity":
            q = f"Clarify: {str(finding.get('message', ''))[:120]}"
            if q not in question_answers and q not in questions:
                questions.append(q)
    return _dedupe(questions)[:5]


def _suggest_labels(
    severity: str,
    affected_area: str,
    critic_findings: list[dict],
) -> list[str]:
    labels = [f"severity:{severity}"]
    if affected_area and affected_area != "Unknown":
        labels.append(f"area:{affected_area.lower()}")
    types = {f.get("type") for f in critic_findings if f.get("type")}
    if "risk" in types or "risk_matrix_match" in types:
        labels.append("security-review")
    return labels


def _build_ado_description(
    title: str,
    reproduction_steps: list[str],
    expected_behaviour: str,
    actual_behaviour: str,
    root_cause_hypothesis: str,
    affected_area: str,
    severity: str,
    epic_context: dict,
) -> str:
    """Build an ADO-ready HTML description."""
    html_steps = "".join(f"<li>{step}</li>" for step in reproduction_steps)
    epic_title = str(epic_context.get("title") or "").strip()
    epic_section = (
        f"<p><strong>Parent Epic:</strong> {epic_title}</p>" if epic_title else ""
    )
    return (
        f"<h3>{title}</h3>"
        f"<p><strong>Severity:</strong> {severity.upper()} | "
        f"<strong>Area:</strong> {affected_area}</p>"
        f"{epic_section}"
        f"<h4>Reproduction Steps</h4><ol>{html_steps}</ol>"
        f"<h4>Expected Behaviour</h4><p>{expected_behaviour}</p>"
        f"<h4>Actual Behaviour</h4><p>{actual_behaviour}</p>"
        f"<h4>Root Cause Hypothesis</h4><p>{root_cause_hypothesis}</p>"
        f"<p><em>Generated by ai-gen bug assistant.</em></p>"
    )


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        key = v.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(v.strip())
    return out
