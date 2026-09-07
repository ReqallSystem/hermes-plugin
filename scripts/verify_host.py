#!/usr/bin/env python3
"""Offline smoke test against a real installed Hermes checkout.

Run with Hermes' Python environment, passing the Hermes source root as argv[1].
Does not load enabled plugins or contact Reqall. Uses temporary profile state.
"""
from pathlib import Path
import importlib.util
import json
import os
import socket
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if len(sys.argv) != 2:
    raise SystemExit('usage: verify_host.py HERMES_SOURCE_ROOT')
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(sys.argv[1]).resolve()))

with tempfile.TemporaryDirectory(prefix='reqall-host-') as home:
    with patch.dict(os.environ, {'HOME': home, 'HERMES_HOME': home,
                                 'XDG_CONFIG_HOME': home, 'REQALL_PROJECT_NAME': 'offline/project'}, clear=True), \
         patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')):
        from hermes_cli import plugins, lifecycle
        from agent.turn_context import _collect_pre_llm_call_context
        from model_tools import _emit_post_tool_call_hook

        spec = importlib.util.spec_from_file_location('reqall_host_smoke', ROOT / '__init__.py',
                                                     submodule_search_locations=[str(ROOT)])
        assert spec is not None and spec.loader is not None
        pkg = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = pkg
        spec.loader.exec_module(pkg)
        callbacks, tools, skills = {}, {}, {}
        class Context:
            def register_hook(self, name, callback): callbacks[name] = callback
            def register_tool(self, **kw): tools[kw['name']] = kw
            def register_skill(self, name, skill_path, **kw):
                assert skill_path.is_file()
                skills[name] = kw
            def register_command(self, **kw): pass
            def get_config(self, key): return None
        pkg.register(Context())
        assert set(skills) == {entry[0] for entry in pkg.SKILLS}
        def invoke(name, **kw):
            cb = callbacks.get(name)
            return [cb(**kw)] if cb else []
        with patch.object(plugins, 'invoke_hook', side_effect=invoke), \
             patch.object(lifecycle, '_observe'), \
             patch.object(lifecycle, 'has_hook', side_effect=lambda name: name in callbacks), \
             patch.object(pkg.client, 'mcp_call', side_effect=AssertionError('unexpected API operation')):
            sid = 'host-smoke-session'
            callbacks['on_session_start'](session_id=sid)
            pkg.state.update(sid, lambda st: st.update(project_id=7))
            before = pkg.state.load(sid)
            assert plugins._dispatch_pre_tool_call_hooks('write_file', {'path': 'a.py'}, session_id=sid) == (None, None)
            _emit_post_tool_call_hook(function_name='write_file', function_args={'path': 'a.py'},
                                      result=json.dumps({'success': True}), session_id=sid)
            assert pkg.state.load(sid)['dirty']
            assert pkg.state.load(sid)['touched_paths'] == ['a.py']
            partial = {'ok': False, 'error': 'link_failed', 'record_saved': True,
                       'data': {'id': 1, 'kind': 'spec', 'project_id': 7}}
            _emit_post_tool_call_hook(function_name='reqall', function_args={'action': 'upsert_record'},
                                      result=json.dumps(partial), session_id=sid)
            assert pkg.state.load(sid)['written_intents'] == [1]
            assert pkg.state.load(sid)['pending_write_failures'] == [1]
            assert plugins.get_pre_verify_continue_message(session_id=sid, attempt=0, changed_paths=['a.py'])
            assert plugins.get_pre_verify_continue_message(session_id=sid, attempt=1, changed_paths=['a.py']) is None
            agent = SimpleNamespace(session_id=sid, model='offline', platform='cli')
            context = _collect_pre_llm_call_context(agent, effective_task_id='task', turn_id='turn2',
                original_user_message='hi', messages=[], conversation_history=[])
            assert 'work_revision=' in context and sid in context
            assert plugins.get_pre_verify_continue_message(session_id=sid, attempt=0, changed_paths=['a.py'])
            assert pkg.state.load(sid)['work_revision'] > before.get('work_revision', 0)
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from agent.secret_scope import set_secret_scope, reset_secret_scope, set_multiplex_active, is_multiplex_active
        config = sys.modules[spec.name + '.reqall.config']
        for label in ('a', 'b', 'a'):
            home_token = set_hermes_home_override(Path(home) / label)
            secret_token = set_secret_scope({'REQALL_API_KEY': 'offline-' + label})
            try:
                assert config.api_key() == 'offline-' + label
                existing = pkg.state.load('same-session').get('scope')
                assert existing in (None, label)
                pkg.state.update('same-session', lambda st: st.update(scope=label))
                config.load_plugin_settings({'machine_name': label})
                assert config.machine_name_override() == label
            finally:
                reset_secret_scope(secret_token)
                reset_hermes_home_override(home_token)
        previous_multiplex = is_multiplex_active()
        set_multiplex_active(True)
        empty_token = set_secret_scope({})
        try:
            with patch.dict(os.environ, {'REQALL_API_KEY': 'wrong-process-secret'}):
                assert config.api_key() == ''
        finally:
            reset_secret_scope(empty_token)
            set_multiplex_active(previous_multiplex)
        print(json.dumps({'ok': True, 'real_host_scopes': True, 'host_hooks': ['pre_llm_call', 'pre_tool_call', 'post_tool_call', 'pre_verify'],
                          'tools': sorted(tools), 'skills': sorted(skills), 'network': 'denied', 'state': 'temporary'}))
