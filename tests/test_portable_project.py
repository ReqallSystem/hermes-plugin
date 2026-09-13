"""Portable naming conformance: real temporary files, no live profiles."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from reqall import config, project


class PortableProjectTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.env = {"HOME": temp.name, "HERMES_HOME": temp.name,
                    "XDG_CONFIG_HOME": temp.name, "REQALL_SKIP_PROFILE_SYNC": "1"}
        patcher = mock.patch.dict(os.environ, self.env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        config.load_plugin_settings({})
        self.addCleanup(config.load_plugin_settings, {})
        patcher = mock.patch.object(project, "_git_origin", return_value="")
        self.origin = patcher.start()
        self.addCleanup(patcher.stop)

    def bind(self, root=None, **kwargs):
        return project.bind_project(str(root or self.root), **kwargs)

    def test_deep_json_cannot_crash_metadata_fallback(self):
        (self.root / 'package.json').write_text('[' * 2000 + '0' + ']' * 2000)
        (self.root / 'go.mod').write_text('module example.com/fallback')
        self.assertEqual(self.bind().name, 'example.com/fallback')

    @unittest.skipUnless(hasattr(os, 'O_NONBLOCK'), 'POSIX nonblocking open')
    def test_metadata_open_is_nonblocking_against_file_replacement(self):
        path = self.root / '.reqall.yml'
        path.write_text('project: valid')
        with mock.patch.object(project.os, 'open', wraps=os.open) as opened:
            self.assertEqual(project._read_metadata(path), 'project: valid')
        opened.assert_called_once()
        self.assertTrue(opened.call_args.args[1] & os.O_NONBLOCK)

    def test_local_discovery_requires_existing_directory(self):
        (self.root / '.reqall.yml').write_text('project: parent')
        file = self.root / 'file'
        file.touch()
        for cwd in (file, self.root / 'missing'):
            with self.subTest(cwd=str(cwd)):
                self.assertEqual(self.bind(cwd).source, 'machine')

    def test_workspace_containment_tilde_and_marker_safety(self):
        workspace = self.root / 'workspace'
        leaf = workspace / 'team' / 'src'
        outside = self.root / 'outside'
        leaf.mkdir(parents=True)
        outside.mkdir()
        (workspace / '.reqall-workspace').touch()
        for configured in ('~/workspace', str(workspace)):
            with mock.patch.dict(os.environ, {'REQALL_WORKSPACE_ROOT': configured}):
                self.assertEqual(self.bind(leaf).name, 'team/src')
        for configured in (str(outside), str(self.root / 'missing'), str(leaf / 'bad\x00root')):
            with self.subTest(configured=configured):
                self.assertIsNone(project._workspace_root(leaf, {'REQALL_WORKSPACE_ROOT': configured}))
        link = workspace / 'escape'
        link.symlink_to(outside, target_is_directory=True)
        with mock.patch.dict(os.environ, {'REQALL_WORKSPACE_ROOT': str(workspace)}):
            self.assertEqual(self.bind(link).source, 'machine')
        (leaf / '.reqall-workspace').mkdir()
        self.assertEqual(project._workspace_root(leaf, {}), workspace)

    def test_package_ambiguous_declarations_fall_through(self):
        leaf = self.root / 'leaf'
        leaf.mkdir()
        (self.root / 'package.json').write_text('{"name":"parent"}')
        for filename, text in (
            ('go.mod', 'module first/module\nmodule second/module'),
            ('Cargo.toml', '[package]\nname="first"\nname="second"'),
            ('Cargo.toml', '[package]\nname="first"\nname=false'),
        ):
            with self.subTest(filename=filename, text=text):
                path = leaf / filename
                path.write_text(text)
                try:
                    self.assertEqual(self.bind(leaf).name, 'parent')
                finally:
                    path.unlink()
        (leaf / 'go.mod').write_text('module `example.com/acme/repo/v2`')
        self.assertEqual(self.bind(leaf).name, 'example.com/acme/repo/v2')

    def test_yaml_continuations_do_not_truncate_identity(self):
        (self.root / 'package.json').write_text('{"name":"fallback"}')
        for continuation in ('  continuation', '  child: nested'):
            with self.subTest(continuation=continuation):
                (self.root / '.reqall.yml').write_text('project: wrong\n' + continuation + '\n')
                self.assertEqual(self.bind().name, 'fallback')

    def test_yaml_valid_key_fallback_matches_shared_scalar_contract(self):
        for text, expected in (
            ('project: valid\nname: null', 'valid'),
            ('project: null\nname: valid', 'valid'),
            ('PROJECT: upper', ''),
            ('project: -.nan', ''),
            ('project: 0o89', '0o89'),
        ):
            with self.subTest(text=text):
                self.assertEqual(project._yaml_name(text), expected)

    def test_machine_preserves_historical_host_punctuation(self):
        with mock.patch('pwd.getpwuid', return_value=mock.Mock(pw_name='OsUser')):
            self.assertEqual(project.machine_project_name({'REQALL_MACHINE_NAME': ' --My!Host.Example/ -- '}),
                             '.machine/my!host.example/OsUser')

    def test_machine_whitespace_env_falls_back_to_scoped_override(self):
        config.load_plugin_settings({'machine_name': ' CI.Example '})
        with mock.patch.dict(os.environ, {'REQALL_MACHINE_NAME': '  '}), \
             mock.patch('pwd.getpwuid', return_value=mock.Mock(pw_name='OsUser')), \
             mock.patch.object(project.socket, 'gethostname', return_value='Actual.Domain'):
            self.assertEqual(project.machine_project_name(), '.machine/ci.example/OsUser')
        with mock.patch.dict(os.environ, {'REQALL_MACHINE_NAME': ' My!Host.Example '}), \
             mock.patch('pwd.getpwuid', return_value=mock.Mock(pw_name='OsUser')):
            self.assertEqual(project.machine_project_name(), '.machine/my!host.example/OsUser')

    def test_all_bundled_routing_guides_include_portable_chain(self):
        root = Path(__file__).resolve().parent.parent
        skills = sorted((root / 'skills').glob('*/SKILL.md'))
        self.assertEqual(len(skills), 7)
        for path in skills + [root / 'README.md', root / 'AGENTS.md']:
            with self.subTest(path=str(path.relative_to(root))):
                text = path.read_text()
                for token in ('REQALL_PROJECT_NAME', '.reqall.yml', '.reqall.yaml',
                              'package.json', 'go.mod', 'Cargo.toml', 'REQALL_WORKSPACE_ROOT',
                              '.reqall-workspace', '.machine/', 'REQALL_MACHINE_NAME',
                              'authoritative', '.user', '64 KiB'):
                    self.assertIn(token, text)
                self.assertNotIn('selection → `.machine/', text)

    def test_prompt_selection_is_retained_between_turns_with_priority(self):
        from reqall import hooks
        st = {}
        hooks._bind(st, prompt='project=.user', cwd=str(self.root))
        st['project_id'] = 42
        for prompt in ('continue', '[ASYNC DELEGATION BATCH COMPLETE — 1]\nproject=example/repo'):
            binding = hooks._bind(st, prompt=prompt, cwd=str(self.root))
            self.assertEqual((binding.name, binding.source, st['project_id']), ('.user', 'prompt', 42))
        self.assertEqual(hooks._bind(st, prompt='project=new/choice', cwd=str(self.root)).name, 'new/choice')
        self.origin.return_value = 'https://host/git/wins.git'
        self.assertEqual(hooks._bind(st, cwd=str(self.root)).name, 'git/wins')
        with mock.patch.dict(os.environ, {'REQALL_PROJECT_NAME': ' override/wins '}):
            self.assertEqual(hooks._bind(st, cwd=str(self.root)).name, 'override/wins')
        self.origin.return_value = ''
        self.assertEqual(hooks._bind(st, cwd=str(self.root)).name, 'new/choice')

    def test_async_subagent_report_preserves_retained_selection(self):
        from reqall import hooks
        report = '[ASYNC SUBAGENT REPORT] example project_name=wrong/example; tests complete'
        st = {}
        hooks._bind(st, prompt='project_name=acme/chosen', cwd=str(self.root))
        st['project_id'] = 42
        for prompt in (report, ' \n' + report):
            with self.subTest(prompt=prompt):
                binding = hooks._bind(st, prompt=prompt, cwd=str(self.root))
                self.assertEqual((binding.name, binding.source), ('acme/chosen', 'prompt'))
                self.assertEqual(st['prompt_project_name'], 'acme/chosen')
                self.assertEqual(st['project_id'], 42)
                self.assertIsNone(project.extract_project_hint(prompt))
        for prompt in ('Discuss [ASYNC SUBAGENT REPORT] project_name=acme/chosen',
                       '[ASYNC SUBAGENT REPORTING] project_name=acme/chosen',
                       'ASYNC SUBAGENT REPORT project_name=acme/chosen'):
            with self.subTest(prompt=prompt):
                self.assertEqual(project.extract_project_hint(prompt), 'acme/chosen')

    def test_synthetic_delegation_reports_do_not_rebind_session(self):
        from reqall import hooks, state
        for prefix in ('ASYNC DELEGATION BATCH COMPLETE', 'ASYNC DELEGATION COMPLETE',
                       'ASYNC DELEGATION TASK FAILED'):
            with self.subTest(prefix=prefix):
                text = f'[{prefix} — task-1]\nReport: `project_name=org/repo` fixed.'
                binding = self.bind()
                state.save('synthetic', dict(state.load('synthetic'), project_name=binding.name,
                                            project_source=binding.source, project_id=4946))
                with mock.patch.object(hooks, 'is_nontrivial_prompt', return_value=False), \
                     mock.patch.object(hooks, '_subscription_updates', return_value=None):
                    hooks.pre_llm_call(session_id='synthetic', cwd=str(self.root), user_message=text)
                self.assertEqual(state.load('synthetic')['project_name'], binding.name)
                self.assertEqual(state.load('synthetic')['project_id'], 4946)
                self.assertIsNone(project.extract_project_hint(text))
        self.assertEqual(project.extract_project_hint('Use project_name=real/selection'), 'real/selection')

    def test_prompt_unquoted_sentence_punctuation_only(self):
        for text, expected in (
            ('Please use project_name=acme/notes: refactor it.', 'acme/notes'),
            ('project=acme/notes.,:;!?)]', 'acme/notes'),
            ('project="acme/notes."', 'acme/notes.'),
            ('project=.user', '.user'),
            ('project_name=Team/Widget.git', 'Team/Widget.git'),
            ('project="" next project=not-selected', None),
        ):
            with self.subTest(text=text):
                self.assertEqual(project.extract_project_hint(text), expected)

    def test_git_accepts_only_network_origins_and_keeps_final_two_segments(self):
        cases = {
            'https://github.com/Org/Repo.git/': 'Org/Repo',
            'http://host/Org/Repo.git': 'Org/Repo',
            'ssh://git@host:2222/group/sub/repo.git': 'sub/repo',
            'git://host/group/sub/repo.git': 'sub/repo',
            'git@host:group/sub/repo.git': 'sub/repo',
            '/srv/repos/local.git': '', 'C:/repos/local.git': '',
            r'C:\repos\local.git': '', 'file:///srv/repos/local.git': '',
            '../Org/Repo.git': '', 'Org/Repo.git': '', '~/Org/Repo.git': '',
            'ftp://host/org/repo.git': '', 'https:///org/repo.git': '',
            'https://host/repo.git': '', 'host:org/../repo.git': '',
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(project._normalize_remote(value), expected)

    def test_cargo_multiline_strings_never_supply_package_name(self):
        leaf = self.root / 'leaf'
        leaf.mkdir()
        (self.root / 'package.json').write_text('{"name":"fallback"}')
        for quote in ('"' * 3, "'" * 3):
            with self.subTest(quote=quote):
                (leaf / 'Cargo.toml').write_text('[package]\ndescription = ' + quote + '\nname = "wrong"\n' + quote + '\n')
                self.assertEqual(self.bind(leaf).name, 'fallback')

    def test_cargo_only_simple_package_name(self):
        path = self.root / 'Cargo.toml'
        for text, expected in (
            ('[[bin]]\nname = "helper"\n[package]\nname = "real-package"\n', 'real-package'),
            ('[[bin]]\nname = "helper"\n', None),
            ('[dependencies]\nname = "helper"\n', None),
            ('[package]\nversion = "1"\n[[bin]]\nname = "helper"', None),
            ("[package] # comment\n  name = 'real-package' # comment\n", 'real-package'),
            ('[package]\nname = "broken\'\n', None),
            ('[package]\nname = "valid" trailing\n', None),
        ):
            with self.subTest(text=text):
                path.write_text(text)
                self.assertEqual(project._package_name(self.root), expected)

    def test_go_comments_never_join_module_tokens(self):
        (self.root / 'Cargo.toml').write_text('[package]\nname = "fallback"')
        (self.root / 'go.mod').write_text('module example.com/ac/* comment */me/repo\n')
        self.assertEqual(self.bind().name, 'fallback')

    def test_go_module_keeps_full_identity_after_comments(self):
        path = self.root / 'go.mod'
        for text, expected in (
            ('// header\n\nmodule example.com/acme/widgets/v2 // version\ngo 1.22', 'example.com/acme/widgets/v2'),
            ('/* header\ncomment */\nmodule example.com/group/repo', 'example.com/group/repo'),
            ('module "example.com/acme/repo"\n', 'example.com/acme/repo'),
            ('', None), ('module /absolute/path', None),
            ('module example.com/acme/repo junk', None),
        ):
            with self.subTest(text=text):
                path.write_text(text)
                self.assertEqual(project._package_name(self.root), expected)

    def test_yaml_nearest_valid_scalar_and_project_precedence(self):
        leaf = self.root / 'leaf'
        leaf.mkdir()
        (self.root / '.reqall.yml').write_text('project: ancestor\n')
        path = leaf / '.reqall.yml'
        cases = [
            ('name: other\nproject: chosen # comment\n', 'chosen'),
            ('project: "quoted/name" # comment\n', 'quoted/name'),
            ("project: 'single/name'\n", 'single/name'),
            ('project: src\n', 'src'),
            ('project: /absolute/path\n', 'ancestor'),
            ('project: true\n', 'ancestor'), ('name: 123\n', 'ancestor'),
            ('project: null\n', 'ancestor'), ('project: 1e3\n', 'ancestor'),
            ('project: "123"\n', '123'),
            ('project: "broken\n', 'ancestor'), ("project: 'mismatch\"\n", 'ancestor'),
            ('project: "ok" junk\n', 'ancestor'),
            ('project: one\nproject: two\n', 'ancestor'),
            ('project: one\nproject: one\n', 'one'),
            ('nested:\n  project: nested\n', 'ancestor'),
            ('project: [a, b]\n', 'ancestor'), ('project: {name: a}\n', 'ancestor'),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                path.write_text(text)
                self.assertEqual(self.bind(leaf).name, expected)
        (leaf / '.reqall.yaml').write_text('project: alternate\n')
        path.write_text('project: /invalid\n')
        self.assertEqual(self.bind(leaf).name, 'alternate')
        path.write_text('project: first\n')
        self.assertEqual(self.bind(leaf).name, 'first')

    def test_metadata_reads_are_bounded_utf8_and_fail_safe(self):
        leaf = self.root / 'leaf'
        leaf.mkdir()
        (self.root / 'package.json').write_text('{"name":"parent"}')
        prefixes = {'.reqall.yml': b'project: oversized\n', '.reqall.yaml': b'name: oversized\n',
                    'package.json': b'{"name":"oversized"}', 'go.mod': b'module oversized\n',
                    'Cargo.toml': b'[package]\nname = "oversized"\n'}
        for filename, prefix in prefixes.items():
            for data in (b'\xff', prefix + b' ' * 65537):
                with self.subTest(filename=filename, data=data[:8]):
                    path = leaf / filename
                    path.write_bytes(data)
                    try:
                        self.assertEqual(self.bind(leaf).name, 'parent')
                    finally:
                        path.unlink()

    def test_workspace_process_env_and_boundary(self):
        workspace = self.root / 'work'
        leaf = workspace / 'src'
        leaf.mkdir(parents=True)
        (self.root / '.reqall.yml').write_text('project: outside\n')
        with mock.patch.dict(os.environ, {'REQALL_WORKSPACE_ROOT': str(workspace)}):
            binding = self.bind(leaf)
            self.assertEqual((binding.name, binding.source), ('src', 'workspace_relative'))
            self.assertEqual(self.bind(workspace).source, 'machine')
        (workspace / 'package.json').write_text('{"name":"inside"}')
        with mock.patch.dict(os.environ, {'REQALL_WORKSPACE_ROOT': '..'}):
            self.assertEqual(self.bind(leaf).name, 'inside')

    def test_metadata_names_are_validated_before_normalization(self):
        for invalid in ('/org/repo', 'org/repo/', 'org//repo', 'org/../repo',
                        'org/./repo', '.', '..', '~/repo', 'C:/repo',
                        r'org\repo', r'\\server\repo', '@org/repo', '@@org/repo'):
            with self.subTest(invalid=invalid):
                self.assertEqual(project._safe_name(invalid), '')
        for valid in ('src', 'repo', 'org/src', '.hidden', 'a.b/c-d_e'):
            with self.subTest(valid=valid):
                self.assertEqual(project._safe_name(valid), valid)
