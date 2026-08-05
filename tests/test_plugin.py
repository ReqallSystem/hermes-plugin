"""Unit tests — offline, no network."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
PKG = "hermes_reqall_plugin_test"


def _load():
    if PKG in sys.modules and hasattr(sys.modules[PKG], "reqall"):
        return sys.modules[PKG]
    init = ROOT / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        PKG, init, submodule_search_locations=[str(ROOT)]
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = PKG
    mod.__path__ = [str(ROOT)]  # type: ignore[attr-defined]
    sys.modules[PKG] = mod
    spec.loader.exec_module(mod)
    return mod


class ReqallPluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pkg = _load()
        cls.project = importlib.import_module(f"{PKG}.reqall.project")
        cls.client = importlib.import_module(f"{PKG}.reqall.client")
        cls.hooks = importlib.import_module(f"{PKG}.reqall.hooks")
        cls.state = importlib.import_module(f"{PKG}.reqall.state")
        cls.config = importlib.import_module(f"{PKG}.reqall.config")
        cls.mcp_status = importlib.import_module(f"{PKG}.reqall.mcp_status")

    def test_resolve_project_override(self):
        name = self.project.resolve_project_name(
            "/tmp", env={"REQALL_PROJECT_NAME": "Acme/Widget"}
        )
        self.assertEqual(name, "Acme/Widget")

    def test_normalize_git_remote_shapes(self):
        self.assertEqual(
            self.project._normalize_remote("git@github.com:Org/Repo.git"),
            "Org/Repo",
        )
        self.assertEqual(
            self.project._normalize_remote("https://github.com/Org/Repo.git"),
            "Org/Repo",
        )

    def test_trivial_prompts(self):
        self.assertTrue(self.hooks.is_trivial_prompt("hi"))
        self.assertTrue(self.hooks.is_nontrivial_prompt("please implement the auth fix"))
        self.assertFalse(self.hooks.is_nontrivial_prompt("ok"))

    def test_format_recall(self):
        text = self.client.format_recall(
            "demo/proj",
            {"ok": True, "text": '[{"title":"BUG: x"}]'},
            {"ok": True, "text": "[]"},
        )
        self.assertIn("demo/proj", text)
        self.assertIn("Search hits", text)

    def test_state_dirty_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict("os.environ", {"HERMES_HOME": tmp}):
                sid = "test-sess"
                self.state.mark_dirty(sid, "/tmp/a.py")
                st = self.state.load(sid)
                self.assertTrue(st["dirty"])
                self.assertIn("/tmp/a.py", st["touched_paths"])
                self.state.clear_dirty(sid)
                st2 = self.state.load(sid)
                self.assertFalse(st2["dirty"])

    def test_mcp_call_auth_missing(self):
        with mock.patch(f"{PKG}.reqall.client.api_key", return_value=""):
            res = self.client.mcp_call("search", {"query": "x"})
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "auth_missing")

    def test_register_passes_path_not_str(self):
        skill_calls = []

        class Ctx:
            def register_hook(self, name, fn):
                pass

            def register_tool(self, **kwargs):
                pass

            def register_command(self, **kwargs):
                pass

            def register_skill(self, name, path, description=""):
                skill_calls.append((name, path, description))
                # Mimic Hermes: Path required
                if not hasattr(path, "exists"):
                    raise AttributeError("'str' object has no attribute 'exists'")
                if not path.exists():
                    raise FileNotFoundError(path)

        self.pkg.register(Ctx())
        self.assertGreaterEqual(len(skill_calls), 6)
        for name, path, desc in skill_calls:
            self.assertIsInstance(path, Path, msg=f"{name} got {type(path)}")
            self.assertTrue(path.exists())
            self.assertTrue(str(path).endswith("SKILL.md"))

    def test_register_smoke(self):
        calls = []

        class Ctx:
            def register_hook(self, name, fn):
                calls.append(("hook", name))

            def register_tool(self, **kwargs):
                calls.append(("tool", kwargs["name"]))

            def register_command(self, **kwargs):
                calls.append(("cmd", kwargs["name"]))

            def register_skill(self, name, path, description=""):
                calls.append(("skill", name, type(path).__name__))

        self.pkg.register(Ctx())
        kinds = {c[0] for c in calls}
        self.assertIn("hook", kinds)
        self.assertIn("tool", kinds)
        self.assertIn("cmd", kinds)
        self.assertIn("skill", kinds)
        self.assertIn(("tool", "reqall_status"), calls)
        self.assertIn(("tool", "reqall"), calls)
        skill_types = {c[2] for c in calls if c[0] == "skill"}
        self.assertEqual(skill_types, {"PosixPath"} | skill_types)  # Path
        self.assertTrue(all(c[2] == "PosixPath" or c[2] == "WindowsPath" or c[2] == "Path" or "Path" in c[2] for c in calls if c[0] == "skill"))

    def test_reqall_action_unknown(self):
        out = json.loads(self.pkg._handle_reqall_action({"action": "nope"}))
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "unknown_action")

    def test_reqall_action_calls_client(self):
        with mock.patch(
            f"{PKG}.reqall.client.mcp_call",
            return_value={"ok": True, "text": "Created [test] #1"},
        ) as m:
            out = json.loads(
                self.pkg._handle_reqall_action(
                    {
                        "action": "upsert_record",
                        "arguments": {
                            "project_id": 1,
                            "kind": "test",
                            "title": "t",
                            "status": "resolved",
                        },
                    }
                )
            )
        self.assertTrue(out["ok"])
        m.assert_called_once()
        self.assertEqual(m.call_args[0][0], "upsert_record")

    def test_status_includes_mcp_host(self):
        with mock.patch(
            f"{PKG}.probe_mcp_host",
            return_value={
                "host_mcp_registered": False,
                "registered_mcp_servers": [],
                "registered_reqall_related_tools": ["reqall_status", "reqall"],
                "expected_mcp_tools_present": [],
                "expected_mcp_tools_missing": list(self.mcp_status.EXPECTED_MCP_TOOLS),
                "name_note": self.mcp_status.NAME_ALIASES_NOTE,
                "session_guidance": self.mcp_status.SESSION_GUIDANCE,
                "probe_errors": [],
            },
        ):
            with mock.patch(f"{PKG}.api_key", return_value=""):
                payload = json.loads(self.pkg._handle_status({}))
        self.assertIn("mcp_host", payload)
        self.assertIn("warning", payload)
        self.assertEqual(payload["mcp_tool_name_example"], "mcp__reqall__upsert_record")
        self.assertEqual(payload["plugin_api_tool"], "reqall")

    def test_probe_mcp_host_offline(self):
        snap = self.mcp_status.probe_mcp_host()
        self.assertIn("host_mcp_registered", snap)
        self.assertIn("session_guidance", snap)
        self.assertIn("mcp__reqall__", self.mcp_status.NAME_ALIASES_NOTE)


if __name__ == "__main__":
    unittest.main()
