"""Reqall plugin entry — Hermes Agent host."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .reqall import client, state
from .reqall.config import api_key, api_url
from .reqall.hooks import (
    on_session_end,
    on_session_start,
    post_tool_call,
    pre_llm_call,
    pre_tool_call,
)
from .reqall.project import resolve_project_name

logger = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parent

SKILLS = (
    ("reqall-context", "skills/context/SKILL.md"),
    ("reqall-persist", "skills/persist/SKILL.md"),
    ("reqall-document", "skills/document/SKILL.md"),
    ("reqall-triage", "skills/triage/SKILL.md"),
    ("reqall-review", "skills/review/SKILL.md"),
    ("reqall-sleep", "skills/sleep/SKILL.md"),
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
                "Show Reqall plugin status: auth configured, API URL, resolved "
                "project name, session dirty flag. Does not call the network "
                "unless check_auth=true."
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
        description="Reqall auth/project/session status",
        emoji="🧠",
    )

    ctx.register_command(
        name="reqall",
        handler=_slash_reqall,
        description="Reqall memory: status | context | persist | clear-dirty",
        args_hint="status | context | persist | clear-dirty",
    )

    for name, rel in SKILLS:
        path = PLUGIN_ROOT / rel
        if path.exists():
            try:
                ctx.register_skill(name, str(path))
            except Exception as exc:
                logger.warning("reqall skill %s failed: %s", name, exc)

    logger.info("reqall Hermes plugin registered")


def _handle_status(args: dict, **kwargs) -> str:
    del kwargs
    cwd = args.get("cwd")
    project = resolve_project_name(cwd if isinstance(cwd, str) else None)
    key = api_key()
    payload = {
        "ok": True,
        "api_url": api_url(),
        "auth_configured": bool(key),
        "auth_preview": (key[:4] + "…" + key[-4:]) if len(key) > 10 else bool(key),
        "project_name": project,
        "mcp_hint": f"{api_url()}/mcp",
        "skills": [n for n, _ in SKILLS],
        "session": state.load("default"),
    }
    if args.get("check_auth"):
        if not key:
            payload["auth_check"] = {"ok": False, "error": "auth_missing"}
        else:
            payload["auth_check"] = client.upsert_project(project)
    return json.dumps(payload, indent=2, default=str)


def _slash_reqall(raw_args: str) -> str:
    text = (raw_args or "").strip()
    verb = (text.split() or ["status"])[0].lower()
    if verb in {"", "status", "info"}:
        return _handle_status({"check_auth": False})
    if verb in {"ping", "check"}:
        return _handle_status({"check_auth": True})
    if verb == "clear-dirty":
        state.clear_dirty("default")
        return "Reqall dirty flag cleared for default session."
    if verb == "context":
        return (
            "Run skill **reqall-context** (or MCP: upsert_project → search → "
            "list_records). Hooks also inject recall on non-trivial turns when "
            "REQALL_API_KEY is set."
        )
    if verb == "persist":
        state.clear_dirty("default")
        return (
            "Run skill **reqall-persist** now: classify session work and "
            "upsert_record / upsert_link. Dirty flag cleared so the nudge resets."
        )
    return (
        "Usage: /reqall status | check | context | persist | clear-dirty\n"
        "MCP: configure reqall server at ${REQALL_URL}/mcp with Bearer REQALL_API_KEY."
    )
