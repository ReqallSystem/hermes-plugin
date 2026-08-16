"""Environment and defaults for Reqall."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Mapping

DEFAULT_URL = "https://www.reqall.net"
DEFAULT_DOC_INTERVAL_MIN = 10
DEFAULT_PERSIST_INTERVAL_MIN = 30

# Hermes host MCP often interpolates a separate env name in config.yaml.
API_KEY_ENVS = (
    "REQALL_API_KEY",
    "MCP_REQALL_API_KEY",
    "REQALL_MCP_API_KEY",
)


def api_url(env: Dict[str, str] | None = None) -> str:
    e = env if env is not None else os.environ
    raw = (e.get("REQALL_URL") or e.get("REQALL_API_URL") or DEFAULT_URL).strip()
    return raw.rstrip("/")


def api_key(env: Dict[str, str] | None = None) -> str:
    """Return the first non-empty Reqall bearer token.

    Accepts REQALL_API_KEY (preferred) and the MCP-template aliases
    MCP_REQALL_API_KEY / REQALL_MCP_API_KEY so hook HTTP and host MCP
    can share one secret under either name.
    """
    e = env if env is not None else os.environ
    for name in API_KEY_ENVS:
        val = (e.get(name) or "").strip()
        if val:
            return val
    # Optional shared CLI auth file (parity with other Reqall plugins)
    cfg = _load_stored_auth()
    token = cfg.get("access_token") or cfg.get("api_key") or ""
    return str(token).strip()


def api_key_source(env: Dict[str, str] | None = None) -> str:
    """Which lookup produced the token (for status / docs)."""
    e = env if env is not None else os.environ
    for name in API_KEY_ENVS:
        if (e.get(name) or "").strip():
            return name
    cfg = _load_stored_auth()
    if cfg.get("access_token") or cfg.get("api_key"):
        return "stored_auth"
    return "missing"


def project_name_override(env: Mapping[str, str] | None = None) -> str:
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
