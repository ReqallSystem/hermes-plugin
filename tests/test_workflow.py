"""Offline workflow contracts; never use real profiles or APIs."""
import importlib
import os
import tempfile
import unittest
from unittest.mock import patch

from reqall import hooks, state, client


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {
            'HOME': self.tmp.name, 'HERMES_HOME': self.tmp.name,
            'XDG_CONFIG_HOME': self.tmp.name, 'REQALL_SKIP_PROFILE_SYNC': '1',
            'REQALL_PROJECT_NAME': 'org/repo',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.network = patch.object(client, 'mcp_call', side_effect=AssertionError('network forbidden'))
        self.network.start()
        self.addCleanup(self.network.stop)

    def test_session_requires_identity_and_selection_reads_exact_spec(self):
        self.assertIsNotNone(importlib.util.find_spec('reqall.workflow'))
        wf = importlib.import_module('reqall.workflow')
        self.assertEqual(wf.handle_session({'action': 'select_intent', 'record_id': 1})['error'], 'needs_session_id')
        state.save('s', dict(state.load('s'), project_id=7, project_name='org/repo'))
        with patch.object(client, 'mcp_call', return_value={'ok': True, 'data': {'record': {'id': 1, 'kind': 'spec', 'project_id': 7}}}) as call:
            result = wf.handle_session({'action': 'select_intent', 'record_id': 1, 'session_id': 'wrong'}, session_id='s')
        self.assertTrue(result['ok'])
        call.assert_called_once_with('get_record', {'id': 1})
        self.assertEqual(state.load('s')['selected_intents'], [1])
        self.assertFalse(state.load('wrong').get('selected_intents'))

    def test_tracking_separates_consultation_and_commitment(self):
        state.save('s', dict(state.load('s'), project_id=7, project_name='org/repo'))
        rec = {'id': 1, 'kind': 'spec', 'project_id': 7}
        hooks.post_tool_call('mcp__reqall__get_record', args={'id': 1}, result={'structuredContent': {'ok': True, 'data': {'record': rec}}}, session_id='s')
        self.assertEqual(state.load('s').get('consulted_records'), [1])
        self.assertFalse(state.load('s').get('selected_intents'))
        hooks.post_tool_call('reqall', args={'action': 'upsert_record', 'arguments': {}}, result={'ok': True, 'data': {'record': rec}}, session_id='s')
        self.assertEqual(state.load('s').get('written_intents'), [1])
        for bad in ({'ok': False, 'data': {'record': dict(rec, id=2)}}, {'ok': True, 'data': {'other': {'record': dict(rec, id=3)}}}, {'ok': True, 'data': {'record': dict(rec, id=4, project_id=8)}}):
            hooks.post_tool_call('reqall', args={'action': 'upsert_record'}, result=bad, session_id='s')
        self.assertEqual(state.load('s')['written_intents'], [1])

    def test_acknowledge_exact_records_links_and_revision(self):
        wf = importlib.import_module('reqall.workflow')
        state.save('s', dict(state.load('s'), project_id=7, project_name='org/repo', dirty=True,
                             selected_intents=[1], written_intents=[2], work_revision=3))
        hooks.post_tool_call('reqall', args={'action': 'upsert_record'}, session_id='s',
                             result={'ok': True, 'data': {'id': 3, 'kind': 'work', 'project_id': 7}})
        links = []
        race = []
        def read(action, args):
            if action == 'get_record':
                rid = args['id']
                return {'ok': True, 'data': {'record': {'id': rid, 'kind': 'spec' if rid < 3 else 'work', 'project_id': 7}}}
            if race:
                state.mark_dirty('s', 'new.py')
            return {'ok': True, 'data': {'links': links, 'total': len(links)}}
        args = {'action': 'acknowledge', 'session_id': 's', 'record_ids': [3], 'work_revision': 3}
        with patch.object(client, 'mcp_call', side_effect=read):
            self.assertFalse(wf.handle_session(args)['ok'])
            self.assertTrue(state.load('s')['dirty'])
            links.extend({'source_id': 3, 'source_table': 'records', 'target_id': n, 'target_table': 'records', 'relationship': 'implements'} for n in (1, 2))
            race.append(True)
            self.assertFalse(wf.handle_session(args)['ok'])
            self.assertTrue(state.load('s')['dirty'])
            race.clear()
            args['work_revision'] = state.load('s')['work_revision']
            self.assertFalse(wf.handle_session(args)['ok'])
            hooks.post_tool_call('reqall', args={'action': 'upsert_record'}, session_id='s',
                                 result={'ok': True, 'data': {'id': 3, 'kind': 'work', 'project_id': 7}})
            self.assertTrue(wf.handle_session(args)['ok'])
        self.assertFalse(state.load('s')['dirty'])
        self.assertEqual(state.load('s')['selected_intents'], [])

    def test_partial_write_stays_pending_and_unavailable_cannot_clear(self):
        wf = importlib.import_module('reqall.workflow')
        state.save('s', dict(state.load('s'), project_id=7, project_name='org/repo'))
        hooks.post_tool_call('reqall', args={'action': 'upsert_record', 'arguments': {'kind': 'spec', 'project_id': 7}},
                             result={'ok': False, 'record_saved': True, 'data': {'id': 9, 'project_id': 7, 'kind': 'spec'}}, session_id='s')
        st = state.load('s')
        self.assertTrue(st['dirty'])
        self.assertEqual(st.get('written_intents'), [9])
        self.assertTrue(st.get('pending_write_failures'))
        self.assertFalse(wf.handle_session({'action': 'acknowledge', 'session_id': 's', 'record_ids': [10], 'work_revision': st['work_revision']})['ok'])
        self.assertTrue(state.load('s')['dirty'])

    def test_project_switch_preserves_pending_separately(self):
        state.save('s', dict(state.load('s'), project_id=7, project_name='old/repo', dirty=True, selected_intents=[1], pending_write_failures=[2]))
        hooks.pre_llm_call(user_message='hi', session_id='s')
        self.assertFalse(state.load('s').get('selected_intents'))
        with patch.dict(os.environ, {'REQALL_PROJECT_NAME': 'old/repo'}):
            hooks.pre_llm_call(user_message='hi', session_id='s')
        self.assertEqual(state.load('s')['selected_intents'], [1])
        self.assertEqual(state.load('s')['pending_write_failures'], [2])
        self.assertTrue(hooks._is_mutating('terminal', {'command': 'git diff --output=a.py'}))

    def test_gap_todo_and_partial_links(self):
        wf = importlib.import_module('reqall.workflow')
        state.save('s', dict(state.load('s'), project_id=7, dirty=True, selected_intents=[1], work_revision=1))
        hooks.post_tool_call('reqall', args={'action': 'upsert_record'}, session_id='s',
                             result={'ok': True, 'data': {'id': 2, 'kind': 'todo', 'status': 'open', 'project_id': 7}})
        total = [2]
        def read(action, args):
            if action == 'get_record':
                rid = args['id']
                return {'ok': True, 'data': {'id': rid, 'kind': 'spec' if rid == 1 else 'todo', 'status': 'open', 'project_id': 7}}
            return {'ok': True, 'data': {'links': [{'source_id': 2, 'source_table': 'records', 'target_id': 1, 'target_table': 'records', 'relationship': 'blocks'}], 'total': total[0]}}
        args = {'action': 'acknowledge', 'session_id': 's', 'record_ids': [2], 'work_revision': 1}
        with patch.object(client, 'mcp_call', side_effect=read):
            self.assertFalse(wf.handle_session(args)['ok'])
            total[0] = 1
            self.assertTrue(wf.handle_session(args)['ok'])

    def test_turn_gate_resets_and_binding_invalidates(self):
        state.mark_dirty('s', 'a.py')
        state.save('s', dict(state.load('s'), project_name='old/repo', project_id=99))
        hooks.pre_llm_call(user_message='hi', session_id='s')
        self.assertIsNone(state.load('s')['project_id'])
        self.assertFalse(state.load('s')['dirty'])
        state.mark_dirty('s', 'new-project.py')
        first = hooks.pre_verify(session_id='s', attempt=0)
        self.assertEqual(first['action'], 'continue')
        self.assertIsNone(hooks.pre_verify(session_id='s', attempt=1))
        self.assertTrue(state.load('s')['dirty'])
        hooks.pre_llm_call(user_message='hi', session_id='s')
        self.assertEqual(hooks.pre_verify(session_id='s', attempt=0)['action'], 'continue')

    def test_host_args_success_failure_shell_and_delegate(self):
        hooks.post_tool_call(tool_name='terminal', args={'command': 'echo hi > code.py'},
                             result={'exit_code': 0}, session_id='s')
        self.assertTrue(state.load('s')['dirty'])
        for result in ({'ok': False}, {'status': 'blocked'}, {'success': False}, {'exit_code': 1}):
            hooks.post_tool_call(tool_name='patch', args={'path': 'bad.py'}, result=result, session_id='failed')
        self.assertFalse(state.load('failed')['dirty'])
        for command in ('git status; touch code.py', 'cat x && rm x', 'echo $(touch x)', 'git branch new'):
            self.assertTrue(hooks._is_mutating('terminal', {'command': command}))
        self.assertFalse(hooks._is_mutating('terminal', {'command': 'git status --short'}))
        hooks.post_tool_call(tool_name='delegate_task', args={'goal': 'implement'}, result={'status': 'completed'}, session_id='delegate')
        self.assertTrue(state.load('delegate')['dirty'])
        self.assertTrue(state.load('delegate')['delegate_activity'])
        self.assertIsNone(hooks.pre_tool_call(tool_name='patch', args={'path': 'a'}, session_id='s'))
