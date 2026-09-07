"""Project binding — never invent a Reqall project from a generic cwd."""

from __future__ import annotations

import os
import re
import socket
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional
from urllib.parse import urlparse

from .config import machine_name_override, project_name_override

# Basenames that are home/workspace noise, not a Reqall project id.
GENERIC_DIR_NAMES = frozenset(
    {
        "",
        "~",
        "home",
        "users",
        "user",
        "ubuntu",
        "root",
        "tmp",
        "temp",
        "var",
        "opt",
        "src",
        "app",
        "apps",
        "code",
        "src",
        "workspace",
        "workspaces",
        "work",
        "project",
        "projects",
        "repo",
        "repos",
        "dev",
        "devel",
        "desktop",
        "documents",
        "downloads",
        "hermes",
        ".hermes",
        "profiles",
        "plugins",
    }
)

_PROJECT_KV = re.compile(
    r"(?<![\w/-])project(?:_name)?\s*[:=]\s*"
    r"(?:`([^`\r\n]+)`|'([^'\r\n]+)'|\"([^\"\r\n]+)\"|([^\s`'\",;]+))",
    re.I,
)


@dataclass(frozen=True)
class ProjectBinding:
    name: Optional[str]
    source: str
    safe_to_upsert: bool

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def is_generic_dirname(name: str) -> bool:
    raw = (name or "").strip().lower().rstrip("/")
    if raw in GENERIC_DIR_NAMES:
        return True
    if raw.startswith("."):
        return True
    return False


def is_generic_cwd(cwd: Path) -> bool:
    try:
        resolved = cwd.expanduser().resolve()
    except OSError:
        resolved = cwd
    if is_generic_dirname(resolved.name):
        return True
    try:
        home = Path.home().resolve()
        if resolved == home or resolved == home.parent:
            return True
    except OSError:
        pass
    if str(resolved) in {"/", "/home", "/Users", "/tmp", "/var", "/opt"}:
        return True
    return False


def extract_project_hint(text: str) -> Optional[str]:
    """Accept only explicitly labelled selections, never incidental slash tokens."""
    if not text:
        return None
    kv = _PROJECT_KV.search(text)
    if kv:
        return next(value for value in kv.groups() if value is not None).strip() or None
    return None


def machine_project_name(env: Optional[Mapping[str, str]] = None) -> str:
    """Claude-compatible reserved machine/OS-user bucket, never cwd-derived."""
    def clean(segment: str) -> str:
        return re.sub(r"[\\/\s]+", "-", segment.strip()).strip("-") or "unknown"

    host = machine_name_override(env)
    if not host:
        try:
            host = socket.gethostname().split(".")[0]
        except OSError:
            host = "unknown"
    try:
        import pwd

        user = pwd.getpwuid(os.getuid()).pw_name or "unknown"
    except ImportError:
        # Windows has no pwd module. Use OS identity, not USER/USERNAME env hints.
        try:
            user = os.getlogin() or "unknown"
        except (AttributeError, OSError):
            user = "unknown"
    except (AttributeError, KeyError, OSError):
        user = "unknown"
    return f".machine/{clean(host).lower()}/{clean(user)}"


def bind_project(
    cwd: Optional[str] = None,
    prompt: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
) -> ProjectBinding:
    """Resolve a Reqall project without creating junk names from $HOME."""
    override = project_name_override(env)
    if override:
        return ProjectBinding(override, "override", True)

    root = Path(cwd).expanduser().resolve() if cwd else Path.cwd()
    remote = _git_origin(root)
    if remote:
        normalized = _normalize_remote(remote)
        if normalized:
            return ProjectBinding(normalized, "git", True)

    hint = extract_project_hint(prompt or "")
    if hint:
        return ProjectBinding(hint, "prompt", True)

    return ProjectBinding(machine_project_name(env), "machine", True)


def resolve_project_name(
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    prompt: Optional[str] = None,
) -> str:
    """Back-compat string form of the deterministic project binding."""
    return bind_project(cwd=cwd, prompt=prompt, env=env).name or ""


def conceptual_query(path_or_cmd: str, user_hint: str = "") -> str:
    """Turn a filesystem path or shell snippet into a meaning-first search query."""
    raw = (path_or_cmd or "").strip()
    hint = (user_hint or "").strip()
    tokens: list[str] = []
    if raw:
        try:
            p = Path(raw.split()[0] if " " in raw and raw[:1] in {"/", ".", "~"} else raw)
            stem = p.stem if p.suffix else p.name
            stem = re.sub(r"[_\-./]+", " ", stem).strip()
            if stem and not is_generic_dirname(stem) and not re.fullmatch(r"[a-f0-9]{7,40}", stem):
                tokens.append(stem)
            parent = p.parent.name if p.parent else ""
            if parent and not is_generic_dirname(parent):
                tokens.append(parent.replace("_", " ").replace("-", " "))
        except Exception:
            pass
        if not tokens:
            words = re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", raw)
            tokens.extend(words[:6])
    if hint:
        tokens.append(hint[:240])
    query = " ".join(dict.fromkeys(t for t in tokens if t)).strip()
    return query[:300]


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
