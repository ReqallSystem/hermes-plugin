"""Offline foundation regressions; host interfaces are synthetic scopes."""
import contextvars
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from reqall import config, state, client, mcp_status


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.enterContext(mock.patch.dict(os.environ, {
            'HOME': str(self.home), 'HERMES_HOME': str(self.home / 'process'),
            'XDG_CONFIG_HOME': str(self.home / 'xdg'), 'REQALL_SKIP_PROFILE_SYNC': '1',
        }, clear=True))
        self.enterContext(mock.patch('socket.socket.connect', side_effect=AssertionError('offline')))
        self.active = contextvars.ContextVar('test_home', default=self.home / 'a')
        self.secrets = contextvars.ContextVar('test_secrets', default={})
        host = types.ModuleType('hermes_constants')
        host.get_hermes_home = lambda: self.active.get()
        host.get_hermes_home_override = lambda: str(self.active.get())
        secret = types.ModuleType('agent.secret_scope')
        secret.current_secret_scope = lambda: self.secrets.get()
        secret.is_multiplex_active = lambda: True
        secret.get_secret = lambda name, default=None: self.secrets.get().get(name, default)
        self.enterContext(mock.patch.dict(sys.modules, {'hermes_constants': host,
            'agent': types.ModuleType('agent'), 'agent.secret_scope': secret}))

    def test_settings_and_home_follow_active_context(self):
        config.load_plugin_settings({'project_name': 'one', 'doc_interval_min': 2})
        self.assertEqual(config.project_name_override(), 'one')
        self.active.set(self.home / 'b')
        self.assertEqual(config.project_name_override(), '')
        self.assertEqual(config.hermes_home(), self.home / 'b')
        config.load_plugin_settings({'project_name': 'two'})
        self.active.set(self.home / 'a')
        self.assertEqual(config.project_name_override(), 'one')
        self.assertEqual(config.doc_interval_min(), 2)

    def test_scoped_secret_never_uses_shared_cli_auth(self):
        os.environ['REQALL_API_KEY'] = 'wrong'
        self.secrets.set({'MCP_REQALL_API_KEY': 'scoped'})
        self.assertEqual(config.api_key(), 'scoped')
        self.assertEqual(config.api_key_source(), 'MCP_REQALL_API_KEY')
        self.secrets.set({})
        with mock.patch.object(config, '_load_stored_auth', return_value={'api_key': 'shared'}) as stored:
            self.assertEqual(config.api_key(), '')
            self.assertEqual(config.api_key_source(), 'missing')
            stored.assert_not_called()
        self.assertEqual(config.api_key({'REQALL_API_KEY': 'explicit'}), 'explicit')

    def test_state_update_is_transactional_and_profile_isolated(self):
        self.assertTrue(callable(getattr(state, 'update', None)))
        import concurrent.futures
        import multiprocessing
        def bump(_):
            def change(st):
                st['count'] = st.get('count', 0) + 1
            return state.update('session', change)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(bump, range(80)))
        children = [multiprocessing.get_context('fork').Process(target=lambda: [bump(0) for _ in range(20)]) for _ in range(4)]
        for child in children:
            child.start()
        for child in children:
            child.join(10)
            self.assertEqual(child.exitcode, 0)
        self.assertEqual(state.load('session')['count'], 160)
        saved = state.update('session', lambda st: st.update({'legacy': 'kept'}))
        self.assertEqual(saved, state.load('session'))
        self.assertTrue((self.home / 'a/reqall/sessions/session.json').exists())
        self.active.set(self.home / 'b')
        self.assertNotIn('count', state.load('session'))

    def test_dirty_revision_and_nudge_transaction(self):
        state.update('s', lambda st: st.update({'persist_nudge_sent': True, 'unknown': 7}))
        self.assertEqual(state.mark_dirty('s', 'a').get('work_revision'), 1)
        self.assertEqual(state.mark_dirty('s', 'b')['work_revision'], 2)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(lambda _: state.should_nudge('s', 'doc', 10), range(30)))
        self.assertEqual(sum(outcomes), 1)
        state.clear_dirty('s')
        saved = state.load('s')
        self.assertFalse(saved['persist_nudge_sent'])
        self.assertFalse(saved['dirty'])
        self.assertEqual(saved['unknown'], 7)
        self.assertEqual(saved['touched_paths'], [])

    def test_normalization_rejects_semantic_errors_and_empty_results(self):
        self.assertTrue(callable(getattr(client, 'normalize_result', None)))
        for payload in (None, '', {}, {'result': {}}, {'result': {'isError': True, 'content': [{'text': 'denied'}]}}, {'error': {'code': -1}}, {'ok': False, 'error': 'bad'}):
            with self.subTest(payload=payload):
                self.assertFalse(client.normalize_result(payload)['ok'])
        payload = json.dumps({'result': {'content': [{'text': 'Saved record'}], 'structuredContent': {'ok': True, 'data': {'record': {'id': 3, 'title': 'saved'}}}}})
        result = client.normalize_result(payload)
        self.assertTrue(result['ok'])
        self.assertEqual(result['data']['id'], 3)
        self.assertTrue(client.normalize_result({'result': {'content': [{'text': '[]'}]}})['ok'])
        self.assertFalse(client.normalize_result({'result': {'content': [{'text': '{"ok":false,"error":"denied"}'}]}})['ok'])
        partial = {'ok': True, 'record_saved': True, 'data': {'id': 3}, 'links': [{'ok': False, 'error': 'denied'}]}
        result = client.normalize_result(partial)
        self.assertFalse(result['ok'])
        self.assertTrue(result['record_saved'])
        self.assertEqual(result['links'], partial['links'])

    def test_sse_rejects_mismatched_ids(self):
        raw = 'data: {"id":"other","result":{"id":1}}\n\n'
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            client.parse_sse_jsonrpc(raw, 'wanted')
        self.assertEqual(client.parse_sse_jsonrpc(raw, 'other')['id'], 'other')

    def test_mcp_probe_uses_only_canonical_discovery(self):
        canonical = types.ModuleType('tools.mcp_tool_discovery')
        canonical.get_registered_mcp_server_names = lambda: {'Reqall'}
        with mock.patch.dict(sys.modules, {'tools': types.ModuleType('tools'), 'tools.mcp_tool_discovery': canonical, 'tools.mcp_tool': None}):
            self.assertTrue(mcp_status.probe_mcp_host()['host_mcp_registered'])
        self.assertNotIn('from tools.mcp_tool import', Path(mcp_status.__file__).read_text())

    def test_machine_and_endpoint_settings_are_profile_local(self):
        config.load_plugin_settings({'machine_name': 'desktop', 'api_url': 'https://example.invalid/'})
        self.assertEqual(config.api_url(), 'https://example.invalid')
        self.assertEqual(config.machine_name_override(), 'desktop')
        self.active.set(self.home / 'b')
        self.assertEqual(config.api_url(), config.DEFAULT_URL)
        self.assertEqual(config.machine_name_override(), '')
        self.assertEqual(config.machine_name_override({'REQALL_MACHINE_NAME': 'explicit'}), 'explicit')
        self.assertEqual(config.api_url({'REQALL_URL': 'https://other.invalid/'}), 'https://other.invalid')

    def test_nested_inline_links_action_error_is_partial_save(self):
        payload = {'result': {'structuredContent': {'ok': True, 'data': {
            'record': {'id': 9, 'project_id': 2},
            'links': [{'action': 'created', 'id': 1}, {'action': 'error'}],
        }}}}
        result = client.normalize_result(payload)
        self.assertFalse(result['ok'])
        self.assertTrue(result['record_saved'])
        self.assertEqual(result['data']['id'], 9)
        self.assertEqual(len(result['links']), 2)

    def test_http_transport_uses_typed_normalization_without_retry(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.headers = {'Content-Type': 'application/json'}
        response.read.return_value = json.dumps({'result': {'isError': True, 'content': [{'text': 'denied'}]}}).encode()
        with mock.patch.object(client.urllib.request, 'urlopen', return_value=response) as request:
            result = client.mcp_call('upsert_record', {'title': 'test'}, env={'REQALL_API_KEY': 'offline'})
        self.assertFalse(result['ok'])
        request.assert_called_once()

    def test_failed_mutator_and_failed_write_do_not_publish_state(self):
        state.update('s', lambda st: st.update({'original': True}))
        original = state.load('s')
        def fail(st):
            st['original'] = False
            raise ValueError('mutator failed')
        with self.assertRaises(ValueError):
            state.update('s', fail)
        self.assertEqual(state.load('s'), original)
        with mock.patch.object(state.os, 'replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                state.update('s', lambda st: st.update({'original': False}))
        self.assertEqual(state.load('s'), original)

    def test_standalone_home_and_unscoped_multiplex_fail_closed(self):
        with mock.patch.dict(sys.modules, {'hermes_constants': None}):
            self.assertEqual(config.hermes_home(), self.home / 'process')
            os.environ.pop('HERMES_HOME')
            self.assertEqual(config.hermes_home(), self.home / '.hermes')
        secret = sys.modules['agent.secret_scope']
        with mock.patch.object(secret, 'get_secret', side_effect=RuntimeError('unscoped')):
            with mock.patch.object(config, '_load_stored_auth') as stored:
                self.assertEqual(config.api_key(), '')
                stored.assert_not_called()


if __name__ == '__main__':
    unittest.main()
