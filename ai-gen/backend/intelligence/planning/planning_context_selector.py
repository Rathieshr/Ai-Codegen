from __future__ import annotations

import re
from typing import Any

from backend.intelligence.capability.capability_rules import CORE_CAPABILITIES, REJECTION_RULES

from .planning_context import PlanningReference, RejectedPlanningContext

AUTH_TOKENS = {"login", "auth", "authentication", "session", "token", "password", "otp", "sign in"}


class PlanningContextSelector:
    def select(
        self,
        work_item: dict[str, Any],
        parent_work_item: dict[str, Any] | None,
        intent_model: dict[str, Any],
        capability_context: dict[str, Any],
        project_profile: dict[str, Any],
        repository_snapshot: dict[str, Any],
        knowledge_registry: dict[str, Any],
    ) -> dict[str, list[Any]]:
        corpus = _corpus(work_item, parent_work_item, intent_model)
        acceptance_corpus = _acceptance_corpus(work_item)
        selected_capabilities = self._capabilities(capability_context, corpus)
        selected_modules = self._context_refs(
            capability_context.get("relevantModules") or [],
            "module",
            corpus,
            acceptance_corpus,
            repository_snapshot,
            knowledge_registry,
        )
        selected_flows = self._context_refs(
            capability_context.get("relevantFlows") or [],
            "flow",
            corpus,
            acceptance_corpus,
            repository_snapshot,
            knowledge_registry,
        )
        raw_corpus = _raw_corpus(work_item, parent_work_item)
        if not any(token in raw_corpus for token in AUTH_TOKENS):
            selected_flows = [flow for flow in selected_flows if flow.name.lower() != "token refresh"]
        selected_applications = self._applications(
            capability_context.get("relevantApplications") or [], project_profile, corpus, acceptance_corpus
        )
        selected_dependencies = self._dependencies(
            capability_context.get("relevantDependencies") or [], repository_snapshot, knowledge_registry, corpus, acceptance_corpus
        )
        selected_standards = self._standards(knowledge_registry, corpus, acceptance_corpus)
        rejected = self._rejections(
            corpus,
            selected_capabilities,
            selected_modules,
            selected_flows,
            capability_context,
            project_profile,
            knowledge_registry,
            repository_snapshot,
        )
        return {
            "selected_capabilities": selected_capabilities,
            "selected_modules": selected_modules,
            "selected_flows": selected_flows,
            "selected_applications": selected_applications,
            "selected_dependencies": selected_dependencies,
            "selected_standards": selected_standards,
            "rejected_context": rejected,
            "intent_keywords": _keywords(intent_model, corpus),
        }

    def _capabilities(self, capability_context: dict[str, Any], corpus: str) -> list[PlanningReference]:
        raw = []
        primary = capability_context.get("primaryCapability")
        if isinstance(primary, dict):
            raw.append(primary)
        raw.extend([item for item in capability_context.get("secondaryCapabilities") or [] if isinstance(item, dict)])
        refs: list[PlanningReference] = []
        for item in raw:
            name = _clean(item.get("name"))
            if not name or _blocked(name, corpus):
                continue
            refs.append(_ref(item, "capability", "capability_engine", "Capability selected because it is supported by parent/work item intent."))
        return _dedupe_refs(refs)[:8]

    def _context_refs(
        self,
        raw: list[dict[str, Any]],
        ref_type: str,
        corpus: str,
        acceptance_corpus: str,
        repository_snapshot: dict[str, Any],
        knowledge_registry: dict[str, Any],
    ) -> list[PlanningReference]:
        candidates = [item for item in raw if isinstance(item, dict)]
        candidates.extend(_repository_named_items(repository_snapshot, ref_type))
        refs: list[PlanningReference] = []
        for item in candidates:
            name = _clean(item.get("name") or item.get("path") or item)
            if not name or _blocked(name, corpus):
                continue
            evidence = _evidence(name, item, repository_snapshot, knowledge_registry, corpus, acceptance_corpus)
            if not evidence and ref_type != "dependency":
                continue
            reason = f"{ref_type.title()} selected from capability context with repository or knowledge evidence."
            if acceptance_corpus and _mentions(name, acceptance_corpus):
                reason = f"{ref_type.title()} selected because Story acceptance criteria mention or imply it."
            source = "repository" if _repository_has(name, repository_snapshot) else _source(item)
            refs.append(
                PlanningReference(
                    name=name,
                    type=ref_type,
                    confidence=max(float(item.get("confidence", 0.58) or 0.58), 0.7 if evidence else 0.5),
                    source=source,
                    reason=reason,
                    evidence=evidence,
                )
            )
        return _dedupe_refs(refs)[:8]

    def _applications(self, raw: list[dict[str, Any]], project_profile: dict[str, Any], corpus: str, acceptance_corpus: str) -> list[PlanningReference]:
        refs: list[PlanningReference] = []
        for item in raw:
            name = _clean(item.get("name"))
            app_type = _clean(item.get("type")) or "application"
            if not name or _blocked(name, corpus):
                continue
            if not (_mentions(name, corpus) or _mentions(app_type, corpus) or _mentions(name, acceptance_corpus) or _app_supported(name, app_type, corpus)):
                continue
            refs.append(PlanningReference(name, "application", float(item.get("confidence", 0.6) or 0.6), _source(item), "Application selected only because it is supported by parent intent or selected capability evidence.", [app_type] if app_type else []))
        return _dedupe_refs(refs)[:5]

    def _dependencies(self, raw: list[dict[str, Any]], repository_snapshot: dict[str, Any], knowledge_registry: dict[str, Any], corpus: str, acceptance_corpus: str) -> list[PlanningReference]:
        refs: list[PlanningReference] = []
        for item in raw:
            name = _clean(item.get("name"))
            if not name or _blocked(name, corpus):
                continue
            if not (_mentions(name, corpus) or any(_mentions(part, corpus + " " + acceptance_corpus) for part in name.split())):
                continue
            refs.append(_ref(item, "dependency", _source(item), "Dependency selected from capability, repository, or knowledge evidence and filtered by intent."))
        return _dedupe_refs(refs)[:6]

    def _standards(self, knowledge_registry: dict[str, Any], corpus: str, acceptance_corpus: str) -> list[PlanningReference]:
        standards = knowledge_registry.get("standards") or []
        refs = [
            PlanningReference(_clean(item), "standard", 0.64, "knowledge_registry", "Engineering/planning standard selected to constrain generation scope.", [])
            for item in standards
            if _clean(item)
        ]
        if acceptance_corpus and not any(ref.name == "Acceptance criteria traceability" for ref in refs):
            refs.append(PlanningReference("Acceptance criteria traceability", "standard", 0.72, "knowledge_registry", "Story/Task planning must trace work to acceptance criteria.", []))
        if not refs:
            refs.append(PlanningReference("No broad context leakage", "standard", 0.7, "knowledge_registry", "Planning context must be the only generation input.", []))
        return _dedupe_refs(refs)[:6]

    def _rejections(
        self,
        corpus: str,
        selected_capabilities: list[PlanningReference],
        selected_modules: list[PlanningReference],
        selected_flows: list[PlanningReference],
        capability_context: dict[str, Any],
        project_profile: dict[str, Any],
        knowledge_registry: dict[str, Any],
        repository_snapshot: dict[str, Any],
    ) -> list[RejectedPlanningContext]:
        selected = {ref.name.lower() for ref in [*selected_capabilities, *selected_modules, *selected_flows]}
        rejected: list[RejectedPlanningContext] = []
        for item in capability_context.get("rejectedCapabilities") or []:
            name = _clean(item.get("name"))
            if name:
                rejected.append(RejectedPlanningContext(name, "capability", str(item.get("reason") or "Rejected by capability engine.")))
        for capability, rule in REJECTION_RULES.items():
            if capability.lower() not in selected and not any(req in corpus for req in rule.get("required", [])):
                rejected.append(RejectedPlanningContext(capability, "capability", str(rule.get("reason") or "Rejected by lineage relevance rules.")))
        known_context = f"{_all_registry_names(knowledge_registry)} {_all_names(knowledge_registry, repository_snapshot)}".lower()
        raw_corpus = _raw_corpus_from_text(corpus)
        if "token refresh" not in selected and "token refresh" in known_context and not any(token in raw_corpus for token in AUTH_TOKENS):
            rejected.append(RejectedPlanningContext("Token Refresh", "flow", "Parent intent does not mention authentication, login, token, session, OTP, or password behavior."))
        if "firmware" not in selected and not any(token in corpus for token in ["firmware", "version", "rollout", "upgrade", "rollback", "compliance", "device update"]):
            rejected.append(RejectedPlanningContext("Firmware", "module", "Parent intent does not mention firmware, version, rollout, upgrade, rollback, compliance, or device update."))
            rejected.append(RejectedPlanningContext("Firmware Rollout", "flow", "Parent intent does not mention firmware, version, rollout, upgrade, rollback, compliance, or device update."))
        for app in project_profile.get("applications") or []:
            name = _clean(app.get("name") if isinstance(app, dict) else app)
            app_type = _clean(app.get("type") if isinstance(app, dict) else "")
            if name and name.lower() not in selected and _blocked(f"{name} {app_type}", corpus):
                rejected.append(RejectedPlanningContext(name, "application", f"Parent intent does not support {name}."))
        return _dedupe_rejected(rejected)


def _ref(item: dict[str, Any], ref_type: str, source: str, reason: str) -> PlanningReference:
    src = source if source in {"intent", "repository", "knowledge_registry", "capability_engine", "parent"} else "capability_engine"
    return PlanningReference(_clean(item.get("name")), ref_type, float(item.get("confidence", 0.6) or 0.6), src, reason, [str(x) for x in item.get("evidence", [])])


def _corpus(work_item: dict[str, Any], parent_work_item: dict[str, Any] | None, intent_model: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in [parent_work_item or {}, work_item or {}]:
        parts.extend([_clean(item.get("title")), _clean(item.get("description")), _clean(item.get("acceptanceCriteria") or item.get("acceptance_criteria"))])
    for key in ["businessGoal", "userGoal", "primaryCapability", "secondaryCapabilities", "businessKeywords", "technicalKeywords", "actions", "entities", "inferredModules", "inferredFlows"]:
        parts.append(_clean(intent_model.get(key)))
    return " ".join(parts).lower()


def _raw_corpus(work_item: dict[str, Any], parent_work_item: dict[str, Any] | None) -> str:
    parts: list[str] = []
    for item in [parent_work_item or {}, work_item or {}]:
        parts.extend([_clean(item.get("title")), _clean(item.get("description")), _clean(item.get("acceptanceCriteria") or item.get("acceptance_criteria"))])
    return " ".join(parts).lower()


def _raw_corpus_from_text(corpus: str) -> str:
    # Intent/capability models may add inferred labels such as "Token Refresh".
    # Rejection rules must look for explicit auth/session intent, not labels inferred from a generic "refresh" verb.
    return corpus.replace("token refresh", "").replace("authentication", "")


def _acceptance_corpus(work_item: dict[str, Any]) -> str:
    return _clean(work_item.get("acceptanceCriteria") or work_item.get("acceptance_criteria") or work_item.get("acceptance_areas")).lower()


def _keywords(intent_model: dict[str, Any], corpus: str) -> list[str]:
    explicit = []
    for key in ["businessKeywords", "technicalKeywords", "actions", "entities"]:
        value = intent_model.get(key)
        if isinstance(value, list):
            explicit.extend(_clean(item).lower() for item in value if _clean(item))
    common = [word for word in re.findall(r"[a-z][a-z0-9]{3,}", corpus) if word not in {"with", "from", "that", "this", "work", "item"}]
    return _unique([*explicit, *common])[:30]


def _repository_named_items(snapshot: dict[str, Any], ref_type: str) -> list[dict[str, Any]]:
    key = {"module": "modules", "flow": "flows", "dependency": "dependencies"}.get(ref_type, "")
    items = snapshot.get(key) or []
    output = []
    for item in items:
        if isinstance(item, dict):
            output.append(item)
        elif isinstance(item, str):
            output.append({"name": item, "confidence": 0.62, "source": "repository"})
    return output


def _evidence(name: str, item: dict[str, Any], repository_snapshot: dict[str, Any], knowledge_registry: dict[str, Any], corpus: str, acceptance_corpus: str) -> list[str]:
    evidence = [str(x) for x in item.get("evidence", []) if str(x).strip()]
    keywords = [str(x).lower() for x in item.get("keywords", []) if str(x).strip()]
    if _mentions(name, corpus) or _mentions(name, acceptance_corpus):
        evidence.append(name)
    evidence.extend([kw for kw in keywords if kw in corpus or kw in acceptance_corpus])
    if item.get("path"):
        evidence.append(str(item["path"]))
    if _registry_has(name, knowledge_registry):
        evidence.append("knowledge_registry")
    if _repository_has(name, repository_snapshot):
        evidence.append("repository")
    return _unique(evidence)


def _blocked(name: str, corpus: str) -> bool:
    text = name.lower()
    if "firmware" in text and not any(token in corpus for token in ["firmware", "version", "rollout", "upgrade", "rollback", "compliance", "device update"]):
        return True
    if ("token refresh" in text or text.strip() == "authentication") and not any(token in corpus for token in AUTH_TOKENS):
        return True
    return False


def _app_supported(name: str, app_type: str, corpus: str) -> bool:
    text = f"{name} {app_type}".lower()
    if "dashboard" in text and any(token in corpus for token in ["dashboard", "monitor", "operational"]):
        return True
    if "analytics" in text and any(token in corpus for token in ["analytics", "kpi", "metric", "trend"]):
        return True
    if "auth" in text and any(token in corpus for token in AUTH_TOKENS):
        return True
    return False


def _mentions(name: str, corpus: str) -> bool:
    if not name or not corpus:
        return False
    normalized = name.lower()
    if normalized in corpus:
        return True
    return any(part in corpus for part in re.findall(r"[a-z][a-z0-9]{3,}", normalized))


def _registry_has(name: str, registry: dict[str, Any]) -> bool:
    return name.lower() in _all_registry_names(registry).lower()


def _repository_has(name: str, snapshot: dict[str, Any]) -> bool:
    return name.lower() in _all_names({}, snapshot).lower()


def _all_registry_names(registry: dict[str, Any]) -> str:
    return _clean([*(registry.get("modules") or []), *(registry.get("flows") or []), *(registry.get("dependencies") or []), *(registry.get("standards") or [])])


def _all_names(registry: dict[str, Any], snapshot: dict[str, Any]) -> str:
    values = [_all_registry_names(registry)]
    for key in ["modules", "flows", "dependencies", "rankedFiles"]:
        for item in snapshot.get(key) or []:
            if isinstance(item, dict):
                values.append(_clean([item.get("name"), item.get("path"), item.get("keywords")]))
            else:
                values.append(_clean(item))
    return " ".join(values)


def _source(item: dict[str, Any]) -> str:
    source = str(item.get("source") or "capability_engine")
    if source == "fallback_rules":
        return "capability_engine"
    return source if source in {"intent", "repository", "knowledge_registry", "capability_engine", "parent"} else "capability_engine"


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(_clean(item) for item in value if _clean(item))
    return " ".join(str(value).strip().split())


def _unique(values: list[str]) -> list[str]:
    output = []
    seen = set()
    for value in values:
        cleaned = _clean(value)
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            output.append(cleaned)
    return output


def _dedupe_refs(refs: list[PlanningReference]) -> list[PlanningReference]:
    output: list[PlanningReference] = []
    seen: set[str] = set()
    for ref in sorted(refs, key=lambda item: item.confidence, reverse=True):
        key = f"{ref.type}:{ref.name.lower()}"
        if key not in seen:
            seen.add(key)
            output.append(ref)
    return output


def _dedupe_rejected(items: list[RejectedPlanningContext]) -> list[RejectedPlanningContext]:
    output: list[RejectedPlanningContext] = []
    seen: set[str] = set()
    for item in items:
        key = f"{item.type}:{item.name.lower()}"
        if key not in seen:
            seen.add(key)
            output.append(item)
    return output
