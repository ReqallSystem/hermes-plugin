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

        with mock.patch.dict("os.environ", {"REQALL_SKIP_PROFILE_SYNC": "1", "HOME": "/tmp"}):
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

        with mock.patch.dict("os.environ", {"REQALL_SKIP_PROFILE_SYNC": "1", "HOME": "/tmp"}):
            self.pkg.register(Ctx())
        kinds = {c[0] for c in calls}
        self.assertIn("hook", kinds)
        self.assertIn("tool", kinds)
        self.assertIn("cmd", kinds)
        self.assertIn("skill", kinds)
        self.assertIn(("tool", "reqall_status"), calls)
        self.assertIn(("tool", "reqall"), calls)
        self.assertIn(("tool", "reqall_skill"), calls)
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
                with mock.patch(f"{PKG}.missing_enabled_homes", return_value=[]):
                    payload = json.loads(self.pkg._handle_status({}))
        self.assertIn("mcp_host", payload)
        self.assertIn("warning", payload)
        self.assertEqual(payload["mcp_tool_name_example"], "mcp__reqall__upsert_record")
        self.assertEqual(payload["plugin_api_tool"], "reqall")
        self.assertTrue(payload["plugin_loaded"])

    def test_probe_mcp_host_offline(self):
        snap = self.mcp_status.probe_mcp_host()
        self.assertIn("host_mcp_registered", snap)
        self.assertIn("session_guidance", snap)
        self.assertIn("mcp__reqall__", self.mcp_status.NAME_ALIASES_NOTE)

    def test_api_key_accepts_mcp_alias(self):
        self.assertEqual(
            self.config.api_key({"MCP_REQALL_API_KEY": "mcp-secret-key"}),
            "mcp-secret-key",
        )
        self.assertEqual(
            self.config.api_key_source({"MCP_REQALL_API_KEY": "mcp-secret-key"}),
            "MCP_REQALL_API_KEY",
        )
        self.assertEqual(
            self.config.api_key(
                {"REQALL_API_KEY": "preferred", "MCP_REQALL_API_KEY": "other"}
            ),
            "preferred",
        )

    def test_mcp_name_case_insensitive(self):
        matched = self.mcp_status.match_expected(
            ["mcp__Reqall__search", "mcp__Reqall__upsert_record", "reqall"]
        )
        self.assertIn("mcp__reqall__search", matched["expected_mcp_tools_present"])
        self.assertIn("mcp__Reqall__search", matched["actual_mcp_tool_names"])
        self.assertNotIn("mcp__reqall__search", matched["expected_mcp_tools_missing"])
        self.assertIn("mcp__reqall__list_records", matched["expected_mcp_tools_missing"])

    def test_skills_host_probe_missing_skill_view(self):
        hit = self.mcp_status.skills_host_probe(["reqall", "reqall_status"])
        self.assertFalse(hit["skill_view_available"])
        self.assertIn("reqall_skill", hit["hint"])

    def test_reqall_skill_dumps_body(self):
        out = json.loads(self.pkg._handle_reqall_skill({"name": "persist"}))
        self.assertTrue(out["ok"])
        self.assertEqual(out["name"], "reqall-persist")
        self.assertIn("Classify the work", out["body"])

    def test_slash_persist_dumps_skill(self):
        text = self.pkg._slash_reqall("persist")
        self.assertIn("reqall-persist", text)
        self.assertIn("Classify the work", text)

    def test_profile_install_symlink(self):
        homes_mod = importlib.import_module(f"{PKG}.reqall.homes")
        install_mod = importlib.import_module(f"{PKG}.reqall.install")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".hermes"
            profile = root / "profiles" / "steward"
            profile.mkdir(parents=True)
            (profile / "config.yaml").write_text(
                "plugins:\n  enabled:\n    - reqall\n",
                encoding="utf-8",
            )
            env = {"HOME": tmp, "HERMES_HOME": str(profile)}
            missing = homes_mod.missing_enabled_homes(env=env)
            self.assertEqual(len(missing), 1)
            self.assertEqual(missing[0]["name"], "steward")
            result = install_mod.ensure_installs(ROOT, apply=True, env=env)
            self.assertGreaterEqual(result["linked"], 1)
            dest = profile / "plugins" / "reqall"
            self.assertTrue(dest.is_symlink() or (dest / "plugin.yaml").is_file())
            self.assertTrue((dest / "plugin.yaml").is_file())
            again = install_mod.ensure_installs(ROOT, apply=True, env=env)
            self.assertEqual(again["linked"], 0)
            self.assertFalse(homes_mod.missing_enabled_homes(env=env))

    def test_profile_install_skips_existing(self):
        install_mod = importlib.import_module(f"{PKG}.reqall.install")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            dest = home / "plugins" / "reqall"
            dest.mkdir(parents=True)
            (dest / "plugin.yaml").write_text("name: other\n", encoding="utf-8")
            out = install_mod.link_into(home, ROOT)
            self.assertEqual(out["action"], "skipped_existing")
            self.assertEqual((dest / "plugin.yaml").read_text(encoding="utf-8"), "name: other\n")


if __name__ == "__main__":
    unittest.main()
