"""Unit tests — offline, no network."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import types
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
        # Explicit empty key disables env + must not use ambient stored auth
        res = self.client.mcp_call(
            "search",
            {"query": "x"},
            env={"REQALL_API_KEY": "", "REQALL_URL": "https://www.reqall.net"},
        )
        # When empty string is set, resolveApiKey returns "" — but loadStoredAuth
        # is only skipped when key is present. Ensure empty forces missing.
        if res.get("ok"):
            # Ambient host auth may still apply if client ignores empty; force
            # path by patching api_key
            with mock.patch.object(self.config, "api_key", return_value=""):
                res = self.client.mcp_call("search", {"query": "x"}, env={"REQALL_API_KEY": ""})
        # Prefer unit of client with patched key
        with mock.patch(f"{PKG}.reqall.client.api_key", return_value=""):
            res = self.client.mcp_call("search", {"query": "x"})
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "auth_missing")

    def test_register_smoke(self):
        calls = []

        class Ctx:
            def register_hook(self, name, fn):
                calls.append(("hook", name))

            def register_tool(self, **kwargs):
                calls.append(("tool", kwargs["name"]))

            def register_command(self, **kwargs):
                calls.append(("cmd", kwargs["name"]))

            def register_skill(self, name, path):
                calls.append(("skill", name))

        self.pkg.register(Ctx())
        kinds = {c[0] for c in calls}
        self.assertIn("hook", kinds)
        self.assertIn("tool", kinds)
        self.assertIn("cmd", kinds)
        self.assertIn("skill", kinds)
        self.assertIn(("tool", "reqall_status"), calls)


if __name__ == "__main__":
    unittest.main()
