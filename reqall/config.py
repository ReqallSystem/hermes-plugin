"""Environment, Hermes plugin settings, and defaults for Reqall."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

DEFAULT_URL = "https://www.reqall.net"
DEFAULT_DOC_INTERVAL_MIN = 10
DEFAULT_PERSIST_INTERVAL_MIN = 30

# Hermes host MCP often interpolates a separate env name in config.yaml.
API_KEY_ENVS = (
    "REQALL_API_KEY",
    "MCP_REQALL_API_KEY",
    "REQALL_MCP_API_KEY",
)

# Filled by register() from plugins.entries.reqall.settings; env still wins.
_PLUGIN_SETTINGS: Dict[str, Any] = {}


def load_plugin_settings(settings: Optional[Mapping[str, Any]]) -> None:
    """Replace the in-process settings cache (fail-open callers)."""
    _PLUGIN_SETTINGS.clear()
    if not settings:
        return
    for key, value in settings.items():
        if value is not None:
            _PLUGIN_SETTINGS[str(key)] = value


def plugin_settings() -> Dict[str, Any]:
    return dict(_PLUGIN_SETTINGS)


def _hermes_file_settings(env: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """Best-effort read of plugins.entries.reqall.settings from $HERMES_HOME."""
    e = env if env is not None else os.environ
    home = (e.get("HERMES_HOME") or "").strip()
    if not home:
        return {}
    path = Path(home).expanduser() / "config.yaml"
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    data: Any = None
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    plugins = data.get("plugins")
    if not isinstance(plugins, dict):
        return {}
    entries = plugins.get("entries")
    if not isinstance(entries, dict):
        return {}
    for key in ("reqall", "Reqall"):
        entry = entries.get(key)
        if isinstance(entry, dict):
            for sub in ("settings", "config"):
                block = entry.get(sub)
                if isinstance(block, dict):
                    return dict(block)
    return {}


def _merged_settings(env: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    merged = _hermes_file_settings(env)
    merged.update(_PLUGIN_SETTINGS)
    return merged


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
    env_val = (e.get("REQALL_PROJECT_NAME") or "").strip()
    if env_val:
        return env_val
    raw = _merged_settings(e).get("project_name")
    return str(raw).strip() if raw else ""


def doc_interval_min(env: Dict[str, str] | None = None) -> float:
    return _float_setting(
        env,
        env_name="REQALL_DOC_INTERVAL_MIN",
        setting_name="doc_interval_min",
        default=DEFAULT_DOC_INTERVAL_MIN,
    )


def persist_interval_min(env: Dict[str, str] | None = None) -> float:
    return _float_setting(
        env,
        env_name="REQALL_PERSIST_INTERVAL_MIN",
        setting_name="persist_interval_min",
        default=DEFAULT_PERSIST_INTERVAL_MIN,
    )


def skip_profile_sync(env: Optional[Mapping[str, str]] = None) -> bool:
    e = env if env is not None else os.environ
    raw = (e.get("REQALL_SKIP_PROFILE_SYNC") or "").strip()
    if raw:
        return raw.lower() in {"1", "true", "yes", "on"}
    val = _merged_settings(e).get("skip_profile_sync")
    if isinstance(val, bool):
        return val
    if val is None:
        return False
    return str(val).strip().lower() in {"1", "true", "yes", "on"}


def _float_setting(
    env: Optional[Mapping[str, str]],
    *,
    env_name: str,
    setting_name: str,
    default: float,
) -> float:
    e = env if env is not None else os.environ
    raw = e.get(env_name)
    if raw is not None and str(raw).strip() != "":
        try:
            return float(raw)
        except ValueError:
            return float(default)
    val = _merged_settings(e).get(setting_name)
    if val is None or val == "":
        return float(default)
    try:
        return float(val)
    except (TypeError, ValueError):
        return float(default)


def _load_stored_auth() -> Dict[str, Any]:
    candidates = []
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        candidates.append(Path(xdg) / "reqall" / "config.json")
    candidates.append(Path.home() / ".config" / "reqall" / "config.json")
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
