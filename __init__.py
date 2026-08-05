"""Reqall plugin entry — Hermes Agent host."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .reqall import client, state
from .reqall.config import api_key, api_url
from .reqall.hooks import (
    on_session_end,
    on_session_start,
    post_tool_call,
    pre_llm_call,
    pre_tool_call,
)
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
                "dirty flag, and whether host MCP tools (mcp__reqall__*) are "
                "registered. Set check_auth=true to ping the API. "
                "For writes when MCP tools are missing from the model list, use "
                "the `reqall` tool (action=upsert_record, …)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "check_auth": {
                        "type": "boolean",
                        "description": "If true, ping upsert_project to verify auth",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Optional project directory override",
                    },
                },
            },
        },
        handler=_handle_status,
        description="Reqall auth/project/session/MCP status",
        emoji="🧠",
    )

    ctx.register_tool(
        name="reqall",
        toolset="reqall",
        schema={
            "name": "reqall",
            "description": (
                "Call Reqall memory API (same operations as MCP server `reqall`). "
                "Use when host tools mcp__reqall__* are unavailable in this session. "
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

    ctx.register_command(
        name="reqall",
        handler=_slash_reqall,
        description="Reqall memory: status | check | context | persist | sleep | clear-dirty",
        args_hint="status | check | context | persist | sleep [org/repo] | clear-dirty",
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

    logger.info(
        "reqall Hermes plugin registered (skills=%s)",
        ",".join(skills_ok) or "none",
    )


def _handle_status(args: dict, **kwargs) -> str:
    del kwargs
    cwd = args.get("cwd")
    project = resolve_project_name(cwd if isinstance(cwd, str) else None)
    key = api_key()
    mcp = probe_mcp_host()
    payload: Dict[str, Any] = {
        "ok": True,
        "api_url": api_url(),
        "auth_configured": bool(key),
        "auth_preview": (key[:4] + "…" + key[-4:]) if key and len(key) > 10 else bool(key),
        "project_name": project,
        "mcp_url": f"{api_url()}/mcp",
        "mcp_tool_name_example": "mcp__reqall__upsert_record",
        "plugin_api_tool": "reqall",
        "skills": [n for n, _, _ in SKILLS],
        "session": state.load("default"),
        "mcp_host": mcp,
    }
    if not mcp.get("host_mcp_registered"):
        payload["warning"] = (
            "Host MCP tools for server 'reqall' not detected in this process. "
            "Use plugin tool `reqall` with action=…, or enable mcp_servers.reqall "
            "and restart gateway + /new session."
        )
    elif mcp.get("expected_mcp_tools_missing"):
        payload["warning"] = (
            "Some expected mcp__reqall__* tools are missing from the registry. "
            + mcp.get("session_guidance", "")
        )
    if args.get("check_auth"):
        if not key:
            payload["auth_check"] = {"ok": False, "error": "auth_missing"}
        else:
            payload["auth_check"] = client.upsert_project(project)
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
    if verb == "clear-dirty":
        state.clear_dirty("default")
        return "Reqall dirty flag cleared for default session."
    if verb == "context":
        return (
            "Run skill **reqall:reqall-context** (qualified) or **reqall-context** if mapped.\n"
            "Tools: plugin `reqall` action=search|list_records, or host MCP "
            "`mcp__reqall__search` / `mcp__reqall__list_records` when present.\n"
            "Hooks also inject recall on non-trivial turns when REQALL_API_KEY is set.\n"
            "If MCP tools are missing mid-session: use `reqall` tool or /new after gateway restart."
        )
    if verb == "persist":
        state.clear_dirty("default")
        return (
            "Run skill **reqall:reqall-persist** now: classify session work and "
            "call plugin tool `reqall` with action=upsert_record / upsert_link "
            "(or mcp__reqall__* if in your tool list). Dirty flag cleared so the nudge resets."
        )
    if verb == "sleep":
        proj = rest or "(current project)"
        return (
            f"Run skill **reqall:reqall-sleep** for project `{proj}`.\n"
            "SLEEP compresses memory: consolidate · split · compact · skip · crosslink.\n"
            "User invoked sleep → rewrite/delete expected. Use decision table in the skill.\n"
            "Tools: `reqall` action=sleep_candidates then sleep_apply "
            "(or mcp__reqall__sleep_candidates / mcp__reqall__sleep_apply)."
        )
    return (
        "Usage: /reqall status | check | context | persist | sleep [org/repo] | clear-dirty\n"
        "Plugin API tool: reqall action=<mcp_tool_name> arguments={...}\n"
        "Host MCP names: mcp__reqall__search, mcp__reqall__upsert_record, …\n"
        "MCP URL: ${REQALL_URL}/mcp with Bearer token."
    )
