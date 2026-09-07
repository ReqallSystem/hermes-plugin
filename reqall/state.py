"""Atomic JSON session state with cross-process transaction locking."""

from __future__ import annotations

import json
import os
import tempfile
import time
import threading
import sqlite3
from contextlib import contextmanager
from .config import hermes_home
from pathlib import Path
from typing import Any, Dict, Optional


def _state_dir() -> Path:
    base = hermes_home()
    d = Path(base) / "reqall" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(session_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (session_id or "default"))
    return _state_dir() / f"{safe}.json"


_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


@contextmanager
def _locked(path):
    key = str(path.parent.resolve())
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(key, threading.RLock())
    with lock:
        # SQLite supplies a cross-process lock on Windows as well as POSIX.
        # Session data stays in the existing atomically replaced JSON files.
        connection = sqlite3.connect(str(path.parent / ".state-lock.sqlite3"), timeout=30)
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield
        finally:
            try:
                connection.rollback()
            finally:
                connection.close()


def load(session_id: str) -> Dict[str, Any]:
    return _load_path(session_id, _path(session_id))


def _load_path(session_id, path):
    default = {
        "session_id": session_id or "default",
        "dirty": False,
        "project_name": None,
        "project_id": None,
        "last_doc_nudge_at": 0.0,
        "last_persist_nudge_at": 0.0,
        "touched_paths": [],
    }
    if not path.exists():
        return dict(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            merged = dict(default)
            merged.update(data)
            return merged
    except Exception:
        pass
    return dict(default)


def update(session_id, mutator) -> Dict[str, Any]:
    """Atomically mutate the latest state in place; ignore mutator's return value.

    Locks cover threads and processes sharing a profile. Raises on failed writes;
    callers must not treat unsaved state as reconciled. Legacy JSON stays readable.
    """
    path = _path(session_id)
    with _locked(path):
        st = _load_path(session_id, path)
        mutator(st)
        return _save_path(session_id, st, path)


def save(session_id: str, state: Dict[str, Any]) -> None:
    path = _path(session_id)
    with _locked(path):
        _save_path(session_id, state, path)


def _save_path(session_id, state, path):
    state = dict(state)
    state["session_id"] = session_id or "default"
    state["updated_at"] = time.time()
    tmp_fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, default=str)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return state


def mark_dirty(session_id: str, path: Optional[str] = None) -> Dict[str, Any]:
    def mutate(st):
        st["dirty"] = True
        st["work_revision"] = int(st.get("work_revision") or 0) + 1
        if path:
            paths = list(st.get("touched_paths") or [])
            if path not in paths:
                paths.append(path)
            st["touched_paths"] = paths[-40:]
    return update(session_id, mutate)


def clear_dirty(session_id: str) -> None:
    def mutate(st):
        st["dirty"] = False
        st["touched_paths"] = []
        st["persist_nudge_sent"] = False
        st["last_persist_nudge_at"] = time.time()
    update(session_id, mutate)


def should_nudge(session_id: str, kind: str, interval_min: float) -> bool:
    allowed = False
    def mutate(st):
        nonlocal allowed
        key = "last_doc_nudge_at" if kind == "doc" else "last_persist_nudge_at"
        now = time.time()
        if interval_min <= 0 or now - float(st.get(key) or 0) >= interval_min * 60:
            st[key] = now
            allowed = True
    update(session_id, mutate)
    return allowed
