"""Offline explicit-project recovery through the real result observer."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from reqall import client, hooks, state, workflow


class ProjectRecoveryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict(os.environ, {'HOME': tmp.name, 'HERMES_HOME': tmp.name,
                         'XDG_CONFIG_HOME': tmp.name, 'REQALL_SKIP_PROFILE_SYNC': '1',
                         'REQALL_PROJECT_NAME': 'org/repo'})
        env.start()
        self.addCleanup(env.stop)
        network = patch.object(client, 'mcp_call', side_effect=AssertionError('network forbidden'))
        network.start()
        self.addCleanup(network.stop)

    def success(self, name='org/repo', pid=7):
        return {'ok': True, 'data': {'action': 'created_or_found',
                                   'project': {'id': pid, 'name': name}}}

    def observe(self, result=None, name='org/repo', tool='reqall', **kwargs):
        args = {'name': name}
        if tool == 'reqall':
            args = {'action': 'upsert_project', 'arguments': args}
        hooks.post_tool_call(tool, args=args, result=self.success() if result is None else result,
                             session_id='s', **kwargs)

    def test_requires_typed_success_envelope(self):
        malformed = [
            {'project': {'id': 7, 'name': 'org/repo'}},
            {'ok': True, 'data': {'project': {'id': 7, 'name': 'org/repo'}}},
            {'ok': True, 'data': {'action': 'unrelated', 'project': {'id': 7, 'name': 'org/repo'}}},
            {'ok': 1, 'data': self.success()['data']},
        ]
        for result in malformed:
            with self.subTest(result=result):
                state.save('s', {'project_name': 'org/repo', 'project_id': None})
                self.observe(result)
                self.assertIsNone(state.load('s')['project_id'])

    def test_request_id_must_match_returned_identity(self):
        state.save('s', {'project_name': 'org/repo', 'project_id': None})
        hooks.post_tool_call('reqall', args={'action': 'upsert_project',
            'arguments': {'name': 'org/repo', 'id': 8}}, result=self.success(), session_id='s')
        self.assertIsNone(state.load('s')['project_id'])

    def test_mismatch_failure_and_untyped_identity_do_not_bind(self):
        cases = [
            (self.success('other/repo'), 'org/repo', 'org/repo'),
            (self.success(), 'other/repo', 'org/repo'),
            (self.success(), 'org/repo', 'other/repo'),
            (self.success(), 'org/repo', None),
            (self.success('Org/repo'), 'org/repo', 'org/repo'),
            (self.success(), ' org/repo', 'org/repo'),
            (dict(self.success(), ok=False), 'org/repo', 'org/repo'),
            (dict(self.success(), success=False), 'org/repo', 'org/repo'),
            (dict(self.success(), status='partial'), 'org/repo', 'org/repo'),
            ({'structuredContent': self.success(), 'isError': True}, 'org/repo', 'org/repo'),
            ({'ok': True, 'data': {'action': 'created_or_found', 'other': self.success()['data']}}, 'org/repo', 'org/repo'),
            ('Project org/repo (#7)', 'org/repo', 'org/repo'),
            (self.success(pid=True), 'org/repo', 'org/repo'),
            (self.success(pid='7'), 'org/repo', 'org/repo'),
        ]
        for result, request, binding in cases:
            with self.subTest(result=result, request=request, binding=binding):
                state.save('s', {'project_name': binding, 'project_id': None, 'dirty': True})
                self.observe(result, name=request)
                self.assertIsNone(state.load('s')['project_id'])
                self.assertTrue(state.load('s')['dirty'])

    def test_native_and_mcp_envelopes_preserve_pending_state(self):
        for tool in ('reqall', 'mcp__reqall__upsert_project', 'mcp__Reqall__UPSERT_PROJECT'):
            for action in ('created_or_found', 'matched_existing', 'updated'):
                with self.subTest(tool=tool, action=action):
                    pending = {'project_name': 'org/repo', 'project_id': None, 'dirty': True,
                        'selected_intents': [1], 'written_intents': [2], 'pending_write_failures': [3],
                        'outcome_records': [4], 'outcome_revisions': {'4': 8}, 'work_revision': 8,
                        'ledger_revision': 9, 'touched_paths': ['a.py'], 'project_workflows': {'old': {'dirty': True}}}
                    state.save('s', pending)
                    result = self.success()
                    result['data']['action'] = action
                    self.observe(json.dumps({'jsonrpc': '2.0', 'result': {'structuredContent': result,
                        'content': [{'type': 'text', 'text': 'Project org/repo (#7)'}]}}), tool=tool)
                    after = state.load('s')
                    self.assertEqual(after['project_id'], 7)
                    for key, value in pending.items():
                        if key != 'project_id':
                            self.assertEqual(after[key], value)
        for existing in (7, 8):
            state.save('s', {'project_name': 'org/repo', 'project_id': existing, 'dirty': True})
            self.observe()
            self.assertEqual(state.load('s')['project_id'], existing)
        state.save('s', {'project_name': 'org/repo', 'project_id': None})
        self.observe(status='failed')
        self.assertIsNone(state.load('s')['project_id'])
        self.observe(tool='mcp__other__upsert_project')
        self.assertIsNone(state.load('s')['project_id'])

    def test_recovery_checks_latest_binding_and_preserves_concurrent_work(self):
        update = state.update
        for race in ({'project_name': 'other/repo', 'project_id': None},
                     {'project_id': 8}, {'pending_write_failures': [99], 'work_revision': 12}):
            with self.subTest(race=race):
                state.save('s', {'project_name': 'org/repo', 'project_id': None})
                def raced(sid, mutator):
                    update(sid, lambda current: current.update(race))
                    return update(sid, mutator)
                with patch.object(state, 'update', side_effect=raced):
                    self.observe()
                after = state.load('s')
                for key, value in race.items():
                    self.assertEqual(after[key], value)
                if 'pending_write_failures' in race:
                    self.assertEqual(after['project_id'], 7)

    def test_failed_initialization_recovers_through_verified_ack(self):
        with patch.object(client, 'upsert_project', return_value={'ok': False, 'error': 'offline'}), \
             patch.object(client, 'search', return_value={'ok': True, 'data': []}):
            hooks.pre_llm_call(user_message='fix project recovery', session_id='s')
        self.assertEqual(state.load('s')['project_name'], 'org/repo')
        self.assertIsNone(state.load('s')['project_id'])
        self.observe()
        self.assertEqual(state.load('s')['project_id'], 7)
        records = {1: {'id': 1, 'kind': 'spec', 'project_id': 7},
                   2: {'id': 2, 'kind': 'work', 'project_id': 7}}
        hooks.post_tool_call('reqall', args={'action': 'upsert_record'},
                             result={'ok': True, 'data': {'record': records[1]}}, session_id='s')
        self.assertEqual(state.load('s')['written_intents'], [1])
        reads = []
        def read(action, args):
            reads.append((action, args))
            if action == 'get_record':
                return {'ok': True, 'data': {'record': records[args['id']]}}
            self.assertEqual(action, 'list_links')
            return {'ok': True, 'data': {'links': [{'source_id': 2, 'source_table': 'records',
                'target_id': 1, 'target_table': 'records', 'relationship': 'implements'}], 'total': 1}}
        with patch.object(client, 'mcp_call', side_effect=read):
            self.assertTrue(workflow.handle_session({'action': 'select_intent', 'record_id': 1}, session_id='s')['ok'])
            hooks.post_tool_call('reqall', args={'action': 'upsert_record'},
                                 result={'ok': True, 'data': {'record': records[2]}}, session_id='s')
            st = state.load('s')
            self.assertEqual(st['outcome_records'], [2])
            self.assertTrue(workflow.handle_session({'action': 'acknowledge', 'record_ids': [2],
                'work_revision': st['work_revision']}, session_id='s')['ok'])
        self.assertEqual([a for a, _ in reads], ['get_record', 'get_record', 'get_record', 'list_links'])
        self.assertFalse(state.load('s')['dirty'])
        self.assertEqual(state.load('s')['acknowledged_record_ids'], [2])
