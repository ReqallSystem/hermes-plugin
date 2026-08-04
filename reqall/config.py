"""Environment and defaults for Reqall."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

DEFAULT_URL = "https://www.reqall.net"
DEFAULT_DOC_INTERVAL_MIN = 10
DEFAULT_PERSIST_INTERVAL_MIN = 30


def api_url(env: Dict[str, str] | None = None) -> str:
    e = env if env is not None else os.environ
    raw = (e.get("REQALL_URL") or e.get("REQALL_API_URL") or DEFAULT_URL).strip()
    return raw.rstrip("/")


def api_key(env: Dict[str, str] | None = None) -> str:
    e = env if env is not None else os.environ
    if "REQALL_API_KEY" in e:
        return (e.get("REQALL_API_KEY") or "").strip()
    # Optional shared CLI auth file (parity with other Reqall plugins)
    cfg = _load_stored_auth()
    token = cfg.get("access_token") or cfg.get("api_key") or ""
    return str(token).strip()


def project_name_override(env: Dict[str, str] | None = None) -> str:
    e = env if env is not None else os.environ
    return (e.get("REQALL_PROJECT_NAME") or "").strip()


def doc_interval_min(env: Dict[str, str] | None = None) -> float:
    e = env if env is not None else os.environ
    try:
        return float(e.get("REQALL_DOC_INTERVAL_MIN", DEFAULT_DOC_INTERVAL_MIN))
    except ValueError:
        return float(DEFAULT_DOC_INTERVAL_MIN)


def persist_interval_min(env: Dict[str, str] | None = None) -> float:
    e = env if env is not None else os.environ
    try:
        return float(e.get("REQALL_PERSIST_INTERVAL_MIN", DEFAULT_PERSIST_INTERVAL_MIN))
    except ValueError:
        return float(DEFAULT_PERSIST_INTERVAL_MIN)


def _load_stored_auth() -> Dict[str, Any]:
    candidates = []
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        candidates.append(Path(xdg) / "reqall" / "config.json")
    candidates.append(Path.home() / ".config" / "reqall" / "config.json")
    # macOS Application Support path (harmless if missing on Linux)
    candidates.append(
        Path.home() / "Library" / "Application Support" / "reqall" / "config.json"
    )
    for path in candidates:
        try:
            if path.is_file():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
    return {}
