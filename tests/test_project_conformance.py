"""Shared fixtures vendored from ReqallSystem/plugins/test/project-naming-cases.json.

Keep the fixture byte-identical to the catalog; the cross-repo checker owns drift.
The offline runner supplies temporary HOME and disables network/profile sync.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from reqall import config, project


class ProjectConformanceTests(unittest.TestCase):
    def run_case(self, case):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cwd = root / case.get('cwd', '')
            cwd.mkdir(parents=True, exist_ok=True)
            if case.get('marker', True):
                (root / '.reqall-workspace').touch()
            for directory in case.get('directories', []):
                (root / directory).mkdir(parents=True, exist_ok=True)
            for group in ('files', 'binary_files', 'repeat_files'):
                for filename, value in case.get(group, {}).items():
                    path = root / filename
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if group == 'binary_files':
                        path.write_bytes(bytes(value))
                    else:
                        path.write_text(value[0] * value[1] if group == 'repeat_files' else value,
                                        encoding='utf-8')
            env = {'HOME': tmp, 'HERMES_HOME': tmp, 'XDG_CONFIG_HOME': tmp,
                   'REQALL_SKIP_PROFILE_SYNC': '1'}
            env.update({key: value.replace('$root', tmp) for key, value in case.get('env', {}).items()})
            with mock.patch.dict(os.environ, env, clear=True), \
                 mock.patch.object(project, '_git_origin', return_value=case.get('remote', '')):
                config.load_plugin_settings({})
                try:
                    binding = project.bind_project(str(cwd), case.get('prompt', ''), None if case.get('use_default_env') else env)
                    expected = project.machine_project_name(env) if case['expected'] == '$machine' else case['expected']
                    user = project.machine_project_name({'REQALL_MACHINE_NAME': 'contract.host'}).split('/')[-1]
                    expected = expected.replace('$user', user)
                    if 'expected_machine' in case:
                        self.assertEqual(project.machine_project_name(env), case['expected_machine'].replace('$user', user))
                    self.assertEqual((binding.name, binding.source), (expected, case['source']))
                    self.assertTrue(binding.safe_to_upsert)
                finally:
                    config.load_plugin_settings({})


def _test(case):
    return lambda self: self.run_case(case)


_CASES = json.loads((Path(__file__).parent / 'fixtures/project-naming-cases.json').read_text())['cases']
assert len({case['id'] for case in _CASES}) == len(_CASES), 'Duplicate shared conformance case IDs'
for _case in _CASES:
    setattr(ProjectConformanceTests, 'test_' + _case['id'].replace('-', '_'), _test(_case))
