"""Explicit session intent and verified reconciliation (no implicit session)."""
from __future__ import annotations
import json
from typing import Any
from . import client, state
from .hooks import _successful


def _payload(value: Any, *, unwrap_data=True) -> Any:
    """Only documented transport envelopes, never a recursive record search."""
    for _ in range(8):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                return None
            continue
        if not isinstance(value, dict):
            return value
        if not _successful(value):
            return None
        if 'jsonrpc' in value and 'result' in value:
            value = value['result']
        elif 'structuredContent' in value:
            value = value['structuredContent']
        elif 'content' in value and isinstance(value['content'], list):
            texts = [v.get('text') for v in value['content'] if isinstance(v, dict) and v.get('type') == 'text']
            if len(texts) != 1:
                return None
            value = texts[0]
        elif unwrap_data and 'ok' in value and 'data' in value:
            value = value['data']
        else:
            return value
    return None


def _record(value: Any):
    value = _payload(value)
    if isinstance(value, dict) and 'record' in value:
        value = value['record']
    if isinstance(value, dict) and _successful(value) and type(value.get('id')) is int and type(value.get('project_id')) is int and isinstance(value.get('kind'), str):
        return value
    return None


def _same_project(st, record):
    return type(st.get('project_id')) is int and st['project_id'] == record['project_id']


def _is_commitment(st, record):
    # A completed standalone design decision is an outcome, not new intent.
    # Once selected/written as intent, status changes cannot self-reconcile it.
    return (record['id'] in st.get('selected_intents', [])
            or record['id'] in st.get('written_intents', [])
            or record['kind'] == 'spec'
            or (record['kind'] == 'arch' and record.get('status') != 'resolved'))


def track_result(sid, tool_name, args, result):
    action = args.get('action') if tool_name == 'reqall' else tool_name.lower().removeprefix('mcp__reqall__')
    if action == 'upsert_project':
        request = args.get('arguments') if tool_name == 'reqall' else args
        envelope = _payload(result, unwrap_data=False)
        if not isinstance(envelope, dict) or envelope.get('ok') is not True:
            return
        data = envelope.get('data')
        if not isinstance(data, dict) or data.get('action') not in {'created_or_found', 'matched_existing', 'updated'}:
            return
        project = data.get('project') if isinstance(data, dict) else None
        if (not isinstance(request, dict) or not isinstance(project, dict)
            or not isinstance(request.get('name'), str) or not request['name']
            or project.get('name') != request['name']
            or type(project.get('id')) is not int or not _successful(project)
            or ('id' in request and (type(request['id']) is not int or request['id'] != project['id']))):
            return
        def recover(current):
            if current.get('project_name') == request['name'] and current.get('project_id') is None:
                current['project_id'] = project['id']
        state.update(sid, recover)
        return
    if action not in {'get_record', 'upsert_record'}:
        return
    normalized = client.normalize_result(result)
    if not normalized.get('ok'):
        if action == 'upsert_record' and normalized.get('record_saved'):
            def partial(st):
                data = normalized.get('data')
                record = _record(data)
                if record and _same_project(st, record):
                    st['dirty'] = True
                    st['work_revision'] = int(st.get('work_revision', 0)) + 1
                    pending = st.setdefault('pending_write_failures', [])
                    if record['id'] not in pending:
                        pending.append(record['id'])
                    if _is_commitment(st, record):
                        intents = st.setdefault('written_intents', [])
                        if record['id'] not in intents:
                            intents.append(record['id'])
            state.update(sid, partial)
        return
    record = _record(result)
    if not record:
        return
    def track(st):
        if not _same_project(st, record):
            return
        if action == 'upsert_record':
            st['ledger_revision'] = int(st.get('ledger_revision', 0)) + 1
            st['pending_write_failures'] = [v for v in st.get('pending_write_failures', []) if v != record['id']]
        key = 'consulted_records' if action == 'get_record' else ('written_intents' if _is_commitment(st, record) else 'outcome_records')
        ids = st.setdefault(key, [])
        if record['id'] not in ids:
            ids.append(record['id'])
        if key == 'outcome_records':
            st.setdefault('outcome_revisions', {})[str(record['id'])] = int(st.get('work_revision', 0))
        if key == 'written_intents':
            st['dirty'] = True
            st['work_revision'] = int(st.get('work_revision', 0)) + 1
    state.update(sid, track)


def _acknowledge(sid, args, st):
    if st.get('pending_write_failures'):
        return {'ok': False, 'error': 'pending_write_failure'}
    revision, ids = args.get('work_revision'), args.get('record_ids')
    if type(revision) is not int or revision != st.get('work_revision', 0):
        return {'ok': False, 'error': 'stale_revision'}
    if not isinstance(ids, list) or not ids or any(type(v) is not int for v in ids) or len(set(ids)) != len(ids):
        return {'ok': False, 'error': 'invalid_record_ids'}
    if not set(ids).issubset(st.get('outcome_records', [])):
        return {'ok': False, 'error': 'outcome_not_written_this_session'}
    outcome_revisions = st.get('outcome_revisions', {})
    if any(type(outcome_revisions.get(str(rid))) is not int or
           outcome_revisions[str(rid)] != revision for rid in ids):
        return {'ok': False, 'error': 'stale_outcome'}
    # Only this revision's persistence batch must be complete. Older outcomes
    # may be superseded by a new consolidated write, but never reused as proof.
    missing = {rid for rid in st.get('outcome_records', [])
               if outcome_revisions.get(str(rid)) == revision} - set(ids)
    if missing:
        return {'ok': False, 'error': 'unverified_batch_outcomes', 'record_ids': sorted(missing)}
    pending = set(st.get('selected_intents', [])) | set(st.get('written_intents', []))
    covered = set()
    try:
        for rid in sorted(pending):
            rec = _record(client.mcp_call('get_record', {'id': rid}))
            if not rec or rec['id'] != rid or not _same_project(st, rec) or rec['kind'] not in {'spec', 'arch'}:
                return {'ok': False, 'error': 'unverified_intent'}
        for rid in ids:
            rec = _record(client.mcp_call('get_record', {'id': rid}))
            if not rec or rec['id'] != rid or not _same_project(st, rec) or _is_commitment(st, rec):
                return {'ok': False, 'error': 'unverified_outcome'}
            data = _payload(client.mcp_call('list_links', {'entity_id': rid, 'entity_type': 'records', 'direction': 'outgoing', 'limit': 100, 'offset': 0}))
            if not isinstance(data, dict) or not isinstance(data.get('links'), list):
                return {'ok': False, 'error': 'unverified_links'}
            links = data['links']
            if data.get('has_more') or (type(data.get('total')) is int and data['total'] != len(links)):
                return {'ok': False, 'error': 'partial_links'}
            for link in links:
                if not isinstance(link, dict) or not _successful(link):
                    return {'ok': False, 'error': 'partial_links'}
                if (link.get('source_id') == rid and link.get('source_table') == 'records'
                    and link.get('target_table') == 'records' and link.get('target_id') in pending
                    and (link.get('relationship') == 'implements' or
                         (link.get('relationship') == 'blocks' and rec['kind'] == 'todo' and rec.get('status') == 'open'))):
                    covered.add(link['target_id'])
    except Exception:
        return {'ok': False, 'error': 'readback_unavailable'}
    if covered != pending:
        return {'ok': False, 'error': 'unreconciled_intent', 'record_ids': sorted(pending - covered)}
    cleared = []
    def commit(current):
        if (current.get('work_revision', 0) != revision
            or current.get('ledger_revision', 0) != st.get('ledger_revision', 0)
            or current.get('project_id') != st.get('project_id')
            or current.get('project_name') != st.get('project_name')):
            return
        current.update(dirty=False, touched_paths=[], selected_intents=[], written_intents=[],
                       outcome_records=[], outcome_revisions={}, delegate_activity=False, acknowledged_record_ids=ids,
                       acknowledged_revision=revision)
        cleared.append(True)
    state.update(sid, commit)
    return {'ok': bool(cleared), 'session_id': sid, **({} if cleared else {'error': 'stale_revision'})}


def handle_session(args, **kwargs):
    """Actions: status; select_intent(record_id); acknowledge(record_ids, revision)."""
    args = args or {}
    sid = kwargs.get('session_id') or args.get('session_id')
    if not isinstance(sid, str) or not sid.strip():
        return {'ok': False, 'error': 'needs_session_id'}
    st = state.load(sid)
    action = args.get('action', 'status')
    if action == 'status':
        return {'ok': True, **st}
    if action == 'acknowledge':
        return _acknowledge(sid, args, st)
    if action == 'select_intent':
        rid = args.get('record_id')
        if type(rid) is not int:
            return {'ok': False, 'error': 'invalid_record_id'}
        try:
            record = _record(client.mcp_call('get_record', {'id': rid}))
        except Exception:
            record = None
        if not record or record['id'] != rid or record['kind'] not in {'spec', 'arch'} or not _same_project(st, record):
            return {'ok': False, 'error': 'unverified_intent'}
        accepted = []
        def select(current):
            if current.get('project_name') != st.get('project_name') or not _same_project(current, record):
                return
            ids = current.setdefault('selected_intents', [])
            if rid not in ids:
                ids.append(rid)
                current['work_revision'] = int(current.get('work_revision', 0)) + 1
            current['dirty'] = True
            accepted.append(True)
        saved = state.update(sid, select)
        return {'ok': bool(accepted), 'session_id': sid, 'work_revision': saved.get('work_revision', 0)}
    return {'ok': False, 'error': 'unknown_action'}
