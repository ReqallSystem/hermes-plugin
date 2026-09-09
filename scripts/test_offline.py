#!/usr/bin/env python3
"""Run plugin tests with temporary profile state and denied network access."""
from pathlib import Path
import os
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="reqall-offline-tests-") as home:
        env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP") if key in os.environ}
        env.update(HOME=home, HERMES_HOME=home, XDG_CONFIG_HOME=home,
                   REQALL_SKIP_PROFILE_SYNC="1", PYTHONDONTWRITEBYTECODE="1")
        with patch.dict(os.environ, env, clear=True), \
             patch.object(socket.socket, "connect", side_effect=AssertionError("network disabled in plugin tests")), \
             patch.object(socket.socket, "connect_ex", side_effect=AssertionError("network disabled in plugin tests")):
            sys.dont_write_bytecode = True
            sys.path.insert(0, str(ROOT))
            suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
            result = unittest.TextTestRunner(verbosity=2).run(suite)
            return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
