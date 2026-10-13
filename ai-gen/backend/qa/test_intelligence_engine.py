"""Engineering test generation from approved execution context."""

from __future__ import annotations

from typing import Any

from .qa_validation_rules import TEST_CATEGORIES, category_for, clean, string_list, unique


class TestIntelligenceEngine:
    def generate_from_execution_package(self, execution_package: dict[str, Any]) -> dict[str, Any]:
        """Canonical package-only QA entry point."""
        package = execution_package or {}
        planning = package.get("planningContext") if isinstance(package.get("planningContext"), dict) else {}
        story = planning.get("story") if isinstance(planning.get("story"), dict) else {}
        acceptance = string_list(planning.get("acceptanceCriteria"))
        result = self.generate(story, acceptance, execution_package=package)
        guidance = package.get("qaGuidance") if isinstance(package.get("qaGuidance"), dict) else {}
        result.update({
            "regressionMatrix": guidance.get("regressionTests", []),
            "negativeTests": guidance.get("negativeTests", []),
            "permissionTests": guidance.get("permissionTests", []),
            "performanceTests": guidance.get("performanceTests", []),
            "coverageExpectations": guidance.get("coverageExpectations", {}),
            "releaseReadiness": (package.get("metadata") or {}).get("status", "Needs Review"),
            "contextSource": "ExecutionPackage",
        })
        return result

    def generate(
        self,
        story: dict[str, Any],
        acceptance_criteria: list[str],
        execution_package: dict[str, Any] | None = None,
        repository_context: dict[str, Any] | None = None,
        knowledge_registry: dict[str, Any] | None = None,
        existing_tests: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        package = execution_package or {}
        repository = repository_context or _repo_context(package)
        title = clean(story.get("title") or _business(package).get("storyTitle") or _business(package).get("taskObjective") or "Approved Story")
        modules = _names(repository.get("relevantModules")) or string_list(story.get("affected_modules")) or string_list((knowledge_registry or {}).get("modules"))[:3]
        flows = _names(repository.get("relevantFlows")) or string_list(story.get("affected_flows")) or string_list((knowledge_registry or {}).get("flows"))[:3]
        tests = [dict(test) for test in (existing_tests or []) if isinstance(test, dict)]
        seed_titles = {clean(test.get("title")).casefold() for test in tests}
        for category in TEST_CATEGORIES:
            candidate = _test_for_category(category, title, acceptance_criteria, modules, flows)
            key = candidate["title"].casefold()
            if key not in seed_titles:
                tests.append(candidate)
                seed_titles.add(key)
        for index, test in enumerate(tests, start=1):
            test["test_id"] = clean(test.get("test_id") or test.get("testId")) or f"TC{index:03d}"
            test["category"] = category_for(test)
        return {
            "testCases": tests,
            "generatedTestCount": len(tests),
            "categories": sorted(unique([category_for(test) for test in tests])),
            "deduplicated": True,
        }


def _test_for_category(category: str, title: str, acceptance: list[str], modules: list[str], flows: list[str]) -> dict[str, Any]:
    module = modules[0] if modules else "selected module"
    flow = flows[0] if flows else "approved flow"
    expected = acceptance[0] if acceptance else f"{title} is verified."
    templates = {
        "Functional": (f"Verify {title} expected behavior", ["Open the approved workflow.", "Perform the primary action."], expected),
        "Integration": (f"Verify {module} integration for {title}", [f"Trigger {flow}.", f"Confirm {module} exchanges expected data."], f"{module} integration supports {title}."),
        "Negative": (f"Reject invalid data for {title}", ["Submit invalid or unavailable data.", "Review the response."], "Invalid data is rejected with a clear message."),
        "Boundary": (f"Validate boundary values for {title}", ["Use first, last, empty, and maximum values.", "Observe handling."], "Boundary values are handled without data loss."),
        "Permission": (f"Validate role access for {title}", ["Use allowed and disallowed roles.", "Attempt the action."], "Authorized users proceed and unauthorized users are blocked."),
        "Security": (f"Validate protected data handling for {title}", ["Attempt access to restricted data.", "Inspect visible fields."], "Protected data is never exposed to unauthorized users."),
        "Performance": (f"Validate response time for {title}", ["Load expected peak data.", "Measure response time."], "Response time remains within the approved threshold."),
        "Regression": (f"Regression check for {flow}", [f"Run existing {flow} regression path.", f"Verify {title} has no side effects."], f"{flow} remains stable."),
    }
    name, steps, expected_result = templates[category]
    return {
        "category": category,
        "title": name,
        "preconditions": ["Approved Story, Execution Package, and repository context are available."],
        "steps": steps,
        "expected_result": expected_result,
        "priority": "High" if category in {"Functional", "Permission", "Security"} else "Medium",
        "risk_level": "High" if category in {"Negative", "Permission", "Security", "Regression"} else "Medium",
        "covers_acceptance_criteria": [0] if acceptance else [],
    }


def _business(package: dict[str, Any]) -> dict[str, Any]:
    return package.get("businessContext") if isinstance(package.get("businessContext"), dict) else {}


def _repo_context(package: dict[str, Any]) -> dict[str, Any]:
    return package.get("repositoryContext") if isinstance(package.get("repositoryContext"), dict) else {}


def _names(values: Any) -> list[str]:
    return [clean(value.get("name") or value.get("path")) for value in values if isinstance(value, dict)] if isinstance(values, list) else string_list(values)
