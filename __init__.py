"""Reqall plugin entry — Hermes Agent host."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .reqall import client, state
from .reqall.config import api_key, api_key_source, api_url, load_plugin_settings, plugin_settings
from .reqall.homes import format_install_hint, missing_enabled_homes
from .reqall.hooks import (
    on_session_end,
    on_session_finalize,
    on_session_start,
    post_tool_call,
    pre_llm_call,
    pre_tool_call,
    pre_verify,
)
from .reqall.install import ensure_installs
from .reqall.mcp_status import probe_mcp_host
from .reqall.project import bind_project

logger = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parent

SKILLS = (
    ("reqall-context", "skills/context/SKILL.md", "Gather Reqall project context before work"),
    ("reqall-intend", "skills/intend/SKILL.md", "Record agreed intent before substantial work"),
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
    "share_project",
    "revoke_share",
    "delete_project",
    "list_prompts",
    "get_prompt",
    "subscribe_project",
    "unsubscribe_project",
    "list_subscriptions",
    "poll_subscriptions",
)


def register(ctx) -> None:
    ctx.register_hook("on_session_start", on_session_start)
    ctx.register_hook("pre_llm_call", pre_llm_call)
    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("post_tool_call", post_tool_call)
    ctx.register_hook("pre_verify", pre_verify)
    ctx.register_hook("on_session_end", on_session_end)
    ctx.register_hook("on_session_finalize", on_session_finalize)

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
                        "description": "If true, perform a read-only list_projects auth check",
                    },
                    "ensure_install": {
                        "type": "boolean",
                        "description": (
                            "If true, symlink this plugin into other Hermes "
                            "profiles that list reqall in plugins.enabled but "
                            "have no $HERMES_HOME/plugins/reqall"
                        ),
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Current session ID when host context is unavailable",
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
                "Actions: search, upsert_*, get_record, list_*, impact, sleep_*, "
                "share_project, revoke_share, list_shares, list_prompts, get_prompt, "
                "subscribe_project, unsubscribe_project, list_subscriptions, "
                "poll_subscriptions (changes since your last poll), "
                "delete_record, delete_link, delete_project. "
                "Deletes and share/revoke only when the user explicitly asked. "
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
                    "session_id": {
                        "type": "string",
                        "description": (
                            "Current session ID when host context is unavailable; "
                            "subscribe/unsubscribe/poll_subscriptions default their "
                            "subscriber to it"
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
                            "Skill name: reqall-context, reqall-intend, reqall-persist, "
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

    ctx.register_tool(
        name="reqall_session",
        toolset="reqall",
        schema={
            "name": "reqall_session",
            "description": (
                "Inspect this session's pending Reqall work, explicitly select agreed "
                "spec/architecture intent, or acknowledge persisted outcomes after "
                "server readback and link verification. Capture work_revision from "
                "status BEFORE persistence; acknowledge never clears newer work. "
                "Supply session_id from the turn context when the host cannot supply it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["status", "select_intent", "acknowledge"]},
                    "session_id": {"type": "string", "description": "Current session identifier, not a project name"},
                    "record_id": {"type": "integer", "minimum": 1, "description": "Existing agreed spec/arch for select_intent"},
                    "record_ids": {"type": "array", "items": {"type": "integer", "minimum": 1}, "description": "Persisted outcome IDs to verify for acknowledge"},
                    "work_revision": {"type": "integer", "minimum": 0, "description": "Revision captured from status before persisting"},
                },
                "required": ["action"],
                "additionalProperties": False,
            },
        },
        handler=_handle_session,
        description="Reqall session intent and verified persistence acknowledgement",
        emoji="🧠",
    )

    ctx.register_command(
        name="reqall",
        handler=_slash_reqall,
        description=(
            "Reqall memory: status | check | context | intend | persist | sleep | "
            "ensure-install"
        ),
        args_hint=(
            "status | check | context | intend | persist | document | triage | review | "
            "sleep [org/repo] | ensure-install"
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
        load_plugin_settings(
            {
                "project_name": ctx.get_config("project_name"),
                "machine_name": ctx.get_config("machine_name"),
                "api_url": ctx.get_config("api_url"),
                "doc_interval_min": ctx.get_config("doc_interval_min"),
                "persist_interval_min": ctx.get_config("persist_interval_min"),
            }
        )
    except Exception:
        logger.debug("reqall plugin settings unavailable (fail-open)", exc_info=True)

    # Loading a plugin must never install it into another profile. Cross-profile
    # diagnostics and installation are explicit user operations only.

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


def _handle_session(args: dict, **kwargs) -> str:
    from .reqall.workflow import handle_session

    result = handle_session(args, **kwargs)
    return result if isinstance(result, str) else json.dumps(result, default=str)


def _handle_status(args: dict, **kwargs) -> str:
    sid = kwargs.get("session_id") or kwargs.get("task_id") or args.get("session_id")
    cwd = args.get("cwd")
    binding = bind_project(cwd=cwd if isinstance(cwd, str) else None)
    project = binding.name or ""
    key = api_key()
    mcp = probe_mcp_host()
    warnings: List[str] = []
    session = state.load(str(sid)) if sid else None
    payload: Dict[str, Any] = {
        "ok": True,
        "plugin_root": str(PLUGIN_ROOT),
        "plugin_loaded": True,
        "api_url": api_url(),
        "auth_configured": bool(key),
        "auth_source": api_key_source(),
        "auth_preview": (key[:4] + "…" + key[-4:]) if key and len(key) > 10 else bool(key),
        "project_name": project or None,
        "project_binding": binding.as_dict(),
        "mcp_url": f"{api_url()}/mcp",
        "mcp_tool_name_example": "mcp__reqall__upsert_record",
        "plugin_api_tool": "reqall",
        "plugin_settings": plugin_settings(),
        "skills": [n for n, _, _ in SKILLS],
        "session": session,
        "session_id": sid or None,
        "subscription": (
            {"project_id": session.get("subscribed_project_id"), "subscriber": sid,
             "unavailable": bool(session.get("subscriptions_unavailable"))}
            if session is not None else None
        ),
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
        payload["auth_check"] = client.mcp_call("list_projects", {"limit": 1})
        payload["auth_check_note"] = "Read-only list_projects probe; no project was created."
    if warnings:
        payload["warning"] = " ".join(warnings)
        payload["warnings"] = warnings
    return json.dumps(payload, indent=2, default=str)


# Subscription cursors are per session: fill in the hook's subscriber label when
# an agent follows the documented manual controls without naming one.
SESSION_SCOPED_ACTIONS = frozenset({"subscribe_project", "unsubscribe_project", "poll_subscriptions"})


def _handle_reqall_action(args: dict, **kwargs) -> str:
    sid = kwargs.get("session_id") or kwargs.get("task_id") or args.get("session_id")
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
    if action in SESSION_SCOPED_ACTIONS and sid and not arguments.get("subscriber"):
        arguments = {**arguments, "subscriber": str(sid)}
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
        return (
            "Unsafe clear-dirty is retired. Use reqall_session action=acknowledge "
            "with this session_id, persisted record_ids and the work_revision "
            "captured before persistence. Records and links are verified before clearing."
        )
    if verb == "prompt":
        if rest:
            return json.dumps(
                client.mcp_call("get_prompt", {"name": rest}),
                indent=2,
                default=str,
            )
        return json.dumps(client.mcp_call("list_prompts", {}), indent=2, default=str)
    skill_verbs = {
        "context": "reqall-context",
        "intend": "reqall-intend",
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
                "\nAfter record/link readbacks, use reqall_session action=acknowledge "
                "with session_id, record_ids and the pre-persist work_revision.\n"
            )
        return header + "\n" + dumped.get("body", "")
    return (
        "Usage: /reqall status | check | context | intend | persist | document | "
        "triage | review | sleep [org/repo] | prompt [name] | ensure-install\n"
        "Plugin API tool: reqall action=<mcp_tool_name> arguments={...}\n"
        "Skill dump (no skill_view): reqall_skill or /reqall persist|context|…\n"
        "Host MCP names: mcp__reqall__search or mcp__Reqall__search (any case)\n"
        "Auth: REQALL_API_KEY or MCP_REQALL_API_KEY\n"
        "MCP URL: ${REQALL_URL}/mcp with Bearer token."
    )
