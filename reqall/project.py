"""Project binding — never invent a Reqall project from a generic cwd."""

from __future__ import annotations

import json
import os
import re
import socket
import stat
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
    r"(?:`([^`\r\n]*)`|'([^'\r\n]*)'|\"([^\"\r\n]*)\"|([^\s`'\",;]+))",
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
    if not text or re.match(r"^\s*\[ASYNC (?:DELEGATION (?:BATCH COMPLETE|COMPLETE|TASK FAILED)\b|SUBAGENT REPORT\])", text):
        # Hermes delivers these notifications as user_message without a trusted
        # synthetic flag. Their quoted task/results are not a user selection.
        return None
    kv = _PROJECT_KV.search(text)
    if kv:
        value = next(value for value in kv.groups() if value is not None)
        if kv.group(4) is not None:
            value = value.rstrip(".,:;!?)]")
        return value.strip() or None
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
    host = clean(host).lower()
    return f".machine/{host}/{clean(user)}"


def bind_project(
    cwd: Optional[str] = None,
    prompt: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    selected: Optional[str] = None,
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

    hint = extract_project_hint(prompt or "") or (selected or "").strip()
    if hint:
        return ProjectBinding(hint, "prompt", True)

    local = _local_portable_name(root, env)
    if local:
        return local

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
    value = remote_url.strip().rstrip("/")
    if not value or re.match(r"^(?:[A-Za-z]:|[\\/]|\.|~)", value) or "\\" in value:
        return ""
    if re.match(r"^(?:https?|ssh|git)://", value, re.I):
        try:
            parsed = urlparse(value)
            if not parsed.hostname:
                return ""
            path = parsed.path
        except ValueError:
            return ""
    else:
        if "://" in value or value.lower().startswith("file:"):
            return ""
        match = re.fullmatch(r"(?:[^\s/@:]+@)?[^\s/:]+:(.+)", value)
        if not match:
            return ""
        path = match.group(1)
    parts = re.sub(r"\.git$", "", path.strip("/")).split("/")
    if len(parts) < 2 or any(part in {"", ".", ".."} for part in parts):
        return ""
    return "/".join(parts[-2:])


_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$")
_YML_KEY = re.compile(r"^(project|name)\s*:\s*(.*)$")


def _yaml_scalar(value: str) -> Optional[str]:
    value = value.strip()
    if value.startswith(('"', "'")):
        match = re.fullmatch(r'''(["'])([^"'\\]*)\1\s*(?:#.*)?''', value)
        return match.group(2) if match else None
    value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
    if value.lower() in {"", "null", "~", "true", "false", "yes", "no", "on", "off"}:
        return None
    if re.fullmatch(r"[+-]?(?:(?:[0-9][0-9_]*(?:\.[0-9_]*)?|\.[0-9_]+)(?:e[+-]?[0-9]+)?|0x[0-9a-f_]+|0o[0-7_]+|0b[01_]+|\.inf|\.nan)", value, re.I):
        return None
    return value


def _yaml_name(text: str) -> str:
    values: Dict[str, Optional[str]] = {}
    for line in text.splitlines():
        # Never truncate multiline scalars or nested YAML into an identity.
        if re.match(r"\s+\S", line) and not line.lstrip().startswith("#"):
            return ""
        match = _YML_KEY.fullmatch(line)
        if not match:
            continue
        key = match.group(1).lower()
        value = _safe_name(_yaml_scalar(match.group(2)))
        if key in values and values[key] != value:
            return ""
        values[key] = value
    return _safe_name(values.get("project")) or _safe_name(values.get("name"))


def _ancestors(start: Path, boundary: Optional[Path] = None):
    cur = start
    seen: set[Path] = set()
    while cur not in seen:
        seen.add(cur)
        yield cur
        if cur == boundary or cur.parent == cur:
            break
        cur = cur.parent


def _safe_name(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    name = value.strip()
    if not _NAME_RE.fullmatch(name) or any(part in {"", ".", ".."} for part in name.split("/")):
        return ""
    return name


def _read_metadata(path: Path, boundary: Optional[Path] = None) -> str:
    """Read at most 64 KiB of a regular UTF-8 file, otherwise ignore it."""
    try:
        if boundary is not None and not path.resolve().is_relative_to(boundary):
            return ""
        if not path.is_file():
            return ""
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
                return ""
            data = b""
            while len(data) <= 65536:
                chunk = os.read(fd, 65537 - len(data))
                if not chunk:
                    break
                data += chunk
        finally:
            os.close(fd)
        return data.decode("utf-8") if len(data) <= 65536 else ""
    except (OSError, UnicodeError, ValueError, RuntimeError):
        return ""


def _reqall_yml_name(root: Path, boundary: Optional[Path] = None) -> Optional[str]:
    for directory in _ancestors(root, boundary):
        for filename in (".reqall.yml", ".reqall.yaml"):
            path = directory / filename
            if not path.is_file():
                continue
            try:
                text = _read_metadata(path, boundary)
            except OSError:
                continue
            name = _yaml_name(text)
            if name:
                return name
    return None


def _package_name(root: Path, boundary: Optional[Path] = None) -> Optional[str]:
    for directory in _ancestors(root, boundary):
        pkg = directory / "package.json"
        if pkg.is_file():
            try:
                data = json.loads(_read_metadata(pkg, boundary))
            except (OSError, json.JSONDecodeError, TypeError):
                data = None
            if isinstance(data, dict):
                raw = data.get("name")
                if isinstance(raw, str) and re.fullmatch(r"@[A-Za-z0-9._-]+/[A-Za-z0-9._-]+", raw.strip()):
                    raw = raw.strip()[1:]
                name = _safe_name(raw)
                if name:
                    return name
        text = re.sub(r"/\*.*?\*/", " ", _read_metadata(directory / "go.mod", boundary), flags=re.S)
        declarations = [line for line in text.splitlines() if re.match(r"\s*module\b", line)]
        if len(declarations) == 1:
            match = re.fullmatch(r'\s*module\s+(?:"([^"\\]+)"|`([^`]+)`|([^\s"`]+))\s*(?://.*)?', declarations[0])
            if match:
                name = _safe_name(next(value for value in match.groups() if value is not None))
                if name:
                    return name
        in_package = False
        name = ""
        seen = False
        cargo = _read_metadata(directory / "Cargo.toml", boundary)
        # Reject unsupported multiline TOML rather than scanning string contents.
        if re.search(r"\"{3}|'{3}", cargo):
            continue
        for line in cargo.splitlines():
            line = line.strip()
            if line.startswith("["):
                in_package = bool(re.fullmatch(r"\[package\]\s*(?:#.*)?", line))
            elif in_package:
                match = re.fullmatch(r"name\s*=\s*(.*)", line)
                if match:
                    raw = match.group(1)
                    value = _safe_name(_yaml_scalar(raw)) if raw.startswith(('"', "'")) else ""
                    if seen and value != name:
                        name = ""
                        break
                    name, seen = value, True
        if name:
            return name
    return None


def _workspace_root(start: Path, env: Optional[Mapping[str, str]]) -> Optional[Path]:
    override = (env if env is not None else os.environ).get("REQALL_WORKSPACE_ROOT", "").strip()
    if override:
        try:
            candidate = Path(override).expanduser()
            base = (candidate if candidate.is_absolute() else start / candidate).resolve()
            return base if base.is_dir() and start.resolve().is_relative_to(base) else None
        except (OSError, ValueError, RuntimeError):
            return None
    for directory in _ancestors(start):
        if (directory / ".reqall-workspace").is_file():
            return directory
    return None


def _workspace_relative(root: Path, env: Optional[Mapping[str, str]]) -> Optional[str]:
    base = _workspace_root(root, env)
    if not base:
        return None
    try:
        rel = root.resolve().relative_to(base)
    except (OSError, ValueError):
        return None
    parts = [p for p in rel.parts if p not in {".", ""}]
    if not parts:
        return None
    return _safe_name("/".join(parts))


def _local_portable_name(root: Path, env: Optional[Mapping[str, str]]) -> Optional[ProjectBinding]:
    try:
        root = root.resolve(strict=True)
        if not root.is_dir():
            return None
    except (OSError, ValueError, RuntimeError):
        return None
    boundary = _workspace_root(root, env)
    yml = _reqall_yml_name(root, boundary)
    if yml:
        return ProjectBinding(yml, "reqall_yml", True)
    pkg = _package_name(root, boundary)
    if pkg:
        return ProjectBinding(pkg, "package", True)
    rel = _workspace_relative(root, env)
    if rel:
        return ProjectBinding(rel, "workspace_relative", True)
    return None
