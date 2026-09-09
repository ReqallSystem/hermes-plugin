"""Executed script failures can leave changes; rejected calls cannot."""
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from reqall import config, hooks, state


class FailedExecutionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.enterContext(patch.dict(os.environ, {'HOME': tmp.name, 'HERMES_HOME': tmp.name,
                          'XDG_CONFIG_HOME': tmp.name, 'REQALL_SKIP_PROFILE_SYNC': '1'}, clear=True))
        self.enterContext(patch.object(config, 'hermes_home', return_value=self.home))
        for method in ('connect', 'connect_ex'):
            self.enterContext(patch.object(socket.socket, method, side_effect=AssertionError('offline')))

    def test_nonzero_terminal_tracks_real_partial_mutation(self):
        marker = self.home / 'changed.txt'
        command = [sys.executable, '-c',
                   'from pathlib import Path; import sys; Path(sys.argv[1]).write_text("changed"); raise SystemExit(1)',
                   str(marker)]
        run = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(run.returncode, 1)
        self.assertEqual(marker.read_text(), 'changed')
        hooks.post_tool_call('terminal', args={'command': shlex.join(command)},
                            result={'exit_code': run.returncode, 'output': run.stdout},
                            status='error', session_id='s')
        self.assertTrue(state.load('s')['dirty'])
        self.assertEqual(state.load('s')['work_revision'], 1)

    def test_execute_code_exception_tracks_real_partial_mutation(self):
        marker = self.home / 'cell.txt'
        code = f'from pathlib import Path; Path({str(marker)!r}).write_text("partial"); raise RuntimeError("later failure")'
        run = subprocess.run([sys.executable, '-c', code], text=True, capture_output=True)
        self.assertEqual(marker.read_text(), 'partial')
        self.assertEqual(run.returncode, 1)
        result = {'status': 'error', 'exit_code': run.returncode, 'output': run.stdout,
                  'error': run.stderr, 'tool_calls_made': 0,
                  'kernel': {'mode': 'session', 'execution_count': 1}}
        hooks.post_tool_call('execute_code', args={'code': code}, result=json.dumps(result),
                            status='error', session_id='s')
        self.assertTrue(state.load('s')['dirty'])

    def test_executed_failure_evidence_includes_timeout_and_remote_cells(self):
        cases = [('terminal', {'exit_code': 124, 'error': 'Command timed out'}, 'error'),
                 ('terminal', {'exit_code': -9, 'output': ''}, 'error'),
                 ('execute_code', {'status': 'error', 'tool_calls_made': 1}, 'error'),
                 ('execute_code', {'status': 'timeout', 'exit_code': -1,
                                   'kernel': {'execution_count': 1}}, 'error'),
                 ('terminal', {'executed': True, 'error': 'lost response'}, 'partial')]
        for i, (tool, result, status) in enumerate(cases):
            with self.subTest(tool=tool, result=result):
                sid = str(i)
                hooks.post_tool_call(tool, args={'command': 'python change.py', 'code': 'run()'},
                                    result=result, status=status, session_id=sid)
                self.assertTrue(state.load(sid)['dirty'])

    def test_blocked_denied_unexecuted_calls_never_dirty(self):
        cases = [(status, {'exit_code': 1, 'output': 'not executed'})
                 for status in ('blocked', 'denied', 'cancelled', 'disabled', 'unexecuted')]
        cases += [('error', {'status': status, 'exit_code': 1})
                  for status in ('blocked', 'denied', 'cancelled', 'disabled', 'unexecuted')]
        cases += [('error', {'exit_code': -1, 'error': 'environment creation failed'}),
                  ('error', {'error': 'approval denied', 'tool_calls_made': 0}),
                  ('error', None), ('error', {}),
                  ('success', {'executed': False, 'exit_code': 0}),
                  ('error', {'exit_code': True}), ('error', {'exit_code': '1'})]
        for tool in ('terminal', 'execute_code'):
            for i, (status, result) in enumerate(cases):
                with self.subTest(tool=tool, status=status, result=result):
                    sid = f'{tool}-{i}'
                    hooks.post_tool_call(tool, args={'command': 'python change.py', 'code': 'run()'},
                                        result=result, status=status, session_id=sid)
                    self.assertFalse(state.load(sid)['dirty'])

    def test_failed_readonly_terminal_and_atomic_edits_remain_clean(self):
        for tool, args in [('terminal', {'command': 'git status --short'}),
                           ('patch', {'path': 'bad.py'}), ('write_file', {'path': 'bad.py'})]:
            hooks.post_tool_call(tool, args=args, result={'exit_code': 1, 'error': 'failed'},
                                status='error', session_id=tool)
            self.assertFalse(state.load(tool)['dirty'])
