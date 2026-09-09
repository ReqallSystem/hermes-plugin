"""Plugin wiring regressions; no host registration or network."""
import json
import os
import tempfile
import unittest
from unittest import mock
from test_plugin import _load


class Context:
    def __init__(self):
        self.tools = {}
        self.hooks = {}
        self.skills = {}

    def register_hook(self, name, handler):
        self.hooks[name] = handler

    def register_tool(self, **kwargs):
        self.tools[kwargs['name']] = kwargs

    def register_command(self, **kwargs):
        pass

    def register_skill(self, name, path, description=''):
        self.skills[name] = path

    def get_config(self, name):
        return None


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = mock.patch.dict(os.environ, {
            'HOME': self.tmp.name, 'HERMES_HOME': self.tmp.name,
            'XDG_CONFIG_HOME': self.tmp.name,
        }, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.pkg = _load()

    def test_registers_session_tool_with_explicit_acknowledgement_fields(self):
        ctx = Context()
        self.pkg.register(ctx)
        self.assertIn('reqall_session', ctx.tools)
        schema = ctx.tools['reqall_session']['schema']['parameters']
        self.assertIn('work_revision', schema['properties'])
        self.assertIn('record_ids', schema['properties'])
        self.assertIn('session_id', schema['properties'])

    def test_status_reads_actual_session_not_default(self):
        with mock.patch.object(self.pkg, 'probe_mcp_host', return_value={}), mock.patch.object(self.pkg, 'missing_enabled_homes', return_value=[]), mock.patch.object(self.pkg, 'api_key', return_value=''), mock.patch.object(self.pkg.state, 'load', return_value={'session_id': 'actual'}) as load:
            result = json.loads(self.pkg._handle_status({}, session_id='actual'))
        load.assert_called_once_with('actual')
        self.assertEqual(result['session']['session_id'], 'actual')

    def test_clear_dirty_cannot_bypass_verified_acknowledgement(self):
        with mock.patch.object(self.pkg.state, 'clear_dirty') as clear:
            result = self.pkg._slash_reqall('clear-dirty')
        clear.assert_not_called()
        self.assertIn('acknowledge', result)

    def test_auth_check_is_read_only_even_when_project_bound(self):
        with mock.patch.object(self.pkg, 'probe_mcp_host', return_value={}), mock.patch.object(self.pkg, 'missing_enabled_homes', return_value=[]), mock.patch.object(self.pkg, 'api_key', return_value='fake-key'), mock.patch.object(self.pkg.client, 'upsert_project') as upsert, mock.patch.object(self.pkg.client, 'mcp_call', return_value={'ok': True, 'data': []}) as call:
            result = json.loads(self.pkg._handle_status({'check_auth': True}))
        upsert.assert_not_called()
        call.assert_called_once_with('list_projects', {'limit': 1})
        self.assertTrue(result['auth_check']['ok'])

    def test_intend_skill_is_discoverable(self):
        names = [name for name, _, _ in self.pkg.SKILLS]
        self.assertIn('reqall-intend', names)
        self.assertIsNotNone(self.pkg.resolve_skill('intend'))

    def test_slash_intend_loads_bundled_skill(self):
        body = self.pkg._slash_reqall('intend')
        self.assertIn('# Capture Intent', body)
        self.assertIn('select_intent', body)

    def test_registration_loads_scoped_machine_and_api_settings(self):
        ctx = Context()
        ctx.get_config = lambda name: {'machine_name': 'stable-box', 'api_url': 'https://example.invalid'}.get(name)
        with mock.patch.object(self.pkg, 'load_plugin_settings') as load:
            self.pkg.register(ctx)
        self.assertEqual(load.call_args.args[0].get('machine_name'), 'stable-box')
        self.assertEqual(load.call_args.args[0].get('api_url'), 'https://example.invalid')

    def test_registration_never_installs_other_profiles(self):
        with mock.patch.object(self.pkg, 'ensure_installs') as install:
            self.pkg.register(Context())
        install.assert_not_called()


if __name__ == '__main__':
    unittest.main()
