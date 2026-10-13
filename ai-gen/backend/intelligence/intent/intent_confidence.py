from __future__ import annotations


def score_intent(
    *,
    has_title: bool,
    has_description: bool,
    has_acceptance: bool,
    persona_count: int,
    action_count: int,
    entity_count: int,
    module_count: int,
    flow_count: int,
    reasoning_count: int,
) -> float:
    score = 0.2
    if has_title:
        score += 0.12
    if has_description:
        score += 0.16
    if has_acceptance:
        score += 0.12
    score += min(persona_count, 2) * 0.08
    score += min(action_count, 3) * 0.04
    score += min(entity_count, 4) * 0.035
    score += min(module_count, 3) * 0.04
    score += min(flow_count, 3) * 0.035
    score += min(reasoning_count, 8) * 0.01
    return round(min(score, 0.96), 2)

