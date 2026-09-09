"""Offline regression tests for project and reconciliation races."""
import os
import socket
import tempfile
import unittest
from unittest.mock import patch

from reqall import client, hooks, state, workflow


class ReconciliationEdgesTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for guard in (
            patch.dict(os.environ, {'HOME': tmp.name, 'HERMES_HOME': tmp.name,
                                   'XDG_CONFIG_HOME': tmp.name,
                                   'REQALL_SKIP_PROFILE_SYNC': '1',
                                   'REQALL_PROJECT_NAME': 'org/a'}, clear=True),
            patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')),
            patch.object(client, 'mcp_call', side_effect=AssertionError('network forbidden')),
        ):
            guard.start()
            self.addCleanup(guard.stop)
        state.update('s', lambda st: st.update(project_name='org/a', project_id=7))

    def write_record(self, rid=10, kind='work', **fields):
        record = dict(id=rid, kind=kind, project_id=7, **fields)
        hooks.post_tool_call('reqall', args={'action': 'upsert_record'},
                             result={'ok': True, 'data': {'record': record}}, session_id='s')
        return record

    def acknowledge(self, ids, read, revision=None):
        if revision is None:
            revision = state.load('s').get('work_revision', 0)
        with patch.object(client, 'mcp_call', side_effect=read):
            return workflow.handle_session({'action': 'acknowledge', 'session_id': 's',
                                            'record_ids': ids, 'work_revision': revision})

    def test_concurrent_outcome_rewrite_cannot_clear_and_snapshot_precedes_persist(self):
        state.mark_dirty('s', 'a.py')
        revision = state.load('s')['work_revision']
        rec = self.write_record()
        self.assertEqual(state.load('s')['work_revision'], revision)
        race = [True]
        def read(action, args):
            if action == 'get_record':
                return {'ok': True, 'data': rec}
            if race:
                self.write_record(body='changed during acknowledgement')
            return {'ok': True, 'data': {'links': [], 'total': 0}}
        self.assertFalse(self.acknowledge([10], read, revision)['ok'])
        self.assertTrue(state.load('s')['dirty'])
        race.clear()
        self.assertTrue(self.acknowledge([10], read, revision)['ok'])

    def test_subset_ack_retains_unverified_current_batch(self):
        state.mark_dirty('s', 'a.py')
        records = {rid: self.write_record(rid) for rid in (10, 11)}
        reads = []
        def read(action, args):
            if action == 'get_record':
                reads.append(args['id'])
                return {'ok': True, 'data': records[args['id']]}
            return {'ok': True, 'data': {'links': [], 'total': 0}}
        before = state.load('s')
        result = self.acknowledge([10], read)
        self.assertFalse(result['ok'])
        self.assertEqual(result['error'], 'unverified_batch_outcomes')
        self.assertEqual(result['record_ids'], [11])
        self.assertEqual(state.load('s'), before)
        records[11]['project_id'] = 8
        self.assertFalse(self.acknowledge([10, 11], read)['ok'])
        self.assertTrue(state.load('s')['dirty'])
        records[11]['project_id'] = 7
        self.assertTrue(self.acknowledge([10, 11], read)['ok'])
        self.assertIn(11, reads)
        self.assertEqual(state.load('s')['acknowledged_record_ids'], [10, 11])

    def test_new_batch_can_supersede_old_outcomes_without_reupserting_them(self):
        state.mark_dirty('s', 'a.py')
        self.write_record(10)
        state.mark_dirty('s', 'b.py')
        rec = self.write_record(11, body='Consolidated outcome for all work')
        def read(action, args):
            if action == 'get_record':
                self.assertEqual(args['id'], 11)
                return {'ok': True, 'data': rec}
            return {'ok': True, 'data': {'links': [], 'total': 0}}
        self.assertEqual(self.acknowledge([10, 11], read)['error'], 'stale_outcome')
        self.assertTrue(self.acknowledge([11], read)['ok'])
        self.assertFalse(state.load('s')['dirty'])

    def test_old_outcome_requires_same_id_reupsert_for_new_work(self):
        state.mark_dirty('s', 'a.py')
        rec = self.write_record()
        def read(action, args):
            return {'ok': True, 'data': rec if action == 'get_record' else {'links': [], 'total': 0}}
        state.mark_dirty('s', 'b.py')
        self.assertFalse(self.acknowledge([10], read)['ok'])
        self.assertTrue(state.load('s')['dirty'])
        self.write_record(body='Includes the new work')
        st = state.load('s')
        self.assertEqual(st['outcome_records'], [10])
        self.assertEqual(st['outcome_revisions'], {'10': st['work_revision']})
        self.assertTrue(self.acknowledge([10], read)['ok'])
        self.assertEqual(state.load('s')['outcome_revisions'], {})

    def test_resolved_arch_acknowledges_design_with_prewrite_snapshot(self):
        state.mark_dirty('s', 'design discussion')
        revision = state.load('s')['work_revision']
        rec = self.write_record(12, kind='arch', status='resolved')
        def read(action, args):
            return {'ok': True, 'data': rec if action == 'get_record' else {'links': [], 'total': 0}}
        self.assertEqual(state.load('s')['work_revision'], revision)
        self.assertEqual(state.load('s').get('written_intents', []), [])
        self.assertTrue(self.acknowledge([12], read, revision)['ok'])
        self.assertFalse(state.load('s')['dirty'])

    def test_arch_outcome_revalidates_status_and_kind(self):
        state.mark_dirty('s', 'design discussion')
        rec = self.write_record(12, kind='arch', status='resolved')
        def read(action, args):
            return {'ok': True, 'data': rec if action == 'get_record' else {'links': [], 'total': 0}}
        for kind, status in [('arch', 'open'), ('arch', None), ('arch', 'closed'),
                             ('spec', 'resolved')]:
            with self.subTest(kind=kind, status=status):
                rec.update(kind=kind, status=status)
                self.assertEqual(self.acknowledge([12], read)['error'], 'unverified_outcome')
                self.assertTrue(state.load('s')['dirty'])
        rec.update(kind='arch', status='resolved')
        self.assertTrue(self.acknowledge([12], read)['ok'])

    def test_resolved_arch_must_cover_other_pending_intent(self):
        state.update('s', lambda st: st.update(selected_intents=[1], dirty=True))
        rec = self.write_record(12, kind='arch', status='resolved')
        links = []
        def read(action, args):
            if action == 'get_record':
                return {'ok': True, 'data': rec if args['id'] == 12 else
                        {'id': 1, 'kind': 'spec', 'status': 'open', 'project_id': 7}}
            return {'ok': True, 'data': {'links': links, 'total': len(links)}}
        self.assertEqual(self.acknowledge([12], read)['error'], 'unreconciled_intent')
        links.append({'source_id': 12, 'source_table': 'records', 'target_id': 1,
                      'target_table': 'records', 'relationship': 'blocks'})
        self.assertFalse(self.acknowledge([12], read)['ok'])
        links[0]['relationship'] = 'implements'
        self.assertTrue(self.acknowledge([12], read)['ok'])

    def test_open_designs_and_resolved_specs_remain_commitments(self):
        for rid, kind, status in [(20, 'arch', 'open'), (21, 'spec', 'open'),
                                  (22, 'spec', 'resolved'), (23, 'arch', None)]:
            self.write_record(rid, kind=kind, status=status)
            self.assertIn(rid, state.load('s')['written_intents'])
            self.assertNotIn(rid, state.load('s').get('outcome_records', []))

    def test_changing_selected_or_written_arch_status_cannot_self_ack(self):
        for source in ('selected', 'written'):
            with self.subTest(source=source):
                state.update('s', lambda st: st.update(selected_intents=[], written_intents=[],
                             outcome_records=[], outcome_revisions={}))
                if source == 'selected':
                    rec = self.write_record(12, kind='arch', status='resolved')
                    with patch.object(client, 'mcp_call', return_value={'ok': True, 'data': rec}):
                        self.assertTrue(workflow.handle_session({'action': 'select_intent',
                                        'record_id': 12, 'session_id': 's'})['ok'])
                else:
                    self.write_record(12, kind='arch', status='open')
                self.write_record(12, kind='arch', status='resolved')
                self.assertFalse(self.acknowledge([12], lambda *_: self.fail('reject before readback'))['ok'])
                self.assertTrue(state.load('s')['dirty'])
                self.assertIn(12, state.load('s')[source + '_intents'])

    def test_partial_resolved_arch_can_recover_without_becoming_intent(self):
        rec = {'id': 12, 'kind': 'arch', 'status': 'resolved', 'project_id': 7}
        hooks.post_tool_call('reqall', args={'action': 'upsert_record'}, session_id='s',
            status='error', result={'ok': False, 'record_saved': True, 'data': rec, 'error': 'link failure'})
        self.assertEqual(state.load('s')['pending_write_failures'], [12])
        self.assertEqual(state.load('s').get('written_intents', []), [])
        self.assertEqual(self.acknowledge([12], lambda *_: None)['error'], 'pending_write_failure')
        revision = state.load('s')['work_revision']
        self.write_record(12, kind='arch', status='resolved')
        def read(action, args):
            return {'ok': True, 'data': rec if action == 'get_record' else {'links': [], 'total': 0}}
        self.assertTrue(self.acknowledge([12], read, revision)['ok'])

    def test_select_intent_accepts_only_same_project_spec_or_arch(self):
        for kind, project_id, expected in [('spec', 7, True), ('arch', 7, True),
                                           ('work', 7, False), ('todo', 7, False),
                                           ('spec', 8, False), ('arch', 8, False)]:
            with self.subTest(kind=kind, project_id=project_id):
                record = {'id': 1, 'kind': kind, 'project_id': project_id}
                with patch.object(client, 'mcp_call', return_value={'ok': True, 'data': record}):
                    result = workflow.handle_session({'action': 'select_intent',
                                                      'record_id': 1, 'session_id': 's'})
                self.assertEqual(result['ok'], expected)

    def test_host_error_status_preserves_partial_record_save(self):
        result = {'ok': False, 'error': 'link_failed', 'record_saved': True,
                  'data': {'id': 1, 'kind': 'spec', 'project_id': 7}}
        hooks.post_tool_call('reqall', args={'action': 'upsert_record'}, result=result,
                             status='error', session_id='s')
        self.assertEqual(state.load('s').get('written_intents'), [1])
        self.assertTrue(state.load('s')['dirty'])
        hooks.post_tool_call('reqall', args={'action': 'upsert_record'}, result=result,
                             status='blocked', session_id='blocked')
        self.assertFalse(state.load('blocked')['dirty'])

    def test_partial_saved_intent_remains_a_commitment(self):
        hooks.post_tool_call('reqall', args={'action': 'upsert_record'}, session_id='s',
            result={'structuredContent': {'ok': True, 'data': {'record': {'id': 1, 'kind': 'spec', 'project_id': 7}, 'links': [{'action': 'error', 'error': 'missing target'}]}}})
        st = state.load('s')
        self.assertEqual(st.get('written_intents'), [1])
        self.assertEqual(st.get('pending_write_failures'), [1])
        self.assertTrue(st['dirty'])

    def test_resolved_gap_cannot_cover_intent(self):
        state.update('s', lambda st: st.update(selected_intents=[1], dirty=True))
        rec = self.write_record(kind='todo', status='resolved')
        def read(action, args):
            if action == 'get_record':
                return {'ok': True, 'data': rec if args['id'] == 10 else {'id': 1, 'kind': 'spec', 'project_id': 7}}
            return {'ok': True, 'data': {'links': [{'source_id': 10, 'source_table': 'records', 'target_id': 1, 'target_table': 'records', 'relationship': 'blocks'}], 'total': 1}}
        self.assertFalse(self.acknowledge([10], read)['ok'])
        rec['status'] = 'open'
        self.assertTrue(self.acknowledge([10], read)['ok'])

    def test_partial_save_requires_same_id_record_recovery_after_link_repair(self):
        state.update('s', lambda st: st.update(selected_intents=[1], dirty=True))
        rec = {'id': 10, 'kind': 'work', 'project_id': 7}
        hooks.post_tool_call('reqall', args={'action': 'upsert_record'}, session_id='s',
            result={'ok': True, 'data': {'record': rec, 'links': [{'action': 'error', 'error': 'missing target'}]}})
        self.assertEqual(state.load('s')['pending_write_failures'], [10])
        link = {'source_id': 10, 'source_table': 'records', 'target_id': 1,
                'target_table': 'records', 'relationship': 'implements'}
        hooks.post_tool_call('reqall', args={'action': 'upsert_link', 'arguments': link},
                             result={'ok': True, 'data': link}, session_id='s')
        def read(action, args):
            if action == 'get_record':
                return {'ok': True, 'data': rec if args['id'] == 10 else {'id': 1, 'kind': 'spec', 'project_id': 7}}
            return {'ok': True, 'data': {'links': [link], 'total': 1}}
        with patch.object(client, 'mcp_call', side_effect=read):
            self.assertEqual(client.mcp_call('get_record', {'id': 10})['data'], rec)
            self.assertEqual(client.mcp_call('list_links', {'entity_id': 10})['data']['links'], [link])
        self.assertEqual(self.acknowledge([10], read)['error'], 'pending_write_failure')
        hooks.post_tool_call('reqall', args={'action': 'upsert_record', 'arguments': dict(rec)},
                             result={'ok': True, 'data': {'record': rec}}, session_id='s')
        snapshot = workflow.handle_session({'action': 'status', 'session_id': 's'})
        self.assertEqual(snapshot['pending_write_failures'], [])
        self.assertEqual(snapshot['outcome_records'], [10])
        self.assertTrue(self.acknowledge([10], read, snapshot['work_revision'])['ok'])
        final = workflow.handle_session({'action': 'status', 'session_id': 's'})
        self.assertFalse(final['dirty'])
        self.assertEqual(final['acknowledged_record_ids'], [10])

    def test_historical_record_cannot_acknowledge_current_work(self):
        state.mark_dirty('s', 'a.py')
        rec = {'id': 10, 'kind': 'work', 'project_id': 7}
        def read(action, args):
            return {'ok': True, 'data': {'record': rec} if action == 'get_record' else {'links': [], 'total': 0}}
        result = self.acknowledge([10], read)
        self.assertFalse(result['ok'])
        self.assertTrue(state.load('s')['dirty'])
        self.write_record()
        self.assertTrue(self.acknowledge([10], read)['ok'])

    def test_legacy_outcome_without_revision_fails_closed(self):
        state.update('s', lambda st: st.update(dirty=True, outcome_records=[10]))
        result = self.acknowledge([10], lambda *_: self.fail('must reject before readback'))
        self.assertEqual(result['error'], 'stale_outcome')
        self.assertTrue(state.load('s')['dirty'])

    def test_outcome_revisions_are_project_scoped(self):
        self.write_record()
        original = state.load('s')['outcome_revisions']
        with patch.dict(os.environ, {'REQALL_PROJECT_NAME': 'org/b'}):
            hooks.on_session_start(session_id='s')
        switched = state.load('s')
        self.assertEqual(switched['outcome_revisions'], {})
        self.assertEqual(switched['project_workflows']['org/a']['outcome_revisions'], original)
        hooks.on_session_start(session_id='s')
        self.assertEqual(state.load('s')['outcome_revisions'], original)

    def test_acknowledging_project_b_preserves_project_a_work_only(self):
        hooks.post_tool_call('delegate_task', args={'path': 'a.py'},
                             result={'ok': True}, session_id='s')
        before = state.load('s')
        with patch.dict(os.environ, {'REQALL_PROJECT_NAME': 'org/b'}):
            hooks.on_session_start(session_id='s')
        switched = state.load('s')
        state.update('s', lambda st: st.update(project_id=7))
        rec = self.write_record()
        def read(action, args):
            return {'ok': True, 'data': {'record': rec} if action == 'get_record' else {'links': [], 'total': 0}}
        self.assertTrue(self.acknowledge([10], read)['ok'])
        hooks.on_session_start(session_id='s')
        restored = state.load('s')
        self.assertTrue(restored['dirty'])
        self.assertEqual(restored['touched_paths'], ['a.py'])
        self.assertTrue(restored['delegate_activity'])
        self.assertFalse(switched['dirty'])
        self.assertEqual(switched['touched_paths'], [])
        self.assertFalse(switched.get('delegate_activity'))
        self.assertGreater(switched['work_revision'], before['work_revision'])
        self.assertGreater(restored['work_revision'], switched['work_revision'])
