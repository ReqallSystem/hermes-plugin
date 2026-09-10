"""Fail-open Hermes hooks: turn-start recall and edited-code verification.

pre_tool_call cannot inject context; end/finalize hooks only log. Persistence
reminders run next turn and at pre_verify, not as a generic Stop/PreCompact gate.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

from . import client, state
from .project import bind_project, conceptual_query

logger = logging.getLogger(__name__)
CODING_HINT = re.compile(r'\b(implement|update|change|edit|fix|debug|bug|refactor|migrat|architect|design|create|add|remove|test|build|review|audit|inspect|assess|examine|research|analy[sz]e|investigate|diagnose|release|deploy|document|wire|hook|plugin|persist|sleep)\w*\b', re.I)


def _session_id(**kwargs: Any) -> Optional[str]:
    value = kwargs.get('session_id') or kwargs.get('task_id') or kwargs.get('conversation_id')
    return str(value) if value else None


def _cwd(**kwargs: Any) -> Optional[str]:
    return kwargs.get('cwd') or kwargs.get('workdir')


def _user_message(**kwargs: Any) -> str:
    value = kwargs.get('user_message') or kwargs.get('message') or ''
    return str(value.get('content') or '') if isinstance(value, dict) else str(value)


def is_trivial_prompt(prompt: str) -> bool:
    return not prompt.strip() or bool(re.fullmatch(r'(hi|hello|hey|thanks|thank you|ok|okay|yo|sup)[!?.\s]*', prompt.strip(), re.I))


def is_nontrivial_prompt(prompt: str) -> bool:
    return not is_trivial_prompt(prompt) and bool(CODING_HINT.search(prompt))


def _tool_path(tool_name: str, args: Dict[str, Any]) -> str:
    for key in ('path', 'file_path', 'workdir'):
        if isinstance(args.get(key), str) and args[key].strip():
            return args[key].strip()
    return str(args.get('command') or '')[:200] if tool_name == 'terminal' else ''


def _is_mutating(tool_name: str, args: Dict[str, Any]) -> bool:
    if tool_name in {'write_file', 'patch', 'skill_manage', 'execute_code', 'delegate_task'}:
        return True
    if tool_name != 'terminal':
        return False
    cmd = str(args.get('command') or '').strip()
    if not cmd:
        return False
    # Deliberately conservative: substitutions, redirects and compounds can write.
    if any(c in cmd for c in ';|&<>`$\n') or '--output' in cmd or '--ext-diff' in cmd or '--textconv' in cmd:
        return True
    return not bool(re.match(r'^(ls|pwd|cat|head|tail|echo|which|rg)\b|^git\s+(status|diff|log|show)\b', cmd))


def _successful(result: Any, status: Any = None) -> bool:
    failed = {'failed', 'failure', 'error', 'blocked', 'cancelled', 'denied', 'partial'}
    if str(status).lower() in failed:
        return False
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except ValueError:
            return bool(result) and not result.lower().startswith(('error', 'failed', 'blocked'))
    if not isinstance(result, dict):
        return result is not None and result is not False
    if result.get('ok') is False or result.get('success') is False or result.get('isError') or result.get('error'):
        return False
    if str(result.get('status')).lower() in failed or result.get('exit_code') not in (None, 0):
        return False
    return all(_successful(result[k]) for k in ('result', 'data', 'structuredContent') if isinstance(result.get(k), dict))


def _mutation_observed(tool_name: str, result: Any, status: Any = None) -> bool:
    if tool_name not in {'terminal', 'execute_code'}:
        # Atomic file edits still require success; a failed edit is not a write.
        return _successful(result, status)
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except ValueError:
            return False
    if not isinstance(result, dict):
        return False
    unexecuted = {'blocked', 'denied', 'cancelled', 'disabled', 'unexecuted'}
    if (str(status).lower() in unexecuted
        or str(result.get('status')).lower() in unexecuted
        or result.get('executed') is False):
        return False
    if _successful(result, status) or result.get('executed') is True:
        return True
    # Nonzero process exits can follow writes. -1 is also the host's generic
    # pre-execution error sentinel, so it alone is not execution evidence.
    exit_code = result.get('exit_code')
    if type(exit_code) is int and exit_code != -1:
        return True
    if tool_name == 'execute_code':
        kernel = result.get('kernel')
        count = kernel.get('execution_count') if isinstance(kernel, dict) else None
        calls = result.get('tool_calls_made')
        return (type(count) is int and count > 0) or (type(calls) is int and calls > 0)
    return False


def _bind(st: Dict[str, Any], prompt: str = '', **kwargs: Any):
    binding = bind_project(cwd=_cwd(**kwargs), prompt=prompt)
    if st.get('project_name') != binding.name:
        st['project_id'] = None
        # The subscription cursor belongs to the old project; release it at session end.
        stale = st.pop('subscribed_project_id', None)
        if type(stale) is int:
            st.setdefault('stale_subscriptions', []).append(stale)
        # IDs are scoped to their binding; never reconcile old-project intent here.
        defaults = dict(consulted_records=[], selected_intents=[], written_intents=[],
                        outcome_records=[], outcome_revisions={}, pending_write_failures=[], dirty=False,
                        touched_paths=[], delegate_activity=False)
        buckets = st.setdefault('project_workflows', {})
        old = st.get('project_name')
        if old:
            buckets[old] = {key: st.get(key, default) for key, default in defaults.items()}
            restored = buckets.pop(binding.name, {})
        else:
            # Preserve work observed before this session's first binding.
            restored = {key: st.get(key, default) for key, default in defaults.items()}
        for key, default in defaults.items():
            st[key] = restored.get(key, default)
        st['work_revision'] = int(st.get('work_revision', 0)) + 1
    st.update(project_name=binding.name, project_source=binding.source,
              project_safe_to_upsert=binding.safe_to_upsert)
    if not binding.safe_to_upsert:
        st['project_id'] = None
    return binding


def on_session_start(**kwargs: Any) -> None:
    try:
        sid = _session_id(**kwargs)
        if sid:
            state.update(sid, lambda st: _bind(st, **kwargs))
    except Exception:
        logger.exception('reqall session start failed (fail-open)')


def _persist_nudge(project: Optional[str], paths: str, source: str) -> str:
    return (
        f'[reqall] Persist meaningful work (touched: {paths}; project={project or "RESOLVE FIRST"}; source={source}). '
        'Use reqall_skill name=reqall-persist. Read reqall_session action=status with this session_id; '
        'persist exact outcome records and implements links to selected/written intent, or gap todo blocks links. '
        'Then reqall_session action=acknowledge with session_id, record_ids and the observed work_revision. '
        'A write alone does not acknowledge reconciliation. If unavailable, continue and disclose the gap; dirty state remains.'
    )


def _own_record_ids(st: Dict[str, Any]) -> list:
    ids = []
    for key in ('written_intents', 'outcome_records', 'pending_write_failures'):
        ids.extend(v for v in st.get(key, []) if type(v) is int)
    return ids


def _subscription_updates(sid: str, st: Dict[str, Any]) -> Optional[str]:
    """Subscribe the bound project once per session, then drain new events each turn.

    One poll per turn; fail-open and silent when the server predates
    subscriptions (unknown tool) or is unreachable.
    """
    pid = st.get('project_id')
    if type(pid) is not int or st.get('subscriptions_unavailable'):
        return None
    if st.get('subscribed_project_id') != pid:
        sub = client.subscribe_project(pid, sid)
        if not _successful(sub):
            if client.unsupported_tool(sub):
                state.update(sid, lambda cur: cur.update(subscriptions_unavailable=True))
            return None
        def remember(cur):
            if cur.get('project_id') == pid:
                cur['subscribed_project_id'] = pid
        state.update(sid, remember)
    poll = client.poll_subscriptions(sid)
    if not _successful(poll):
        return None
    return client.format_updates(poll, _own_record_ids(st))


def pre_llm_call(**kwargs: Any) -> Optional[Dict[str, str]]:
    try:
        sid = _session_id(**kwargs)
        if not sid:
            return None
        prompt = _user_message(**kwargs)
        bindings = []
        def begin(st):
            bindings.append(_bind(st, prompt=prompt, **kwargs))
            st.update(last_user_prompt=prompt[:500], persist_nudge_sent=False)
            st.pop('last_pre_edit_note', None)
            st.pop('pending_doc_nudge', None)
        st = state.update(sid, begin)
        binding = bindings[0]
        chunks = []
        if is_nontrivial_prompt(prompt):
            if binding.safe_to_upsert and binding.name:
                up = client.upsert_project(binding.name)
                pid = client.parse_project_id(up) if _successful(up) else None
                if pid is not None:
                    def save_project(current):
                        if current.get('project_name') == binding.name:
                            current['project_id'] = pid
                    st = state.update(sid, save_project)
            query = conceptual_query('', prompt) or prompt[:500]
            sr = client.search(query, project_name=binding.name, limit=5)
            opened = client.list_open_records(st['project_id']) if st.get('project_id') is not None else None
            chunks.append(client.format_recall(binding.name, sr, opened, binding=binding.as_dict()))
            chunks.append('Before edits, explicitly search/get relevant intent. Reading is consultation, not a commitment; select existing specs with reqall_session action=select_intent record_id=ID.')
        updates = _subscription_updates(sid, st)
        if updates:
            chunks.append(updates)
        if st.get('dirty') or st.get('selected_intents') or st.get('written_intents'):
            chunks.append(_persist_nudge(binding.name, ', '.join(st.get('touched_paths', [])[:8]), binding.source))
        if chunks:
            chunks.append(f'[reqall] session_id={sid}; work_revision={st.get("work_revision", 0)}')
            return {'context': '\n\n'.join(chunks)}
        return None
    except Exception:
        logger.exception('reqall turn recall failed (fail-open)')
        return {'context': '[reqall] Recall unavailable; continue and disclose missing context. Use reqall_skill name=reqall-context.'}


def pre_tool_call(tool_name: str = '', args: Optional[Dict] = None,
                  params: Optional[Dict] = None, **kwargs: Any):
    """No network, no queued recall, no unsupported context return or blocking."""
    return None


def post_tool_call(tool_name: str = '', args: Optional[Dict] = None,
                   result: Any = None, params: Optional[Dict] = None, **kwargs: Any) -> None:
    try:
        sid = _session_id(**kwargs)
        if not sid:
            return
        args = args if args is not None else (params or {})
        if tool_name == 'reqall' or tool_name.lower().startswith('mcp__reqall__'):
            from .workflow import track_result
            status = str(kwargs.get('status') or '').lower()
            # The host correctly labels a partial link failure as an error, but
            # that must not erase the successful record write inside the result.
            partial_save = (status in {'error', 'failed', 'partial'}
                            and client.normalize_result(result).get('record_saved'))
            if _successful({}, status) or partial_save:
                track_result(sid, tool_name, args, result)
        elif _is_mutating(tool_name, args) and _mutation_observed(tool_name, result, kwargs.get('status')):
            state.mark_dirty(sid, _tool_path(tool_name, args) or tool_name)
            if tool_name == 'delegate_task':
                state.update(sid, lambda st: st.update(delegate_activity=True))
    except Exception:
        logger.exception('reqall tool tracking failed (fail-open)')


def pre_verify(**kwargs: Any) -> Optional[Dict[str, str]]:
    try:
        sid = _session_id(**kwargs)
        if not sid or kwargs.get('attempt', 0) != 0:
            return None
        sent = []
        def gate(st):
            if st.get('persist_nudge_sent'):
                return
            changed = kwargs.get('changed_paths') or []
            if changed and not st.get('dirty'):
                st['dirty'] = True
                st['work_revision'] = int(st.get('work_revision', 0)) + 1
                st['touched_paths'] = list(dict.fromkeys(p for p in changed if isinstance(p, str)))[:40]
            if not (st.get('dirty') or st.get('selected_intents') or st.get('written_intents')):
                return
            st['persist_nudge_sent'] = True
            sent.append(_persist_nudge(st.get('project_name'), ', '.join(st.get('touched_paths', [])[:8]), st.get('project_source', 'unbound')) + f' session_id={sid}; work_revision={st.get("work_revision", 0)}')
        state.update(sid, gate)
        return {'action': 'continue', 'message': sent[0]} if sent else None
    except Exception:
        logger.exception('reqall verification reminder failed (fail-open)')
        return None


def _release_subscription(sid: str) -> None:
    """Drop this session's server-side cursor; a stale one only costs a row."""
    st = state.load(sid)
    pids = [v for v in st.get('stale_subscriptions', []) if type(v) is int]
    if type(st.get('subscribed_project_id')) is int:
        pids.append(st['subscribed_project_id'])
    if not pids:
        return
    def clear(cur):
        cur.pop('subscribed_project_id', None)
        cur.pop('stale_subscriptions', None)
    state.update(sid, clear)
    for pid in dict.fromkeys(pids):
        try:
            client.unsubscribe_project(pid, sid, timeout=4.0)
        except Exception:
            logger.debug('reqall unsubscribe failed (fail-open)', exc_info=True)


def on_session_end(**kwargs: Any) -> None:
    try:
        sid = _session_id(**kwargs)
        if not sid:
            return
        if state.load(sid).get('dirty'):
            logger.info('reqall session ends with unacknowledged work session=%s', sid)
        _release_subscription(sid)
    except Exception:
        logger.exception('reqall session end failed (fail-open)')


def on_session_finalize(**kwargs: Any) -> None:
    """Logging only; this notification cannot force persistence."""
    on_session_end(**kwargs)
