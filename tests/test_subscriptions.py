"""Offline contracts for project subscriptions: subscribe once, poll per turn, fail open."""
import os
import tempfile
import unittest
from unittest.mock import patch

from reqall import client, hooks, state


def _poll(events, project='org/repo', has_more=False):
    return {'ok': True, 'data': {'total_events': len(events), 'results': [
        {'subscription': {'project_id': 7, 'project_name': project, 'subscriber': 's', 'cursor': 9},
         'events': events, 'has_more': has_more}]}}


def _ev(action, rid, actor='other', title='T', kind='todo'):
    return {'id': 1, 'project_id': 7, 'action': action, 'record_id': rid, 'kind': kind, 'title': title, 'actor': actor, 'created_at': 'now'}


class SubscriptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {'HOME': self.tmp.name, 'HERMES_HOME': self.tmp.name,
                                      'XDG_CONFIG_HOME': self.tmp.name, 'REQALL_SKIP_PROFILE_SYNC': '1',
                                      'REQALL_PROJECT_NAME': 'org/repo'})
        env.start()
        self.addCleanup(env.stop)
        self.calls = []

    PROJECT_IDS = {'org/repo': 7, 'org/other': 8}

    def _router(self, poll=None, subscribe=None, project=True, unsubscribe=None):
        def call(tool, args=None, env=None, timeout=None):
            self.calls.append((tool, args or {}))
            if tool == 'upsert_project':
                name = (args or {}).get('name')
                return {'ok': project, 'data': {'action': 'created_or_found',
                                                'project': {'id': self.PROJECT_IDS.get(name, 7), 'name': name}}}
            if tool == 'search':
                return {'ok': True, 'data': []}
            if tool == 'list_records':
                return {'ok': True, 'data': {'records': []}}
            if tool == 'subscribe_project':
                return subscribe or {'ok': True, 'data': {'action': 'created', 'subscription': {'project_id': 7, 'cursor': 9}}}
            if tool == 'poll_subscriptions':
                return poll or _poll([])
            if tool == 'unsubscribe_project':
                return unsubscribe or {'ok': True, 'data': {'removed': 1}}
            raise AssertionError(f'unexpected tool {tool}')
        return call

    def _tools(self, name):
        return [t for t, _ in self.calls if t == name]

    def test_format_updates_hides_own_writes_and_renders_others(self):
        poll = _poll([_ev('record.created', 1, actor='self', title='Mine'),
                      _ev('record.updated', 2, actor='self', title='Other session of mine'),
                      _ev('record.deleted', 3, title='Teammate delete', kind='spec'),
                      _ev('sleep.applied', None, actor='unknown', title='SLEEP applied 2 operation(s)', kind=None)], has_more=True)
        text = client.format_updates(poll, own_record_ids=[1])
        self.assertIn('## Reqall updates since last turn', text)
        self.assertNotIn('Mine', text, 'this session wrote record 1')
        self.assertIn('record.updated #2 [todo] (you, another session): Other session of mine', text)
        self.assertIn('org/repo: record.deleted #3 [spec]: Teammate delete', text)
        self.assertIn('sleep.applied: SLEEP applied 2 operation(s)', text)
        self.assertIn('more pending', text)
        self.assertIsNone(client.format_updates(_poll([_ev('record.created', 1, actor='self')]), own_record_ids=[1]))
        self.assertIsNone(client.format_updates({'ok': False, 'error': 'network'}))
        self.assertIsNone(client.format_updates({'ok': True, 'data': {'results': 'garbage'}}))

    def test_turn_subscribes_once_then_polls_each_turn(self):
        with patch.object(client, 'mcp_call', side_effect=self._router()):
            first = hooks.pre_llm_call(user_message='implement the widget', session_id='s')
        self.assertEqual(self._tools('subscribe_project'), ['subscribe_project'])
        self.assertEqual(self._tools('poll_subscriptions'), ['poll_subscriptions'])
        sub_args = next(a for t, a in self.calls if t == 'subscribe_project')
        self.assertEqual(sub_args, {'project_id': 7, 'subscriber': 's'})
        poll_args = next(a for t, a in self.calls if t == 'poll_subscriptions')
        self.assertEqual(poll_args, {'subscriber': 's', 'limit': client.POLL_LIMIT, 'project_id': 7},
                         'poll is scoped to the bound project')
        self.assertEqual(state.load('s')['subscribed_project_id'], 7)
        self.assertNotIn('Reqall updates', first['context'], 'quiet poll injects nothing')

        self.calls.clear()
        hooks.post_tool_call('reqall', args={'action': 'upsert_record'}, session_id='s',
                             result={'ok': True, 'data': {'record': {'id': 5, 'kind': 'work', 'project_id': 7}}})
        poll = _poll([_ev('record.created', 5, actor='self', title='My own write'),
                      _ev('record.updated', 6, title='Teammate change')])
        with patch.object(client, 'mcp_call', side_effect=self._router(poll=poll)):
            second = hooks.pre_llm_call(user_message='thanks, continue', session_id='s')
        self.assertEqual(self._tools('subscribe_project'), [], 'already subscribed')
        self.assertEqual(self._tools('poll_subscriptions'), ['poll_subscriptions'])
        self.assertIn('Teammate change', second['context'])
        self.assertNotIn('My own write', second['context'])
        self.assertIn('session_id=s', second['context'])

    def test_trivial_turn_without_project_does_not_touch_network(self):
        with patch.object(client, 'mcp_call', side_effect=AssertionError('network forbidden')):
            self.assertIsNone(hooks.pre_llm_call(user_message='hi', session_id='fresh'))

    def test_project_switch_releases_old_cursor_and_polls_only_the_new_project(self):
        with patch.object(client, 'mcp_call', side_effect=self._router()):
            hooks.pre_llm_call(user_message='implement the widget', session_id='s')
        self.calls.clear()
        with patch.dict(os.environ, {'REQALL_PROJECT_NAME': 'org/other'}), \
             patch.object(client, 'mcp_call', side_effect=self._router()):
            hooks.pre_llm_call(user_message='implement the other widget', session_id='s')
        ordered = [(t, a) for t, a in self.calls if t in {'unsubscribe_project', 'subscribe_project', 'poll_subscriptions'}]
        self.assertEqual(ordered, [
            ('unsubscribe_project', {'project_id': 7, 'subscriber': 's'}),
            ('subscribe_project', {'project_id': 8, 'subscriber': 's'}),
            ('poll_subscriptions', {'subscriber': 's', 'limit': client.POLL_LIMIT, 'project_id': 8}),
        ], 'old cursor released before the new one exists; poll never sees project 7')
        self.assertNotIn('stale_subscriptions', state.load('s'))
        self.assertEqual(state.load('s')['subscribed_project_id'], 8)

    def test_stale_cursor_survives_a_failed_release_until_it_succeeds(self):
        with patch.object(client, 'mcp_call', side_effect=self._router()):
            hooks.pre_llm_call(user_message='implement the widget', session_id='s')
        failing = {'ok': False, 'error': 'network'}
        with patch.dict(os.environ, {'REQALL_PROJECT_NAME': 'org/other'}), \
             patch.object(client, 'mcp_call', side_effect=self._router(unsubscribe=failing)):
            hooks.pre_llm_call(user_message='implement the other widget', session_id='s')
        self.assertEqual(state.load('s')['stale_subscriptions'], [7], 'kept for a later attempt')
        self.assertEqual(state.load('s')['subscribed_project_id'], 8)
        self.calls.clear()
        with patch.object(client, 'mcp_call', side_effect=self._router(unsubscribe=failing)):
            hooks.on_session_end(session_id='s')
        self.assertEqual(state.load('s')['stale_subscriptions'], [7])
        self.assertEqual(state.load('s')['subscribed_project_id'], 8, 'nothing forgotten while the server still holds it')
        self.calls.clear()
        with patch.object(client, 'mcp_call', side_effect=self._router()):
            hooks.on_session_finalize(session_id='s')
        self.assertEqual([a['project_id'] for t, a in self.calls if t == 'unsubscribe_project'], [7, 8])
        self.assertNotIn('stale_subscriptions', state.load('s'))
        self.assertNotIn('subscribed_project_id', state.load('s'))

    def test_older_server_without_subscriptions_is_silent_and_remembered(self):
        missing = {'ok': False, 'error': {'code': -32602, 'message': 'Tool subscribe_project not found'}}
        with patch.object(client, 'mcp_call', side_effect=self._router(subscribe=missing)):
            out = hooks.pre_llm_call(user_message='implement the widget', session_id='s')
        self.assertIn('Reqall context', out['context'])
        self.assertTrue(state.load('s')['subscriptions_unavailable'])
        self.assertEqual(self._tools('poll_subscriptions'), [])
        self.calls.clear()
        with patch.object(client, 'mcp_call', side_effect=self._router()):
            hooks.pre_llm_call(user_message='implement more', session_id='s')
        self.assertEqual(self._tools('subscribe_project'), [], 'does not retry an unsupported tool every turn')

    def test_transient_failures_fail_open_and_retry_next_turn(self):
        transient = {'ok': False, 'error': 'network', 'detail': 'timeout'}
        with patch.object(client, 'mcp_call', side_effect=self._router(subscribe=transient)):
            out = hooks.pre_llm_call(user_message='implement the widget', session_id='s')
        self.assertIn('Reqall context', out['context'])
        self.assertIsNone(state.load('s').get('subscribed_project_id'))
        self.assertFalse(state.load('s').get('subscriptions_unavailable'))
        self.calls.clear()
        with patch.object(client, 'mcp_call', side_effect=self._router(poll={'ok': False, 'error': 'network'})):
            out = hooks.pre_llm_call(user_message='implement more', session_id='s')
        self.assertEqual(self._tools('subscribe_project'), ['subscribe_project'])
        self.assertNotIn('Reqall updates', out['context'])

    def test_session_end_releases_the_cursor(self):
        with patch.object(client, 'mcp_call', side_effect=self._router()):
            hooks.pre_llm_call(user_message='implement the widget', session_id='s')
        self.calls.clear()
        with patch.object(client, 'mcp_call', side_effect=self._router()):
            hooks.on_session_end(session_id='s')
        self.assertEqual([a for t, a in self.calls if t == 'unsubscribe_project'], [{'project_id': 7, 'subscriber': 's'}])
        self.assertNotIn('subscribed_project_id', state.load('s'))
        self.calls.clear()
        with patch.object(client, 'mcp_call', side_effect=AssertionError('network forbidden')):
            hooks.on_session_end(session_id='s')
        with patch.object(client, 'mcp_call', side_effect=RuntimeError('boom')):
            hooks.on_session_finalize(session_id='s')

    def test_plugin_action_tool_exposes_subscription_ops(self):
        import importlib.util, sys
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location('hermes_reqall_sub_test', root / '__init__.py', submodule_search_locations=[str(root)])
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = 'hermes_reqall_sub_test'
        mod.__path__ = [str(root)]
        sys.modules['hermes_reqall_sub_test'] = mod
        spec.loader.exec_module(mod)
        for op in ('subscribe_project', 'unsubscribe_project', 'list_subscriptions', 'poll_subscriptions'):
            self.assertIn(op, mod.REQALL_ACTIONS)
        # Manual controls default the cursor label to the session; an explicit one wins.
        with patch.object(mod.client, 'mcp_call', return_value={'ok': True, 'data': {}}) as call:
            mod._handle_reqall_action({'action': 'poll_subscriptions', 'arguments': {}}, session_id='host-sess')
            mod._handle_reqall_action({'action': 'subscribe_project', 'arguments': {'project_id': 7, 'subscriber': 'ide'}}, session_id='host-sess')
            mod._handle_reqall_action({'action': 'unsubscribe_project', 'arguments': {'project_id': 7}, 'session_id': 'arg-sess'})
            mod._handle_reqall_action({'action': 'list_subscriptions', 'arguments': {}}, session_id='host-sess')
            mod._handle_reqall_action({'action': 'poll_subscriptions', 'arguments': {}})
        self.assertEqual([c.args for c in call.call_args_list], [
            ('poll_subscriptions', {'subscriber': 'host-sess'}),
            ('subscribe_project', {'project_id': 7, 'subscriber': 'ide'}),
            ('unsubscribe_project', {'project_id': 7, 'subscriber': 'arg-sess'}),
            ('list_subscriptions', {}),
            ('poll_subscriptions', {}),
        ])


if __name__ == '__main__':
    unittest.main()
