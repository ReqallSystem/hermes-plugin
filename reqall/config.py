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
_PLUGIN_SETTINGS: Dict[str, Dict[str, Any]] = {}


def hermes_home() -> Path:
    """Resolve the active host context; standalone use stays under its own HOME."""
    try:
        from hermes_constants import get_hermes_home
    except ImportError:
        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes").expanduser()
    return Path(get_hermes_home()).expanduser()


def _scope_key() -> str:
    return str(hermes_home().resolve())


def load_plugin_settings(settings: Optional[Mapping[str, Any]]) -> None:
    """Replace the in-process settings cache (fail-open callers)."""
    _PLUGIN_SETTINGS[_scope_key()] = {
        str(key): value for key, value in (settings or {}).items() if value is not None
    }


def plugin_settings() -> Dict[str, Any]:
    return dict(_PLUGIN_SETTINGS.get(_scope_key(), {}))


def _hermes_file_settings(env: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """Best-effort read of plugins.entries.reqall.settings from $HERMES_HOME."""
    home = Path(env["HERMES_HOME"]).expanduser() if env and env.get("HERMES_HOME") else hermes_home()
    path = home / "config.yaml"
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
    merged.update(plugin_settings())
    return merged


def api_url(env: Dict[str, str] | None = None) -> str:
    e = env if env is not None else os.environ
    raw = str(e.get("REQALL_URL") or e.get("REQALL_API_URL") or _merged_settings(env).get("api_url") or DEFAULT_URL).strip()
    return raw.rstrip("/")


def _credential(env=None):
    scoped = env is not None
    if env is not None:
        getter = env.get
    else:
        try:
            from agent.secret_scope import get_secret, current_secret_scope, is_multiplex_active
        except ImportError:
            getter = os.environ.get
        else:
            getter = get_secret
            scoped = current_secret_scope() is not None or is_multiplex_active()
        try:
            from hermes_constants import get_hermes_home_override
            scoped = scoped or bool(get_hermes_home_override())
        except ImportError:
            pass
    for name in API_KEY_ENVS:
        try:
            val = str(getter(name) or "").strip()
        except Exception:
            return "", "missing"
        if val:
            return val, name
    if not scoped:
        cfg = _load_stored_auth()
        token = cfg.get("access_token") or cfg.get("api_key") or ""
        if token:
            return str(token).strip(), "stored_auth"
    return "", "missing"


def api_key(env: Dict[str, str] | None = None) -> str:
    """Resolve scoped secrets; shared CLI auth is available only when unscoped."""
    return _credential(env)[0]


def api_key_source(env: Dict[str, str] | None = None) -> str:
    return _credential(env)[1]


def machine_name_override(env: Mapping[str, str] | None = None) -> str:
    e = env if env is not None else os.environ
    return str(e.get("REQALL_MACHINE_NAME") or _merged_settings(env).get("machine_name") or "").strip()


def project_name_override(env: Mapping[str, str] | None = None) -> str:
    e = env if env is not None else os.environ
    env_val = (e.get("REQALL_PROJECT_NAME") or "").strip()
    if env_val:
        return env_val
    raw = _merged_settings(env).get("project_name")
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
    val = _merged_settings(env).get("skip_profile_sync")
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
    val = _merged_settings(env).get(setting_name)
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
