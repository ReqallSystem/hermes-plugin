"""Project name detection — mirrors other Reqall host plugins."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse

from .config import project_name_override


def resolve_project_name(
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> str:
    e = env if env is not None else os.environ
    override = project_name_override(e)
    if override:
        return override

    root = Path(cwd).expanduser().resolve() if cwd else Path.cwd()
    remote = _git_origin(root)
    if remote:
        normalized = _normalize_remote(remote)
        if normalized:
            return normalized
    return root.name


def _git_origin(cwd: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if out.returncode == 0:
            return (out.stdout or "").strip()
    except Exception:
        pass
    return ""


def _normalize_remote(remote_url: str) -> str:
    if not remote_url:
        return ""
    trimmed = re.sub(r"\.git$", "", remote_url.strip())
    m = re.search(r"[:/]([^/:]+/[^/]+)$", trimmed)
    if m:
        return m.group(1)
    try:
        path = urlparse(trimmed).path.lstrip("/")
        if path:
            return path
    except Exception:
        pass
    return ""
