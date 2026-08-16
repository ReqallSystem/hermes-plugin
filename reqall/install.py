"""Install this plugin into every Hermes home that enabled it.

Hermes discovers user plugins from ``$HERMES_HOME/plugins`` only.
Named profiles are separate homes. This module symlinks the running
plugin tree into each enabled-but-empty home so one install serves
every profile that opted in.

Never overwrites an existing plugin checkout. Fail-open.

CLI::

    python3 -m reqall.install
    python3 path/to/hermes-plugin/reqall/install.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from .homes import diagnose_homes, plugin_dir


def plugin_root() -> Path:
    return Path(__file__).resolve().parent.parent


def skip_sync(env: Optional[Mapping[str, str]] = None) -> bool:
    e = env if env is not None else os.environ
    return (e.get("REQALL_SKIP_PROFILE_SYNC") or "").strip() in {
        "1",
        "true",
        "TRUE",
        "yes",
        "YES",
    }


def _same_tree(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return False


def link_into(home: Path, source: Path) -> Dict[str, Any]:
    """Create ``$home/plugins/reqall`` → ``source`` when missing.

    Leaves an existing plugin tree untouched (real dir or other symlink).
    """
    dest = plugin_dir(home)
    result: Dict[str, Any] = {
        "home": str(home),
        "dest": str(dest),
        "source": str(source),
        "ok": True,
        "action": "noop",
    }
    try:
        source = source.resolve()
        if not (source / "plugin.yaml").is_file() and not (source / "__init__.py").is_file():
            result["ok"] = False
            result["error"] = "source_not_plugin"
            return result
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() or dest.is_symlink():
            if _same_tree(dest, source):
                result["action"] = "already"
                return result
            if dest.is_symlink() and not dest.exists():
                dest.unlink()
            else:
                result["action"] = "skipped_existing"
                result["existing"] = str(dest)
                return result
        try:
            dest.symlink_to(source, target_is_directory=True)
            result["action"] = "symlinked"
            return result
        except OSError as exc:
            shutil.copytree(source, dest)
            result["action"] = "copied"
            result["copy_note"] = str(exc)
            return result
    except Exception as exc:
        result["ok"] = False
        result["error"] = str(exc)
        return result


def ensure_installs(
    source: Optional[Path] = None,
    *,
    apply: bool = True,
    env: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Diagnose all homes; optionally symlink this plugin into gaps."""
    src = (source or plugin_root()).resolve()
    homes = diagnose_homes(env=env)
    planned: List[Dict[str, Any]] = []
    applied: List[Dict[str, Any]] = []
    for row in homes:
        if not row["wants_plugin"]:
            continue
        if row["plugin_present"]:
            planned.append({**row, "plan": "ok"})
            continue
        planned.append({**row, "plan": "install"})
        if apply:
            applied.append(link_into(Path(row["home"]), src))
    missing = [row for row in planned if row.get("plan") == "install"]
    return {
        "ok": True,
        "source": str(src),
        "apply": apply,
        "homes": homes,
        "planned": planned,
        "applied": applied,
        "missing_before": len(missing),
        "linked": sum(1 for item in applied if item.get("action") in {"symlinked", "copied"}),
    }


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    apply = "--dry-run" not in args
    payload = ensure_installs(apply=apply)
    print(json.dumps(payload, indent=2, default=str))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
