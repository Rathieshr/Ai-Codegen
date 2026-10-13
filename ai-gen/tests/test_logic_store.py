"""Tests for JSON-backed logic store dependency linking."""

import json
import tempfile
import unittest
from pathlib import Path

from logic_store.store import LogicStore


class LogicStoreDependencyTests(unittest.TestCase):
    def test_resolves_dependency_records(self) -> None:
        store = self._store(
            [
                {
                    "id": "Login",
                    "name": "Login Flow",
                    "keywords": ["login"],
                    "summary": "Login summary.",
                    "steps": ["Validate password"],
                    "depends_on": ["TokenGeneration"],
                },
                {
                    "id": "TokenGeneration",
                    "name": "TokenGeneration",
                    "keywords": ["token"],
                    "summary": "Token summary.",
                    "steps": ["Generate session token"],
                    "depends_on": [],
                },
            ]
        )

        result = store.find_relevant("login")[0]

        self.assertEqual(result["dependent_flows"][0]["id"], "TokenGeneration")
        self.assertEqual(
            result["linked_flows"],
            [{"from": "Login Flow", "to": "TokenGeneration"}],
        )

    def test_avoids_duplicate_dependency_steps(self) -> None:
        store = self._store(
            [
                {
                    "id": "Login",
                    "name": "Login Flow",
                    "keywords": ["login"],
                    "summary": "Login summary.",
                    "steps": ["Validate password"],
                    "depends_on": ["TokenGeneration", "TokenGeneration"],
                },
                {
                    "id": "TokenGeneration",
                    "name": "TokenGeneration",
                    "keywords": ["token"],
                    "summary": "Token summary.",
                    "steps": ["Generate session token"],
                    "depends_on": [],
                },
            ]
        )

        result = store.find_relevant("login")[0]

        self.assertEqual(len(result["dependent_flows"]), 1)
        self.assertEqual(result["linked_flows"].count({"from": "Login Flow", "to": "TokenGeneration"}), 1)

    def test_prevents_circular_dependencies(self) -> None:
        store = self._store(
            [
                {
                    "id": "Login",
                    "name": "Login Flow",
                    "keywords": ["login"],
                    "summary": "Login summary.",
                    "steps": ["Validate password"],
                    "depends_on": ["TokenGeneration"],
                },
                {
                    "id": "TokenGeneration",
                    "name": "TokenGeneration",
                    "keywords": ["token"],
                    "summary": "Token summary.",
                    "steps": ["Generate session token"],
                    "depends_on": ["Login"],
                },
            ]
        )

        result = store.find_relevant("login")[0]

        self.assertEqual([flow["id"] for flow in result["dependent_flows"]], ["TokenGeneration"])

    def _store(self, items: list[dict]) -> LogicStore:
        temp_file = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        with temp_file:
            json.dump(items, temp_file)
        return LogicStore(Path(temp_file.name))


if __name__ == "__main__":
    unittest.main()
