"""Discover Hermes homes / profiles and whether they can load this plugin.

Hermes loads user plugins only from ``$HERMES_HOME/plugins/<name>``.
Each named profile uses its own HERMES_HOME (``~/.hermes/profiles/<id>``),
so ``hermes plugins install`` into the default home does not make the
plugin available to other profiles — even when those profiles list
``reqall`` in ``plugins.enabled``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional


def default_hermes_root(env: Optional[Mapping[str, str]] = None) -> Path:
    """User-level Hermes root (parent of ``profiles/``), not a named profile."""
    e = env if env is not None else os.environ
    home = Path(e.get("HOME") or Path.home())
    hermes_home = (e.get("HERMES_HOME") or "").strip()
    if hermes_home:
        p = Path(hermes_home).expanduser()
        if p.parent.name == "profiles":
            return p.parent.parent
        return p
    return home / ".hermes"


def discover_homes(env: Optional[Mapping[str, str]] = None) -> List[Dict[str, Any]]:
    """Return candidate Hermes homes: default root + each named profile."""
    e = env if env is not None else os.environ
    root = default_hermes_root(e)
    found: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def _add(name: str, path: Path) -> None:
        try:
            resolved = str(path.expanduser().resolve())
        except OSError:
            resolved = str(path)
        if resolved in seen:
            return
        seen.add(resolved)
        found.append({"name": name, "home": path, "home_resolved": resolved})

    _add("default", root)

    current = (e.get("HERMES_HOME") or "").strip()
    if current:
        cur = Path(current).expanduser()
        if cur.parent.name == "profiles":
            _add(cur.name, cur)
        elif cur.resolve() != root.resolve():
            _add("current", cur)

    profiles = root / "profiles"
    try:
        if profiles.is_dir():
            for child in sorted(profiles.iterdir()):
                if child.is_dir() and not child.name.startswith("."):
                    _add(child.name, child)
    except OSError:
        pass

    return found


def _load_mapping(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return _loose_config(text)


def _loose_config(text: str) -> Dict[str, Any]:
    """Best-effort plugins.enabled + disabled_toolsets without PyYAML."""
    enabled: List[str] = []
    disabled_toolsets: List[str] = []
    section = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        stripped = line.strip()
        if stripped in {"plugins:", "agent:"}:
            section = stripped[:-1]
            continue
        if stripped == "enabled:" and section == "plugins":
            section = "plugins.enabled"
            continue
        if stripped == "disabled_toolsets:" and section == "agent":
            section = "agent.disabled_toolsets"
            continue
        if stripped.startswith("- ") and section == "plugins.enabled":
            enabled.append(stripped[2:].strip().strip("'\""))
        elif stripped.startswith("- ") and section == "agent.disabled_toolsets":
            disabled_toolsets.append(stripped[2:].strip().strip("'\""))
        elif stripped and not line.startswith(" ") and not line.startswith("\t"):
            section = None
    out: Dict[str, Any] = {}
    if enabled:
        out["plugins"] = {"enabled": enabled}
    if disabled_toolsets:
        out["agent"] = {"disabled_toolsets": disabled_toolsets}
    return out


def _enabled_plugins(config: Dict[str, Any]) -> List[str]:
    plugins = config.get("plugins")
    if not isinstance(plugins, dict):
        return []
    enabled = plugins.get("enabled")
    if not isinstance(enabled, list):
        return []
    return [str(item) for item in enabled]


def wants_reqall_plugin(config: Dict[str, Any]) -> bool:
    """True when this home opted into the native plugin (not MCP-only)."""
    return any(name.lower() == "reqall" for name in _enabled_plugins(config))


def skills_toolset_disabled(config: Dict[str, Any]) -> bool:
    agent = config.get("agent")
    if not isinstance(agent, dict):
        return False
    disabled = agent.get("disabled_toolsets")
    if not isinstance(disabled, list):
        return False
    return any(str(item).lower() == "skills" for item in disabled)


def plugin_dir(home: Path) -> Path:
    return Path(home) / "plugins" / "reqall"


def plugin_present(home: Path) -> bool:
    dest = plugin_dir(home)
    return (dest / "plugin.yaml").is_file() or (dest / "__init__.py").is_file()


def diagnose_homes(
    env: Optional[Mapping[str, str]] = None,
    homes: Optional[Iterable[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Per-home snapshot: wants plugin, files present, skills toolset."""
    rows = []
    for item in homes if homes is not None else discover_homes(env):
        home = Path(item["home"])
        config = _load_mapping(home / "config.yaml")
        dest = plugin_dir(home)
        row = {
            "name": item.get("name"),
            "home": str(home),
            "wants_plugin": wants_reqall_plugin(config),
            "plugin_present": plugin_present(home),
            "plugin_path": str(dest),
            "plugin_is_symlink": dest.is_symlink(),
            "skills_toolset_disabled": skills_toolset_disabled(config),
        }
        if dest.is_symlink():
            try:
                row["plugin_symlink_target"] = str(dest.resolve())
            except OSError:
                row["plugin_symlink_target"] = None
        rows.append(row)
    return rows


def missing_enabled_homes(
    env: Optional[Mapping[str, str]] = None,
    homes: Optional[Iterable[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    return [
        row
        for row in diagnose_homes(env=env, homes=homes)
        if row["wants_plugin"] and not row["plugin_present"]
    ]


def format_install_hint(missing: List[Dict[str, Any]]) -> str:
    if not missing:
        return ""
    names = ", ".join(str(row.get("name") or row.get("home")) for row in missing)
    return (
        "These Hermes homes enable plugin 'reqall' but have no plugin files "
        f"under $HERMES_HOME/plugins/reqall: {names}. "
        "Hermes does not share user plugins across profiles. "
        "From any copy of this plugin run: python3 -m reqall.install "
        "(or /reqall ensure-install). Then restart that profile's gateway "
        "from an external shell and /new."
    )
