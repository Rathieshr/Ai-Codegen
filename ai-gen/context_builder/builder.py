"""Business context compression for Codex prompts."""

from __future__ import annotations

from typing import Any

from architecture.graph_store import find_related_nodes
from backend.intent_detector import detect_intent
from backend.importance_scorer import extract_critical, score_flow, trim_flow
from backend.planner import create_plan, summarize_plan
from constraints.constraint_store import get_constraints
from context_builder.flow_composer import compose_flow
from logic_store.store import LogicStore


def compress_flow_steps(flow_steps: list[str]) -> list[str]:
    """Compress ordered flow steps into a readable chain without dropping steps."""

    unique_steps = _dedupe_text_values(flow_steps)
    if not unique_steps:
        return []
    return [" -> ".join(unique_steps)]


def compress_plan(plan: dict[str, Any], max_steps: int | None = None) -> list[str]:
    """Render plan steps as compact single-line guidance."""

    if not plan.get("needs_planning"):
        return []

    steps = plan.get("steps", [])
    if max_steps is not None:
        steps = steps[:max_steps]

    return [
        f"{index}. {step['title']} (risk: {step['risk']})"
        for index, step in enumerate(steps, start=1)
    ]


def compress_constraints(constraints: list[str], bug_fix: bool = False) -> list[str]:
    """Deduplicate and merge common domain constraints into concise rules."""

    compressed: list[str] = []
    for constraint in constraints:
        normalized = constraint.lower()
        if "credential validation" in normalized:
            _append_once(compressed, "Do not bypass credential validation.")
        elif "reveal whether" in normalized or "email or username exists" in normalized:
            _append_once(compressed, "Keep failed authentication responses generic.")
        elif "token/session" in normalized or "session lifecycle" in normalized or "second session model" in normalized:
            _append_once(compressed, "Reuse existing token/session lifecycle logic.")
        elif "order of critical authentication" in normalized:
            _append_once(compressed, "Preserve critical authentication step order.")
        elif "duplicate user" in normalized:
            _append_once(compressed, "Do not create duplicate user records.")
        elif "password hashing" in normalized:
            _append_once(compressed, "Preserve password hashing and validation rules.")
        elif "payment" in normalized or "transaction" in normalized or "gateway" in normalized:
            _append_once(compressed, constraint)
        elif not bug_fix:
            _append_once(compressed, constraint)

    if bug_fix:
        compressed = select_bug_fix_constraints(compressed)
    return compressed


def select_bug_fix_flow(flow_steps: list[str]) -> list[str]:
    """Select a compact, ordered flow slice for bug-fix prompts."""

    unique_steps = _dedupe_text_values(flow_steps)
    if len(unique_steps) <= 2:
        return unique_steps

    selected: list[str] = []
    for step in unique_steps:
        normalized = step.lower()
        if any(keyword in normalized for keyword in ("validates credentials", "verify credentials", "credential", "password")):
            _append_once(selected, step)
        if len(selected) >= 2:
            break

    if not selected:
        selected = unique_steps[:2]
    elif len(selected) == 1:
        for step in unique_steps:
            normalized = step.lower()
            if step not in selected and any(keyword in normalized for keyword in ("status", "inactive", "session", "token", "auth")):
                _append_once(selected, step)
                break

    ordered = [step for step in unique_steps if step in selected]
    if _has_session_or_token_step(unique_steps) and not _has_session_or_token_step(ordered):
        ordered.append("Reuse existing session/token logic.")
    return ordered[:3]


def select_bug_fix_constraints(constraints: list[str]) -> list[str]:
    """Keep only critical safety constraints for bug-fix prompts."""

    priority_checks = (
        lambda value: "failed authentication" in value.lower() or "generic" in value.lower() or "existence" in value.lower(),
        lambda value: "session" in value.lower() or "token" in value.lower(),
        lambda value: "credential" in value.lower() or "password" in value.lower() or "validation" in value.lower(),
        lambda value: "payment" in value.lower() or "transaction" in value.lower() or "gateway" in value.lower(),
    )
    selected: list[str] = []
    for check in priority_checks:
        for constraint in constraints:
            if check(constraint):
                _append_once(selected, constraint)
                break
        if len(selected) >= 3:
            break
    return selected


def _has_session_or_token_step(steps: list[str]) -> bool:
    return any("session" in step.lower() or "token" in step.lower() for step in steps)


def _append_once(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _dedupe_text_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        normalized = value.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        output.append(normalized)
    return output


class ContextBuilder:
    """Build compact, deduplicated business context in three levels."""

    def __init__(self, logic_store: LogicStore) -> None:
        self.logic_store = logic_store

    def build_prompt(
        self,
        user_query: str,
        max_tokens: int = 900,
        logic_bias_scores: dict[str, float] | None = None,
        bug_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create an optimized prompt with logic flow, metadata, and snippets."""

        intent = detect_intent(user_query)
        matched_logic = self._sort_logic_items_by_bias(
            self._score_logic_items(
                self._dedupe_logic_items(self.logic_store.find_relevant(user_query)),
                intent=intent,
            ),
            logic_bias_scores or {},
        )
        plan = self._create_execution_plan(user_query, intent, matched_logic)
        prompt = self._build_budgeted_prompt(
            user_query=user_query,
            logic_items=matched_logic,
            max_tokens=max_tokens,
            intent=intent,
            plan=plan,
            bug_context=bug_context or {},
        )

        return {
            "optimized_prompt": prompt,
            "matched_logic": [item["id"] for item in matched_logic],
            "token_estimate": self._estimate_tokens(prompt),
            "planning_enabled": bool(plan.get("needs_planning")),
            "plan": plan,
            "plan_summary": summarize_plan(plan),
        }

    def _build_budgeted_prompt(
        self,
        user_query: str,
        logic_items: list[dict[str, Any]],
        max_tokens: int,
        intent: str,
        plan: dict[str, Any],
        bug_context: dict[str, Any] | None = None,
    ) -> str:
        """Build the richest prompt that fits without cutting through sections."""

        variants = self._budget_variants(intent)

        for options in variants:
            prompt = self._format_prompt(
                user_query=user_query,
                logic_items=logic_items,
                include_metadata=options["include_metadata"],
                include_snippets=options["include_snippets"],
                max_flow_steps=options["max_flow_steps"],
                intent=intent,
                plan=plan,
                bug_context=bug_context or {},
            )
            if self._estimate_tokens(prompt) <= max_tokens:
                return prompt

        minimal_prompt = self._format_prompt(
            user_query=user_query,
            logic_items=logic_items,
            include_metadata=False,
            include_snippets=False,
            max_flow_steps=1,
            intent=intent,
            plan=plan,
            bug_context=bug_context or {},
        )
        if self._has_critical_steps(logic_items):
            return self._critical_only_prompt(user_query, logic_items, intent, plan)
        return self._trim_preserving_task(minimal_prompt, max_tokens=max_tokens)

    def _budget_variants(self, intent: str) -> list[dict[str, Any]]:
        """Return compression order, adjusted slightly for user intent."""

        if intent == "feature":
            return [
                {"include_metadata": True, "include_snippets": True, "max_flow_steps": None},
                {"include_metadata": True, "include_snippets": False, "max_flow_steps": None},
                {"include_metadata": False, "include_snippets": False, "max_flow_steps": None},
                {"include_metadata": False, "include_snippets": False, "max_flow_steps": 1},
            ]
        if intent == "refactor":
            return [
                {"include_metadata": True, "include_snippets": True, "max_flow_steps": None},
                {"include_metadata": True, "include_snippets": False, "max_flow_steps": None},
                {"include_metadata": True, "include_snippets": False, "max_flow_steps": 2},
                {"include_metadata": True, "include_snippets": False, "max_flow_steps": 1},
            ]
        if intent == "bug_fix":
            return [
                {"include_metadata": False, "include_snippets": False, "max_flow_steps": 2},
                {"include_metadata": False, "include_snippets": False, "max_flow_steps": 1},
            ]
        return [
            {"include_metadata": True, "include_snippets": True, "max_flow_steps": None},
            {"include_metadata": True, "include_snippets": False, "max_flow_steps": None},
            {"include_metadata": True, "include_snippets": False, "max_flow_steps": 2},
            {"include_metadata": False, "include_snippets": False, "max_flow_steps": 1},
        ]

    def _format_prompt(
        self,
        user_query: str,
        logic_items: list[dict[str, Any]],
        include_metadata: bool,
        include_snippets: bool,
        max_flow_steps: int | None,
        intent: str,
        plan: dict[str, Any],
        bug_context: dict[str, Any],
    ) -> str:
        """Format context so Codex sees task, constraints, and source hints clearly."""

        context_sections = self._context_sections(
            logic_items=logic_items,
            include_metadata=include_metadata,
            include_snippets=include_snippets,
            max_flow_steps=max_flow_steps,
            intent=intent,
        )
        constraints_section = self._constraints_section(user_query, logic_items, intent)
        plan_section = self._plan_section(plan, intent)
        prompt = "\n\n".join(
            section for section in [
                "# Codex Task",
                user_query.strip(),
                f"## Detected Intent: {intent}",
                "# Context",
                context_sections,
                self._bug_context_section(bug_context) if intent == "bug_fix" else "",
                constraints_section,
                plan_section,
                "# Execution Rules",
                "\n".join(
                    [
                        "- Follow plan when present.",
                        "- Prefer minimal safe change.",
                        "- Reuse existing logic.",
                        *(
                            ["- Identify root cause before applying fix."]
                            if intent == "bug_fix"
                            else []
                        ),
                        *(
                            ["- Do not change working auth/session logic unnecessarily."]
                            if intent == "bug_fix"
                            else []
                        ),
                    ]
                ),
            ] if section
        )
        return self._dedupe_lines(prompt).strip()

    def _context_sections(
        self,
        logic_items: list[dict[str, Any]],
        include_metadata: bool,
        include_snippets: bool,
        max_flow_steps: int | None,
        intent: str,
    ) -> str:
        """Return only the context levels requested for the current budget."""

        if not logic_items:
            return "No stored business logic matched. Inspect the codebase first and keep changes minimal."

        sections = [self._flow(logic_items, max_steps=max_flow_steps, intent=intent)]
        critical_steps = self._critical_steps(logic_items, max_steps=2 if intent == "bug_fix" else None, intent=intent)
        if critical_steps:
            sections.append(critical_steps)
        if intent != "bug_fix":
            linked_flows = self._linked_flows(logic_items)
            impacted_components = self._impacted_components(logic_items)
            if linked_flows:
                sections.append(linked_flows)
            if impacted_components:
                sections.append(impacted_components)
        else:
            impacted_components = self._impacted_components(logic_items, max_nodes=2)
            if impacted_components:
                sections.append(impacted_components)
        if include_metadata:
            sections.append(self._level_2_metadata(logic_items))
        if include_snippets and intent != "bug_fix":
            snippets = self._level_3_snippets(logic_items)
            if snippets:
                sections.append(snippets)

        return "\n\n".join(section for section in sections if section)

    def _bug_context_section(self, bug_context: dict[str, Any]) -> str:
        """Render compact repo-aware bug localization hints."""

        sections: list[str] = []
        hotspots = bug_context.get("likely_bug_hotspots") or []
        if hotspots:
            lines = ["## Likely Breakpoints"]
            for hotspot in hotspots[:3]:
                label = f"{hotspot.get('flow', 'unknown')}/{hotspot.get('role', 'unknown')}"
                reasons = ", ".join(hotspot.get("reasons", [])[:3])
                lines.append(f"- {hotspot.get('file')} ({label}): {reasons}")
            sections.append("\n".join(lines))

        related_flows = _dedupe_text_values(bug_context.get("related_flows") or [])
        if related_flows:
            lines = ["## Related Flows"]
            lines.extend(f"- {flow}" for flow in related_flows)
            sections.append("\n".join(lines))

        return "\n\n".join(sections)

    def _level_1_flow(self, logic_items: list[dict[str, Any]]) -> str:
        """Describe each matching business flow at a summary level."""

        lines = ["## Level 1: Business Flow"]
        for item in logic_items:
            lines.append(f"- {item['name']}: {item['summary']}")
        return "\n".join(lines)

    def _flow(
        self,
        logic_items: list[dict[str, Any]],
        max_steps: int | None = None,
        intent: str = "general",
    ) -> str:
        """Render one compressed main flow section."""

        lines = ["## Flow"]
        for item in logic_items:
            scored_steps = item.get("scored_flow", []) if intent == "bug_fix" else trim_flow(item.get("scored_flow", []), max_steps=max_steps)
            flow_steps = [scored_step["step"] for scored_step in scored_steps]
            if intent == "bug_fix":
                flow_steps = select_bug_fix_flow(flow_steps)
            for compressed_step in compress_flow_steps(flow_steps):
                lines.append(f"- {compressed_step}")
        return "\n".join(lines)

    def _critical_steps(
        self,
        logic_items: list[dict[str, Any]],
        max_steps: int | None = None,
        intent: str = "general",
    ) -> str:
        """Render only critical safety steps to avoid repeating the whole flow."""

        steps: list[str] = []
        for item in logic_items:
            critical_steps = extract_critical(item.get("scored_flow", []))
            if intent == "bug_fix":
                critical_values = select_bug_fix_flow([scored_step["step"] for scored_step in critical_steps])
                critical_steps = [
                    scored_step for scored_step in critical_steps
                    if scored_step["step"] in critical_values
                ]
            if max_steps is not None:
                critical_steps = critical_steps[:max_steps]
            for scored_step in critical_steps:
                steps.append(scored_step["step"])

        unique_steps = _dedupe_text_values(steps)
        if not unique_steps:
            return ""

        lines = ["## Critical Steps"]
        lines.extend(f"- {step}" for step in unique_steps)
        return "\n".join(lines)

    def _linked_flows(self, logic_items: list[dict[str, Any]]) -> str:
        """Render flow dependency links when present."""

        lines = ["## Linked Flows"]
        for item in logic_items:
            for link in item.get("linked_flows", []):
                lines.append(f"- {link['from']} → {link['to']}")
        return "\n".join(lines) if len(lines) > 1 else ""

    def _impacted_components(self, logic_items: list[dict[str, Any]], max_nodes: int | None = None) -> str:
        """Render related architecture nodes for matched flows."""

        related_nodes = self._impacted_component_nodes(logic_items)
        if max_nodes is not None:
            related_nodes = related_nodes[:max_nodes]
        if not related_nodes:
            return ""

        lines = ["## Impacted Components"]
        for node in related_nodes:
            lines.append(f"- {node['id']} ({node['type']})")
        return "\n".join(lines)

    def _impacted_component_nodes(self, logic_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return related architecture graph nodes for matched flows."""

        seed_ids = self._architecture_seed_ids(logic_items)
        if not seed_ids:
            return []
        return find_related_nodes(seed_ids, max_depth=2)

    def _architecture_seed_ids(self, logic_items: list[dict[str, Any]]) -> list[str]:
        """Map matched flow names to graph node ids."""

        seed_ids: list[str] = []
        for item in logic_items:
            self._append_architecture_seed(seed_ids, item.get("name", ""))
            self._append_architecture_seed(seed_ids, item.get("id", ""))
        return seed_ids

    def _append_architecture_seed(self, seed_ids: list[str], flow_name: str) -> None:
        """Append a normalized architecture node id once."""

        node_id = self._flow_name_to_node_id(flow_name)
        if node_id and node_id not in seed_ids:
            seed_ids.append(node_id)

    def _flow_name_to_node_id(self, flow_name: str) -> str:
        """Normalize common flow labels into architecture graph ids."""

        explicit_map = {
            "login flow": "LoginFlow",
            "login": "LoginFlow",
            "tokengeneration": "TokenGeneration",
            "token generation": "TokenGeneration",
        }
        normalized = flow_name.strip().lower()
        if normalized in explicit_map:
            return explicit_map[normalized]
        return flow_name.strip().replace(" ", "")

    def _composed_flow(
        self,
        logic_items: list[dict[str, Any]],
        max_steps: int | None = None,
    ) -> str:
        """Render main and injected dependency steps in logical order."""

        lines = ["## Composed Flow"]
        for item in logic_items:
            retained_steps = trim_flow(item.get("scored_flow", []), max_steps=max_steps)
            for scored_step in retained_steps:
                lines.append(f"- {scored_step['step']}")
        return "\n".join(lines)

    def _importance_aware_flow(
        self,
        logic_items: list[dict[str, Any]],
        max_steps: int | None = None,
    ) -> str:
        """Render scored flow steps, trimming low-importance steps first."""

        lines = ["## Importance-Aware Flow"]
        for item in logic_items:
            scored_flow = item.get("scored_flow", [])
            retained_steps = trim_flow(scored_flow, max_steps=max_steps)
            for scored_step in retained_steps:
                label = self._importance_label(scored_step["importance"])
                lines.append(f"- {scored_step['step']} ({label})")
        return "\n".join(lines)

    def _critical_only_prompt(
        self,
        user_query: str,
        logic_items: list[dict[str, Any]],
        intent: str,
        plan: dict[str, Any],
    ) -> str:
        """Build the smallest safe prompt without dropping critical steps."""

        critical_lines = ["## Importance-Aware Flow"]
        for item in logic_items:
            for scored_step in extract_critical(item.get("scored_flow", [])):
                label = self._importance_label(scored_step["importance"])
                critical_lines.append(f"- {scored_step['step']} ({label})")

        sections = [
            "# Codex Task",
            user_query.strip(),
            f"## Detected Intent: {intent}",
            "# Context",
            self._critical_context(logic_items, critical_lines, intent),
            self._constraints_section(user_query, logic_items, intent),
            self._plan_section(plan, intent),
            "# Execution Rules",
            "\n".join(
                [
                    "- Follow plan when present.",
                    "- Prefer minimal safe change.",
                    "- Reuse existing logic.",
                    *(
                        ["- Identify root cause before applying fix."]
                        if intent == "bug_fix"
                        else []
                    ),
                    *(
                        ["- Do not change working auth/session logic unnecessarily."]
                        if intent == "bug_fix"
                        else []
                    ),
                ]
            ),
        ]
        return "\n\n".join(section for section in sections if section)

    def _constraints_section(self, user_query: str, logic_items: list[dict[str, Any]], intent: str) -> str:
        """Render non-negotiable domain constraints when domains are detected."""

        constraints = compress_constraints(
            self._constraints_for_logic(user_query, logic_items),
            bug_fix=intent == "bug_fix",
        )
        if not constraints:
            return ""

        lines = ["## Constraints"]
        lines.extend(f"- {constraint}" for constraint in constraints)
        lines.append(
            "If the requested change conflicts with these constraints, preserve the constraints and make the smallest safe change."
        )
        return "\n".join(lines)

    def _critical_constraints(self, user_query: str, logic_items: list[dict[str, Any]]) -> str:
        """Backward-compatible constraint renderer."""

        return self._constraints_section(user_query, logic_items, intent="general")

    def _constraints_for_logic(self, user_query: str, logic_items: list[dict[str, Any]]) -> list[str]:
        """Return domain constraints inferred from query and composed context."""

        return get_constraints(
            query=user_query,
            flow_steps=self._flow_steps_for_constraints(logic_items),
            linked_flows=self._linked_flow_names(logic_items),
        )

    def _plan_section(self, plan: dict[str, Any], intent: str) -> str:
        """Render the optional planner guidance section."""

        if not plan.get("needs_planning"):
            return ""

        if intent == "bug_fix":
            lines = [
                "## Plan",
                "1. Identify root cause in the relevant flow (risk: medium)",
                "2. Apply the smallest safe fix without breaking constraints (risk: medium)",
            ]
            return "\n".join(lines)

        lines = ["## Plan"]
        lines.extend(compress_plan(plan))
        return "\n".join(lines).strip()

    def _execution_plan(self, plan: dict[str, Any]) -> str:
        """Backward-compatible plan renderer."""

        return self._plan_section(plan, intent="general")

    def _create_execution_plan(
        self,
        user_query: str,
        intent: str,
        logic_items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build planner metadata from the same context used in the prompt."""

        if intent == "bug_fix" and not self._is_broad_bug_fix(user_query, logic_items):
            return {
                "needs_planning": True,
                "plan_type": "bug_fix",
                "steps": [
                    {
                        "id": "step_1",
                        "title": "Identify root cause in the relevant flow",
                        "purpose": "Confirm the bug source before changing auth or session behavior.",
                        "risk": "medium",
                    },
                    {
                        "id": "step_2",
                        "title": "Apply the smallest safe fix without breaking constraints",
                        "purpose": "Fix only the failing behavior while preserving critical safeguards.",
                        "risk": "medium",
                    },
                ],
            }

        return create_plan(
            query=user_query,
            intent=intent,
            linked_flows=self._linked_flow_names(logic_items),
            impacted_components=self._impacted_component_labels(logic_items),
            constraints=self._constraints_for_logic(user_query, logic_items),
        )

    def _is_broad_bug_fix(self, user_query: str, logic_items: list[dict[str, Any]]) -> bool:
        """Return whether a bug fix deserves broader planner context."""

        normalized = user_query.lower()
        if any(keyword in normalized for keyword in ("migration", "migrate", "cross-platform", "architecture", "refactor")):
            return True
        return len(self._linked_flow_names(logic_items)) > 4 or len(self._impacted_component_labels(logic_items)) > 3

    def _flow_steps_for_constraints(self, logic_items: list[dict[str, Any]]) -> list[str]:
        """Collect composed flow steps for domain detection."""

        steps: list[str] = []
        for item in logic_items:
            steps.extend(item.get("composed_steps", []))
        return steps

    def _linked_flow_names(self, logic_items: list[dict[str, Any]]) -> list[str]:
        """Collect linked flow names for domain detection."""

        names: list[str] = []
        for item in logic_items:
            for link in item.get("linked_flows", []):
                names.extend([link.get("from", ""), link.get("to", "")])
        return [name for name in names if name]

    def _critical_context(
        self,
        logic_items: list[dict[str, Any]],
        critical_lines: list[str],
        intent: str,
    ) -> str:
        """Render dependency links with critical-only flow context."""

        linked_flows = self._linked_flows(logic_items)
        impacted_components = self._impacted_components(logic_items)
        sections = [self._flow(logic_items, max_steps=2 if intent == "bug_fix" else 1, intent=intent)]
        if linked_flows:
            sections.append(linked_flows)
        if impacted_components:
            sections.append(impacted_components)
        critical_text = "\n".join(critical_lines).replace("## Importance-Aware Flow", "## Critical Steps")
        sections.append(critical_text)
        return "\n\n".join(sections)

    def _impacted_component_labels(self, logic_items: list[dict[str, Any]]) -> list[str]:
        """Return impacted architecture node labels for planner heuristics."""

        return [
            f"{node['id']} ({node['type']})"
            for node in self._impacted_component_nodes(logic_items)
        ]

    def _level_2_metadata(self, logic_items: list[dict[str, Any]]) -> str:
        """Add services and dependencies that constrain implementation choices."""

        lines = ["## Level 2: Metadata"]
        for item in logic_items:
            services = ", ".join(self._dedupe_values(item.get("services", []))) or "none"
            dependencies = ", ".join(self._dedupe_values(item.get("dependencies", []))) or "none"
            files = ", ".join(self._dedupe_values(item.get("files", []))) or "unknown"
            lines.append(f"- {item['name']}: services={services}; dependencies={dependencies}; files={files}")
        return "\n".join(lines)

    def _level_3_snippets(self, logic_items: list[dict[str, Any]]) -> str:
        """Include minimal snippets only after higher-level context is present."""

        lines = ["## Level 3: Minimal Snippets"]
        seen_snippets: set[str] = set()
        for item in logic_items:
            snippets = item.get("snippets", [])
            for snippet in snippets:
                label = snippet.get("label", "snippet")
                code = snippet.get("code", "").strip()
                if not code or code in seen_snippets:
                    continue
                seen_snippets.add(code)
                lines.append(f"- {item['name']} / {label}:")
                lines.append("```")
                lines.append(code)
                lines.append("```")
        return "\n".join(lines) if len(lines) > 1 else ""

    def _dedupe_logic_items(self, logic_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove duplicate logic records while preserving store order."""

        seen: set[str] = set()
        unique_items: list[dict[str, Any]] = []
        for item in logic_items:
            key = str(item.get("id") or item.get("name") or item)
            if key in seen:
                continue
            seen.add(key)
            unique_items.append(item)
        return unique_items

    def _score_logic_items(
        self,
        logic_items: list[dict[str, Any]],
        intent: str,
    ) -> list[dict[str, Any]]:
        """Attach scored, deduplicated flow steps without mutating store data."""

        scored_items: list[dict[str, Any]] = []
        for item in logic_items:
            copied_item = dict(item)
            composed_steps = compose_flow(
                main_flow=self._dedupe_values(item.get("steps", item.get("flow", []))),
                dependent_flows=item.get("dependent_flows", []),
            )
            copied_item["composed_steps"] = composed_steps
            copied_item["scored_flow"] = score_flow(
                composed_steps,
                intent=intent,
            )
            scored_items.append(copied_item)
        return scored_items

    def _sort_logic_items_by_bias(
        self,
        logic_items: list[dict[str, Any]],
        bias_scores: dict[str, float],
    ) -> list[dict[str, Any]]:
        """Apply optional repo/session bias without replacing keyword matching."""

        if not bias_scores:
            return logic_items
        return sorted(
            logic_items,
            key=lambda item: (
                -max(
                    bias_scores.get(str(item.get("id", "")), 0.0),
                    bias_scores.get(str(item.get("name", "")), 0.0),
                    bias_scores.get(str(item.get("id", "")).lower(), 0.0),
                    bias_scores.get(str(item.get("name", "")).lower(), 0.0),
                ),
                str(item.get("id") or item.get("name") or item),
            ),
        )

    def _importance_label(self, importance: float) -> str:
        """Map numeric importance to a compact prompt label."""

        if importance >= 0.85:
            return "critical"
        if importance >= 0.7:
            return "high"
        if importance >= 0.5:
            return "medium"
        return "low"

    def _has_critical_steps(self, logic_items: list[dict[str, Any]]) -> bool:
        """Return whether any matched flow has critical steps."""

        return any(
            extract_critical(item.get("scored_flow", []))
            for item in logic_items
        )

    def _dedupe_values(self, values: list[str]) -> list[str]:
        """Remove duplicate metadata values without changing their order."""

        seen: set[str] = set()
        unique_values: list[str] = []
        for value in values:
            normalized = value.strip()
            key = normalized.lower()
            if not normalized or key in seen:
                continue
            seen.add(key)
            unique_values.append(normalized)
        return unique_values

    def _dedupe_lines(self, text: str) -> str:
        """Remove repeated non-empty lines while preserving first occurrence order."""

        seen: set[str] = set()
        output: list[str] = []
        for line in text.splitlines():
            key = line.strip()
            if key.startswith("```") or line.startswith(" "):
                output.append(line)
                continue
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            output.append(line)
        return "\n".join(output)

    def _trim_preserving_task(self, prompt: str, max_tokens: int) -> str:
        """Last-resort trim that keeps the task and execution rules readable."""

        words = prompt.split()
        if len(words) <= max_tokens:
            return prompt

        marker = "[Context trimmed to fit token budget.]"
        marker_words = marker.split()
        keep_count = max(max_tokens - len(marker_words), 0)
        kept = words[:keep_count]
        kept.extend(marker_words)
        return " ".join(kept)

    def _estimate_tokens(self, text: str) -> int:
        """Approximate tokens with word count to keep the MVP dependency-free."""

        return len(text.split())
