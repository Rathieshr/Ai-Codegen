"""Deterministic flow detection and logic extraction from indexed files."""

from __future__ import annotations

from typing import Any


FLOW_KEYWORDS: dict[str, list[str]] = {
    "login": ["login", "auth", "signin", "credential", "password"],
    "payment": ["payment", "pay", "invoice", "billing", "transaction"],
    "session": ["session", "token", "jwt", "refresh"],
    "dashboard": ["dashboard", "home", "overview", "stats"],
    "profile": ["profile", "user", "account", "settings"],
}

FLOW_IDS = {
    "login": "logic_auth_login",
    "payment": "logic_payment",
    "session": "logic_session",
    "dashboard": "logic_dashboard",
    "profile": "logic_profile",
}

FLOW_NAMES = {
    "login": "Login Flow",
    "payment": "Payment Flow",
    "session": "Session Flow",
    "dashboard": "Dashboard Flow",
    "profile": "Profile Flow",
}

ROLE_ORDER = ["ui", "viewmodel", "controller", "api", "service", "data", "unknown"]


def detect_flow_from_file(file_path: str, summary: str) -> str | None:
    """Return the strongest flow match for a file path and summary."""

    text = f"{file_path} {summary}".lower()
    best_flow: str | None = None
    best_score = 0
    for flow, keywords in FLOW_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in text)
        if score > best_score:
            best_flow = flow
            best_score = score
    return best_flow if best_score > 0 else None


def detect_file_role(file_path: str) -> str:
    """Detect a file's architectural role from its path/name."""

    text = file_path.lower()
    if "controller" in text:
        return "controller"
    if "service" in text:
        return "service"
    if "repository" in text:
        return "data"
    if "viewmodel" in text:
        return "viewmodel"
    if "screen" in text or "page" in text:
        return "ui"
    if "api" in text:
        return "api"
    return "unknown"


def group_files_by_flow(file_index: list[dict[str, Any]], summaries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Group indexed files into one main flow and role buckets."""

    summary_by_path = {summary.get("path"): summary for summary in summaries}
    groups: dict[str, dict[str, Any]] = {}
    for record in file_index:
        path = record.get("path", "")
        summary = summary_by_path.get(path, {}).get("summary", "")
        flow = detect_flow_from_file(path, summary)
        if not flow:
            continue
        role = detect_file_role(path)
        group = groups.setdefault(flow, {"files": [], "roles": {}})
        if path not in group["files"]:
            group["files"].append(path)
        group["roles"].setdefault(role, [])
        if path not in group["roles"][role]:
            group["roles"][role].append(path)
        record["flow"] = flow
        record["role"] = role
        summary_record = summary_by_path.get(path)
        if summary_record is not None:
            summary_record["flow"] = flow
            summary_record["role"] = role
    return groups


def build_logic_units_from_flows(flow_groups: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Build deterministic logic units from grouped flow files."""

    units: list[dict[str, Any]] = []
    for flow in sorted(flow_groups):
        group = flow_groups[flow]
        roles = group.get("roles", {})
        units.append(
            {
                "id": FLOW_IDS.get(flow, f"logic_{flow}"),
                "name": FLOW_NAMES.get(flow, f"{flow.title()} Flow"),
                "domain": _domain_for_flow(flow),
                "inputs": _inputs_for_flow(flow),
                "outputs": _outputs_for_flow(flow, roles),
                "summary": f"Auto-detected {FLOW_NAMES.get(flow, flow)} from repo files.",
                "steps": _steps_for_roles(flow, roles),
                "files": group.get("files", []),
                "roles": roles,
            }
        )
    return units


def update_logic_store(existing_units: list[dict[str, Any]], generated_units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge generated units into logic_store while preserving manual fields."""

    output: list[dict[str, Any]] = []
    index: dict[str, int] = {}
    for unit in existing_units:
        key = str(unit.get("id") or unit.get("name"))
        index[key] = len(output)
        output.append(unit)
    for generated in generated_units:
        key = str(generated.get("id"))
        if key in index:
            merged = dict(output[index[key]])
            constraints = merged.get("constraints")
            merged.update(generated)
            if constraints:
                merged["constraints"] = constraints
            output[index[key]] = merged
        else:
            index[key] = len(output)
            output.append(generated)
    return output


def enrich_graph_with_flows(graph: dict[str, Any], flow_groups: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Add flow-aware nodes and role chain edges to graph."""

    nodes = graph.setdefault("nodes", [])
    edges = graph.setdefault("edges", [])
    for flow, group in flow_groups.items():
        flow_node = _flow_node_id(flow)
        _append_unique(nodes, {"id": flow_node, "type": "flow"})
        role_nodes: list[str] = []
        for role in ROLE_ORDER:
            files = group.get("roles", {}).get(role, [])
            for file_path in files:
                node_id = _file_node_id(file_path)
                _append_unique(nodes, {"id": node_id, "type": role})
                _append_unique(edges, {"from": node_id, "to": flow_node, "type": "uses"})
                if node_id not in role_nodes:
                    role_nodes.append(node_id)
        for left, right in zip(role_nodes, role_nodes[1:]):
            _append_unique(edges, {"from": left, "to": right, "type": "invokes"})
    return graph


def extract_and_update_logic(
    file_index: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    existing_logic: list[dict[str, Any]],
    graph: dict[str, Any],
    affected_files: list[str] | None = None,
) -> dict[str, Any]:
    """Group flows and update logic/graph, optionally scoped to affected flows."""

    flow_groups = group_files_by_flow(file_index, summaries)
    if affected_files:
        affected_flows = {
            flow
            for flow, group in flow_groups.items()
            if set(group.get("files", [])).intersection(affected_files)
        }
        flow_groups = {flow: group for flow, group in flow_groups.items() if flow in affected_flows}
    generated = build_logic_units_from_flows(flow_groups)
    return {
        "flow_groups": flow_groups,
        "logic_store": update_logic_store(existing_logic, generated),
        "graph": enrich_graph_with_flows(graph, flow_groups),
        "detected_flows": sorted(flow_groups),
    }


def _steps_for_roles(flow: str, roles: dict[str, list[str]]) -> list[str]:
    label = FLOW_NAMES.get(flow, flow.title())
    steps: list[str] = []
    if roles.get("ui"):
        steps.append(f"UI triggers {label.lower()}.")
    if roles.get("viewmodel"):
        steps.append(f"ViewModel coordinates {label.lower()} state.")
    if roles.get("controller") or roles.get("api"):
        steps.append(f"Controller/API handles {label.lower()} request.")
    if roles.get("service"):
        steps.append(f"Service executes {label.lower()} business rules.")
    if roles.get("data"):
        steps.append(f"Data layer persists {label.lower()} state.")
    if not steps:
        steps.append(f"Files participate in {label.lower()}.")
    if flow == "login" and any(role in roles for role in ("service", "controller", "api")):
        steps.append("Session/token is created or reused after validation.")
    return steps


def _inputs_for_flow(flow: str) -> list[str]:
    if flow == "login":
        return ["credentials", "password"]
    if flow == "payment":
        return ["payment details", "transaction"]
    if flow == "session":
        return ["token", "refresh request"]
    return []


def _outputs_for_flow(flow: str, roles: dict[str, list[str]]) -> list[str]:
    if flow in {"login", "session"}:
        return ["session/token"]
    if flow == "payment":
        return ["transaction status"]
    if roles.get("ui"):
        return ["screen state"]
    return []


def _domain_for_flow(flow: str) -> str:
    if flow in {"login", "session"}:
        return "auth"
    return flow


def _flow_node_id(flow: str) -> str:
    return f"{flow.title().replace('_', '')}Flow"


def _file_node_id(file_path: str) -> str:
    return file_path.replace("/", "::").replace(".", "_")


def _append_unique(values: list[dict[str, Any]], value: dict[str, Any]) -> None:
    if value not in values:
        values.append(value)
