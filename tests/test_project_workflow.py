"""Offline routing and bundled workflow contracts; never use a live profile."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from reqall import config, project

ROOT = Path(__file__).resolve().parent.parent


class ProjectWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = {"HOME": self.temp.name, "HERMES_HOME": self.temp.name,
                    "XDG_CONFIG_HOME": self.temp.name,
                    "REQALL_MACHINE_NAME": "Test Host"}
        self.patch = mock.patch.dict(os.environ, self.env, clear=True)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        config.load_plugin_settings({})
        self.addCleanup(config.load_plugin_settings, {})
        self.origin = mock.patch.object(project, "_git_origin", return_value="").start()
        self.addCleanup(mock.patch.stopall)

    def test_no_origin_always_uses_reserved_machine_not_cwd(self):
        binding = project.bind_project(cwd=self.temp.name, env=self.env)
        self.assertTrue((binding.name or "").startswith(".machine/test-host/"), binding)
        self.assertEqual(binding.source, "machine")
        self.assertTrue(binding.safe_to_upsert)

    def test_unlabelled_prose_never_selects_a_project(self):
        for prompt in ("Fix src/auth.py", "use text/plain", "compare Acme/Widget",
                       "read https://github.com/Acme/Widget first"):
            with self.subTest(prompt=prompt):
                self.assertIsNone(project.extract_project_hint(prompt))
                self.assertEqual(project.bind_project(self.temp.name, prompt, self.env).source,
                                 "machine")

    def test_explicit_label_preserves_complete_selection(self):
        for prompt, expected in (("project_name=Team/Widget", "Team/Widget"),
                                 ('project: "Personal Notes"', "Personal Notes"),
                                 ("project=Notebook", "Notebook"),
                                 ("project=.machine/host/User", ".machine/host/User"),
                                 ("project_name=Team/Widget.git", "Team/Widget.git")):
            with self.subTest(prompt=prompt):
                self.assertEqual(project.extract_project_hint(prompt), expected)
                self.assertEqual(project.bind_project(self.temp.name, prompt, self.env).name,
                                 expected)

    def test_machine_fallback_survives_unavailable_os_identity(self):
        with mock.patch.object(project.socket, "gethostname", side_effect=OSError("unavailable")):
            with mock.patch("pwd.getpwuid", side_effect=KeyError("no user")):
                self.assertEqual(project.machine_project_name({}), ".machine/unknown/unknown")

    def test_intend_skill_selects_deduplicated_agreed_intent(self):
        path = ROOT / "skills/ intend/SKILL.md".replace(" ", "")
        self.assertTrue(path.is_file(), "reqall-intend must ship with this plugin")
        text = path.read_text()
        for contract in ("reqall-intend", "select_intent", "session_id", "spec", "arch",
                         "acceptance", "non-goals", "dedup", "questions", "chores", "trivial"):
            self.assertIn(contract, text.lower())

    def test_persist_requires_snapshot_verified_acknowledgement(self):
        text = (ROOT / "skills/persist/SKILL.md").read_text()
        for contract in ("reqall_session", "action=status", "work_revision", "session_id",
                         "action=acknowledge", "record_ids", "readback", "stale"):
            self.assertIn(contract, text)
        self.assertNotIn("/reqall clear-dirty", text)
        self.assertLess(text.index("action=status"), text.index("action=acknowledge"))

    def test_machine_uses_scoped_setting_with_environment_precedence(self):
        config.load_plugin_settings({"machine_name": "Profile Host"})
        with mock.patch("pwd.getpwuid", return_value=mock.Mock(pw_name="User")):
            self.assertEqual(project.machine_project_name({}), ".machine/profile-host/User")
            self.assertEqual(project.machine_project_name(self.env), ".machine/test-host/User")

    def test_partial_save_docs_require_same_id_record_recovery(self):
        for name in ('persist', 'intend'):
            with self.subTest(skill=name):
                text = (ROOT / 'skills' / name / 'SKILL.md').read_text().lower()
                for contract in ('same-id `upsert_record`', 'pending_write_failures',
                                 'link repair alone', 'do not recreate', 'readback'):
                    self.assertIn(contract, text)

    def test_workflow_skills_define_inline_link_failure_contract(self):
        for name in ("persist", "document", "context", "triage", "review"):
            with self.subTest(skill=name):
                text = (ROOT / "skills" / name / "SKILL.md").read_text().lower()
                for contract in ("inline", "upsert_record", "target_table", "direction",
                                 "outgoing", "incoming", "per-link", "existing-pair",
                                 "legacy", "upsert_link", "list_links"):
                    self.assertIn(contract, text)

    def test_machine_uses_os_login_when_pwd_is_unavailable(self):
        with mock.patch.dict("sys.modules", {"pwd": None}):
            with mock.patch.object(os, "getlogin", return_value="Windows User"):
                self.assertEqual(project.machine_project_name(self.env),
                                 ".machine/test-host/Windows-User")

    def test_agents_contract_is_safe_and_hook_timing_is_honest(self):
        text = (ROOT / "AGENTS.md").read_text()
        for contract in ("reqall-intend", "select_intent", "work_revision", "acknowledge",
                         ".machine/", "REQALL_MACHINE_NAME", "once per user turn",
                         "file-edit", "pre-compaction", "target_table", "per-link"):
            self.assertIn(contract, text)
        self.assertNotIn("clear-dirty", text)
        self.assertNotIn("Run `python3 ensure-install.py`", text)

    def test_sleep_retains_work_review_and_uses_machine_binding(self):
        text = (ROOT / "skills/sleep/SKILL.md").read_text()
        for contract in ("work_review", "promote", "discard", "sleep_apply",
                         ".machine/", "REQALL_MACHINE_NAME"):
            self.assertIn(contract, text)


if __name__ == "__main__":
    unittest.main()
