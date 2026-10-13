import unittest
import importlib
import sys
import types
from pathlib import Path

# Load the pure navigation unit without initializing FastAPI/pydantic.
package = types.ModuleType('_hei_workspace_policy_test')
package.__path__ = [str(Path(__file__).resolve().parents[1] / 'backend' / 'workspace')]
sys.modules[package.__name__] = package
NavigationService = importlib.import_module(f'{package.__name__}.navigation').NavigationService


class NamedRoleNavigationTests(unittest.TestCase):
    def ids(self, role):
        return {item['id'] for item in NavigationService().get_navigation(role)['items']}

    def test_manager_can_configure(self):
        self.assertIn('settings', self.ids('manager'))
        self.assertIn('approvals', self.ids('manager'))

    def test_developer_cannot_approve_or_configure(self):
        self.assertIn('execution', self.ids('developer'))
        self.assertNotIn('approvals', self.ids('developer'))
        self.assertNotIn('settings', self.ids('developer'))

    def test_collaborator_can_plan_not_execute(self):
        self.assertIn('planning', self.ids('collaborator'))
        self.assertNotIn('execution', self.ids('collaborator'))

    def test_read_only_and_unknown_do_not_gain_write_workspaces(self):
        for role in ('tester', 'reader', 'unknown'):
            self.assertFalse(self.ids(role) & {'planning', 'execution', 'approvals', 'settings'})
