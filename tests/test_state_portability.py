"""State storage must not depend on a POSIX-only import."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


class StatePortabilityTests(unittest.TestCase):
    def test_state_import_does_not_require_fcntl(self):
        path = Path(__file__).resolve().parents[1] / 'reqall' / 'state.py'
        spec = importlib.util.spec_from_file_location('reqall._portable_state_probe', path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        failure = None
        with patch.dict(sys.modules, {'fcntl': None}):
            try:
                spec.loader.exec_module(module)
            except ImportError as exc:
                failure = str(exc)
        self.assertIsNone(failure, 'State storage must import without POSIX fcntl')
