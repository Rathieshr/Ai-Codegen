"""Deterministic domain constraint lookup for prompt enforcement."""

from __future__ import annotations

import json
from pathlib import Path


DOMAIN_KEYWORDS = {
    "auth": ["login", "auth", "password", "credential", "token", "otp"],
    "payment": ["payment", "transaction", "gateway", "invoice", "checkout"],
    "signup": ["signup", "register", "create account", "onboarding"],
    "session": ["session", "token", "refresh", "expiry"],
}


def load_rules() -> dict:
    """Load domain constraints from the local JSON rules file."""

    rules_path = Path(__file__).with_name("rules.json")
    with rules_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def detect_domains(
    query: str,
    flow_steps: list[str],
    linked_flows: list[str] | None = None,
) -> list[str]:
    """Infer relevant domains from query text, flow steps, and linked flow names."""

    rules = load_rules()
    haystack_parts = [query]
    haystack_parts.extend(flow_steps)
    haystack_parts.extend(linked_flows or [])
    haystack = " ".join(haystack_parts).lower()

    domains: list[str] = []
    for domain in rules:
        keywords = DOMAIN_KEYWORDS.get(domain, [])
        if any(keyword in haystack for keyword in keywords):
            domains.append(domain)
    return domains


def get_constraints(
    query: str,
    flow_steps: list[str],
    linked_flows: list[str] | None = None,
) -> list[str]:
    """Return deduplicated constraints for all detected domains."""

    rules = load_rules()
    constraints: list[str] = []
    seen: set[str] = set()

    for domain in detect_domains(query, flow_steps, linked_flows):
        for constraint in rules.get(domain, []):
            if constraint in seen:
                continue
            seen.add(constraint)
            constraints.append(constraint)

    return constraints
