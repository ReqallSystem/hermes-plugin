"""Hermes lifecycle hooks for Reqall — fail-open always."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from . import client, state
from .config import doc_interval_min, persist_interval_min
from .project import resolve_project_name

logger = logging.getLogger(__name__)

READISH_SHELL = re.compile(
    r"^(ls|pwd|cat|head|tail|git\s+(status|diff|log|show|branch)|echo|which|rg|find)\b",
    re.I,
)


def _session_id(**kwargs: Any) -> str:
    return str(
        kwargs.get("session_id")
        or kwargs.get("task_id")
        or kwargs.get("conversation_id")
        or "default"
    )


def _cwd(**kwargs: Any) -> Optional[str]:
    return kwargs.get("cwd") or kwargs.get("workdir") or None


def _user_message(**kwargs: Any) -> str:
    msg = kwargs.get("user_message") or kwargs.get("message") or ""
    if isinstance(msg, dict):
        return str(msg.get("content") or "")
    return str(msg or "")


def is_trivial_prompt(prompt: str) -> bool:
    value = (prompt or "").strip()
    if not value:
        return True
    if re.match(
        r"^(hi|hello|hey|thanks|thank you|ok|okay|yo|sup)[!?.\s]*$",
        value,
        re.I,
    ):
        return True
    return False


def is_nontrivial_prompt(prompt: str) -> bool:
    if is_trivial_prompt(prompt):
        return False
    if len(prompt) > 40:
        return True
    return bool(
        re.search(
            r"\b(implement|update|change|edit|fix|debug|bug|refactor|migrat|"
            r"architect|design|create|add|remove|test|build|review|audit|"
            r"inspect|assess|examine|research|analy[sz]e|investigate|diagnose|"
            r"release|deploy|document|wire|hook|plugin)\w*\b",
            prompt,
            re.I,
        )
    )


def _tool_path(tool_name: str, params: Dict[str, Any]) -> str:
    for key in ("path", "file_path", "workdir"):
        val = params.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    if tool_name == "terminal":
        cmd = str(params.get("command") or "")
        return cmd.strip()[:200]
    return ""


def _is_mutating(tool_name: str, params: Dict[str, Any]) -> bool:
    name = tool_name or ""
    if name in {"write_file", "patch", "skill_manage", "execute_code"}:
        return True
    if name == "terminal":
        cmd = str(params.get("command") or "").strip()
        if not cmd:
            return False
        if READISH_SHELL.match(cmd):
            return False
        return True
    return False


def on_session_start(**kwargs: Any) -> None:
    try:
        sid = _session_id(**kwargs)
        project = resolve_project_name(_cwd(**kwargs))
        st = state.load(sid)
        st["project_name"] = project
        state.save(sid, st)
        logger.info("reqall session start project=%s session=%s", project, sid)
    except Exception:
        logger.exception("reqall on_session_start failed (fail-open)")


def pre_llm_call(**kwargs: Any) -> Optional[Dict[str, str]]:
    """Inject Reqall recall + documentation/persistence nudges into the user turn."""
    try:
        prompt = _user_message(**kwargs)
        sid = _session_id(**kwargs)
        st = state.load(sid)
        project = st.get("project_name") or resolve_project_name(_cwd(**kwargs))
        st["project_name"] = project
        chunks: List[str] = []

        if is_nontrivial_prompt(prompt):
            try:
                up = client.upsert_project(project)
                if up.get("ok"):
                    pid = client.parse_project_id(up)
                    if pid is not None:
                        st["project_id"] = pid
                sr = client.search(prompt[:500], project_name=project, limit=5)
                open_r = None
                if st.get("project_id") is not None:
                    open_r = client.list_open_records(st.get("project_id"))
                chunks.append(client.format_recall(project, sr, open_r))
            except Exception:
                logger.exception("reqall recall failed")
                chunks.append(
                    f"[reqall] project_name={project} — recall unavailable; "
                    "use skill reqall-context when needed."
                )
        elif not is_trivial_prompt(prompt):
            chunks.append(
                f"[reqall] project_name={project}. "
                "For coding work, run skill reqall-context before edits; "
                "reqall-persist before finishing non-trivial turns."
            )

        note = st.pop("last_pre_edit_note", None)
        if note:
            chunks.append(str(note))

        nudge = st.pop("pending_doc_nudge", None)
        if nudge:
            chunks.append(str(nudge))

        if st.get("dirty") and state.should_nudge(
            sid, "persist", persist_interval_min()
        ):
            paths = ", ".join((st.get("touched_paths") or [])[:8]) or "(paths noted)"
            chunks.append(
                "[reqall] MANDATORY persistence before ending this turn if work "
                "was meaningful (touched: {paths}). Persist now: plugin tool "
                f"`reqall` action=upsert_record (project_name={project}) or "
                "load instructions via `reqall_skill` name=reqall-persist / "
                "/reqall persist (works when skill_view is disabled). Then "
                "upsert_link → list_records. Skip pure Q&A / read-only. "
                "If Reqall is unavailable, continue and disclose that."
            )

        state.save(sid, st)
        if not chunks:
            return None
        return {"context": "\n\n".join(chunks)}
    except Exception:
        logger.exception("reqall pre_llm_call failed (fail-open)")
        return None


def pre_tool_call(
    tool_name: str = "",
    params: Optional[Dict] = None,
    **kwargs: Any,
):
    """Path-focused recall before mutations. Never blocks."""
    try:
        params = params or {}
        if not _is_mutating(tool_name, params):
            return None
        sid = _session_id(**kwargs)
        st = state.load(sid)
        project = st.get("project_name") or resolve_project_name(_cwd(**kwargs))
        query = _tool_path(tool_name, params) or tool_name
        if not query or len(query) < 2:
            return None
        sr = client.search(query[:300], project_name=project, limit=4)
        if not sr.get("ok"):
            return None
        text = sr.get("text") or ""
        if not text or text == "[]" or re.search(r"no results", text, re.I):
            return None
        st["last_pre_edit_note"] = (
            f"[reqall pre-edit recall for `{query}`]\n"
            f"{client._truncate(text, 2000)}"
        )
        state.save(sid, st)
        return None
    except Exception:
        logger.exception("reqall pre_tool_call failed (fail-open)")
        return None


def post_tool_call(
    tool_name: str = "",
    params: Optional[Dict] = None,
    result: Any = None,
    **kwargs: Any,
) -> None:
    del result
    try:
        params = params or {}
        if not _is_mutating(tool_name, params):
            return
        sid = _session_id(**kwargs)
        path = _tool_path(tool_name, params)
        state.mark_dirty(sid, path or tool_name)
        if state.should_nudge(sid, "doc", doc_interval_min()):
            st = state.load(sid)
            st["pending_doc_nudge"] = (
                "[reqall] Meaningful tool use completed. If non-trivial, document "
                "via `reqall` action=upsert_record or `reqall_skill` "
                "name=reqall-document (skip read-only/no-op)."
            )
            state.save(sid, st)
    except Exception:
        logger.exception("reqall post_tool_call failed (fail-open)")


def on_session_end(**kwargs: Any) -> None:
    try:
        sid = _session_id(**kwargs)
        st = state.load(sid)
        if st.get("dirty"):
            logger.info(
                "reqall session end with dirty work session=%s project=%s",
                sid,
                st.get("project_name"),
            )
    except Exception:
        logger.exception("reqall on_session_end failed (fail-open)")
