"""Reqall plugin entry — Hermes Agent host."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .reqall import client, state
from .reqall.config import api_key, api_key_source, api_url
from .reqall.homes import format_install_hint, missing_enabled_homes
from .reqall.hooks import (
    on_session_end,
    on_session_start,
    post_tool_call,
    pre_llm_call,
    pre_tool_call,
)
from .reqall.install import ensure_installs, skip_sync
from .reqall.mcp_status import probe_mcp_host
from .reqall.project import resolve_project_name

logger = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parent

SKILLS = (
    ("reqall-context", "skills/context/SKILL.md", "Gather Reqall project context before work"),
    ("reqall-persist", "skills/persist/SKILL.md", "Persist session outcomes to Reqall"),
    ("reqall-document", "skills/document/SKILL.md", "Document one meaningful work item"),
    ("reqall-triage", "skills/triage/SKILL.md", "Triage incoming issues into Reqall"),
    ("reqall-review", "skills/review/SKILL.md", "Review open Reqall records"),
    ("reqall-sleep", "skills/sleep/SKILL.md", "Compress Reqall memory (SLEEP)"),
)

# MCP tool names the native `reqall` action tool can invoke via HTTP.
REQALL_ACTIONS = (
    "search",
    "upsert_project",
    "upsert_record",
    "get_record",
    "list_records",
    "delete_record",
    "list_projects",
    "upsert_link",
    "delete_link",
    "list_links",
    "impact",
    "sleep_candidates",
    "sleep_apply",
    "list_shares",
)


def register(ctx) -> None:
    ctx.register_hook("on_session_start", on_session_start)
    ctx.register_hook("pre_llm_call", pre_llm_call)
    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("post_tool_call", post_tool_call)
    ctx.register_hook("on_session_end", on_session_end)

    ctx.register_tool(
        name="reqall_status",
        toolset="reqall",
        schema={
            "name": "reqall_status",
            "description": (
                "Show Reqall plugin status: auth, API URL, project name, session "
                "dirty flag, host MCP (mcp__reqall__* or mcp__Reqall__*), and "
                "whether other Hermes profiles enabled this plugin without files. "
                "Set check_auth=true to ping the API. Set ensure_install=true to "
                "symlink this plugin into those homes. For writes when MCP tools "
                "are missing, use `reqall` (action=upsert_record). If skill_view "
                "is disabled, use reqall_skill or /reqall persist|context|sleep."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "check_auth": {
                        "type": "boolean",
                        "description": "If true, ping upsert_project to verify auth",
                    },
                    "ensure_install": {
                        "type": "boolean",
                        "description": (
                            "If true, symlink this plugin into other Hermes "
                            "profiles that list reqall in plugins.enabled but "
                            "have no $HERMES_HOME/plugins/reqall"
                        ),
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Optional project directory override",
                    },
                },
            },
        },
        handler=_handle_status,
        description="Reqall auth/project/session/MCP/profile-install status",
        emoji="🧠",
    )

    ctx.register_tool(
        name="reqall",
        toolset="reqall",
        schema={
            "name": "reqall",
            "description": (
                "Call Reqall memory API (same operations as MCP server `reqall`). "
                "Use when host tools mcp__reqall__* / mcp__Reqall__* are unavailable. "
                "Actions: search, upsert_project, upsert_record, get_record, "
                "list_records, upsert_link, list_links, impact, sleep_candidates, "
                "sleep_apply, list_projects, delete_record, delete_link, list_shares. "
                "Pass MCP argument fields in `arguments`."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": (
                            "Reqall operation name (e.g. upsert_record, search). "
                            f"One of: {', '.join(REQALL_ACTIONS)}"
                        ),
                    },
                    "arguments": {
                        "type": "object",
                        "description": (
                            "Arguments for the operation (project_id, kind, title, "
                            "body, query, …). Same shape as MCP tools/call arguments."
                        ),
                        "additionalProperties": True,
                    },
                },
                "required": ["action"],
            },
        },
        handler=_handle_reqall_action,
        description="Reqall API (search/upsert/link/sleep) via plugin HTTP client",
        emoji="🧠",
    )

    ctx.register_tool(
        name="reqall_skill",
        toolset="reqall",
        schema={
            "name": "reqall_skill",
            "description": (
                "Return a bundled Reqall skill body. Use this when host "
                "skill_view is unavailable (skills toolset disabled) so "
                "persist/context/sleep instructions are still readable."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": (
                            "Skill name: reqall-context, reqall-persist, "
                            "reqall-document, reqall-triage, reqall-review, "
                            "reqall-sleep (reqall- prefix optional)"
                        ),
                    },
                },
                "required": ["name"],
            },
        },
        handler=_handle_reqall_skill,
        description="Load a bundled Reqall skill without skill_view",
        emoji="🧠",
    )

    ctx.register_command(
        name="reqall",
        handler=_slash_reqall,
        description=(
            "Reqall memory: status | check | context | persist | sleep | "
            "ensure-install | clear-dirty"
        ),
        args_hint=(
            "status | check | context | persist | document | triage | review | "
            "sleep [org/repo] | ensure-install | clear-dirty"
        ),
    )

    skills_ok: List[str] = []
    for name, rel, desc in SKILLS:
        path = PLUGIN_ROOT / rel
        if not path.exists():
            logger.warning("reqall skill %s missing at %s", name, path)
            continue
        try:
            # Hermes PluginContext.register_skill requires pathlib.Path (calls .exists()).
            ctx.register_skill(name, path, desc)
            skills_ok.append(name)
        except TypeError:
            # Older hosts: description kw unsupported
            try:
                ctx.register_skill(name, path)
                skills_ok.append(name)
            except Exception as exc:
                logger.warning("reqall skill %s failed: %s", name, exc)
        except Exception as exc:
            logger.warning("reqall skill %s failed: %s", name, exc)

    try:
        if not skip_sync():
            sync = ensure_installs(PLUGIN_ROOT, apply=True)
            if sync.get("linked"):
                logger.info(
                    "reqall linked plugin into %s other Hermes home(s)",
                    sync.get("linked"),
                )
        still = missing_enabled_homes()
        if still:
            logger.warning("%s", format_install_hint(still))
    except Exception:
        logger.exception("reqall profile-install sync failed (fail-open)")

    logger.info(
        "reqall Hermes plugin registered (skills=%s)",
        ",".join(skills_ok) or "none",
    )


def resolve_skill(name: str) -> Optional[Tuple[str, Path, str]]:
    raw = (name or "").strip().lower()
    if raw.startswith("reqall:"):
        raw = raw[len("reqall:") :]
    for skill_name, rel, desc in SKILLS:
        short = skill_name[len("reqall-") :] if skill_name.startswith("reqall-") else skill_name
        aliases = {skill_name.lower(), short, f"reqall-{short}"}
        if raw in aliases:
            return skill_name, PLUGIN_ROOT / rel, desc
    return None


def _handle_reqall_skill(args: dict, **kwargs) -> str:
    del kwargs
    found = resolve_skill(str(args.get("name") or ""))
    if not found:
        return json.dumps(
            {
                "ok": False,
                "error": "unknown_skill",
                "skills": [n for n, _, _ in SKILLS],
            }
        )
    skill_name, path, desc = found
    if not path.is_file():
        return json.dumps({"ok": False, "error": "skill_missing", "name": skill_name})
    return json.dumps(
        {
            "ok": True,
            "name": skill_name,
            "description": desc,
            "path": str(path),
            "body": path.read_text(encoding="utf-8"),
        },
        indent=2,
    )


def _handle_status(args: dict, **kwargs) -> str:
    del kwargs
    cwd = args.get("cwd")
    project = resolve_project_name(cwd if isinstance(cwd, str) else None)
    key = api_key()
    mcp = probe_mcp_host()
    warnings: List[str] = []
    payload: Dict[str, Any] = {
        "ok": True,
        "plugin_root": str(PLUGIN_ROOT),
        "plugin_loaded": True,
        "api_url": api_url(),
        "auth_configured": bool(key),
        "auth_source": api_key_source(),
        "auth_preview": (key[:4] + "…" + key[-4:]) if key and len(key) > 10 else bool(key),
        "project_name": project,
        "mcp_url": f"{api_url()}/mcp",
        "mcp_tool_name_example": "mcp__reqall__upsert_record",
        "plugin_api_tool": "reqall",
        "skills": [n for n, _, _ in SKILLS],
        "session": state.load("default"),
        "mcp_host": mcp,
    }
    if args.get("ensure_install"):
        payload["ensure_install"] = ensure_installs(PLUGIN_ROOT, apply=True)
    try:
        missing = missing_enabled_homes()
        payload["profile_installs_missing"] = missing
        if missing:
            warnings.append(format_install_hint(missing))
    except Exception as exc:
        payload["profile_installs_error"] = str(exc)

    skills_host = (mcp or {}).get("skills_host") or {}
    if skills_host.get("hint"):
        warnings.append(str(skills_host["hint"]))

    if not mcp.get("host_mcp_registered"):
        warnings.append(
            "Host MCP tools for server 'reqall' not detected in this process. "
            "Use plugin tool `reqall` with action=…, or enable mcp_servers.reqall "
            "(any case) and restart gateway + /new session."
        )
    elif mcp.get("expected_mcp_tools_missing"):
        warnings.append(
            "Some expected Reqall MCP ops are missing from the registry. "
            + mcp.get("session_guidance", "")
        )
    if args.get("check_auth"):
        if not key:
            payload["auth_check"] = {"ok": False, "error": "auth_missing"}
        else:
            payload["auth_check"] = client.upsert_project(project)
    if warnings:
        payload["warning"] = " ".join(warnings)
        payload["warnings"] = warnings
    return json.dumps(payload, indent=2, default=str)


def _handle_reqall_action(args: dict, **kwargs) -> str:
    del kwargs
    action = (args.get("action") or "").strip()
    if not action:
        return json.dumps({"ok": False, "error": "action_required", "actions": list(REQALL_ACTIONS)})
    if action not in REQALL_ACTIONS:
        return json.dumps(
            {
                "ok": False,
                "error": "unknown_action",
                "action": action,
                "actions": list(REQALL_ACTIONS),
            }
        )
    arguments = args.get("arguments") or {}
    if not isinstance(arguments, dict):
        return json.dumps({"ok": False, "error": "arguments_must_be_object"})
    result = client.mcp_call(action, arguments)
    return json.dumps(result, indent=2, default=str)


def _slash_reqall(raw_args: str) -> str:
    text = (raw_args or "").strip()
    parts = text.split(None, 1)
    verb = (parts[0] if parts else "status").lower()
    rest = parts[1].strip() if len(parts) > 1 else ""
    if verb in {"", "status", "info"}:
        return _handle_status({"check_auth": False})
    if verb in {"ping", "check"}:
        return _handle_status({"check_auth": True})
    if verb in {"ensure-install", "ensure_install", "sync-profiles"}:
        return _handle_status({"ensure_install": True})
    if verb == "clear-dirty":
        state.clear_dirty("default")
        return "Reqall dirty flag cleared for default session."
    skill_verbs = {
        "context": "reqall-context",
        "persist": "reqall-persist",
        "document": "reqall-document",
        "triage": "reqall-triage",
        "review": "reqall-review",
        "sleep": "reqall-sleep",
    }
    if verb in skill_verbs:
        dumped = json.loads(_handle_reqall_skill({"name": skill_verbs[verb]}))
        if not dumped.get("ok"):
            return json.dumps(dumped, indent=2)
        header = (
            f"# {dumped['name']}\n\n"
            "Host skill_view is optional. Follow this skill now using plugin "
            "tool `reqall` (action=…) or host mcp__reqall__* / mcp__Reqall__*.\n"
        )
        if verb == "sleep" and rest:
            header += f"\nProject hint: `{rest}`\n"
        if verb == "persist":
            header += (
                "\nAfter you upsert records, call /reqall clear-dirty "
                "so the persist nudge resets.\n"
            )
        return header + "\n" + dumped.get("body", "")
    return (
        "Usage: /reqall status | check | context | persist | document | "
        "triage | review | sleep [org/repo] | ensure-install | clear-dirty\n"
        "Plugin API tool: reqall action=<mcp_tool_name> arguments={...}\n"
        "Skill dump (no skill_view): reqall_skill or /reqall persist|context|…\n"
        "Host MCP names: mcp__reqall__search or mcp__Reqall__search (any case)\n"
        "Auth: REQALL_API_KEY or MCP_REQALL_API_KEY\n"
        "MCP URL: ${REQALL_URL}/mcp with Bearer token."
    )
