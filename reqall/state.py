"""In-memory + disk session markers for throttle / dirty tracking."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional


def _state_dir() -> Path:
    base = os.environ.get("HERMES_HOME") or str(Path.home() / ".hermes")
    d = Path(base) / "reqall" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(session_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (session_id or "default"))
    return _state_dir() / f"{safe}.json"


def load(session_id: str) -> Dict[str, Any]:
    default = {
        "session_id": session_id or "default",
        "dirty": False,
        "project_name": None,
        "project_id": None,
        "last_doc_nudge_at": 0.0,
        "last_persist_nudge_at": 0.0,
        "touched_paths": [],
    }
    path = _path(session_id)
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


def save(session_id: str, state: Dict[str, Any]) -> None:
    path = _path(session_id)
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


def mark_dirty(session_id: str, path: Optional[str] = None) -> Dict[str, Any]:
    st = load(session_id)
    st["dirty"] = True
    if path:
        paths = list(st.get("touched_paths") or [])
        if path not in paths:
            paths.append(path)
            st["touched_paths"] = paths[-40:]
    save(session_id, st)
    return st


def clear_dirty(session_id: str) -> None:
    st = load(session_id)
    st["dirty"] = False
    st["touched_paths"] = []
    st["last_persist_nudge_at"] = time.time()
    save(session_id, st)


def should_nudge(session_id: str, kind: str, interval_min: float) -> bool:
    if interval_min <= 0:
        return True
    st = load(session_id)
    key = "last_doc_nudge_at" if kind == "doc" else "last_persist_nudge_at"
    last = float(st.get(key) or 0)
    if (time.time() - last) < interval_min * 60:
        return False
    st[key] = time.time()
    save(session_id, st)
    return True
