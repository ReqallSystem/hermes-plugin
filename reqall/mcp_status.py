"""Detect whether Hermes host has Reqall MCP tools registered."""

from __future__ import annotations

from typing import Any, Dict, List

# Hermes registers HTTP MCP tools as mcp__<server>__<tool>
EXPECTED_MCP_TOOLS = (
    "mcp__reqall__search",
    "mcp__reqall__upsert_project",
    "mcp__reqall__upsert_record",
    "mcp__reqall__get_record",
    "mcp__reqall__list_records",
    "mcp__reqall__upsert_link",
    "mcp__reqall__list_links",
    "mcp__reqall__impact",
    "mcp__reqall__sleep_candidates",
    "mcp__reqall__sleep_apply",
)

# Legacy / docs aliases agents may still search for
NAME_ALIASES_NOTE = (
    "Host MCP names use double underscores: mcp__reqall__search "
    "(not mcp_reqall_search)."
)

SESSION_GUIDANCE = (
    "If MCP tools are registered on the host but missing from this chat's "
    "tool list, start a new session (/new) after enabling MCP or restarting "
    "the gateway — Hermes freezes the tool set for prompt cache on long-lived "
    "conversations. Prefer the plugin tool `reqall` (action=...) which calls "
    "Reqall over HTTP and does not require host MCP injection."
)


def probe_mcp_host() -> Dict[str, Any]:
    """Best-effort snapshot of Reqall MCP visibility inside this process."""
    registered_servers: List[str] = []
    registered_tools: List[str] = []
    errors: List[str] = []

    try:
        from tools.mcp_tool import get_registered_mcp_server_names  # type: ignore

        registered_servers = sorted(get_registered_mcp_server_names() or [])
    except Exception as exc:  # pragma: no cover - host optional
        errors.append(f"mcp_server_probe: {exc}")

    try:
        from tools.registry import registry  # type: ignore

        all_names = registry.get_all_tool_names() or []
        registered_tools = sorted(
            n for n in all_names if "reqall" in n.lower() or n.startswith("mcp__reqall")
        )
    except Exception as exc:  # pragma: no cover
        errors.append(f"registry_probe: {exc}")

    expected_present = [n for n in EXPECTED_MCP_TOOLS if n in registered_tools]
    expected_missing = [n for n in EXPECTED_MCP_TOOLS if n not in registered_tools]
    host_mcp_ok = "reqall" in registered_servers or bool(expected_present)

    return {
        "host_mcp_registered": host_mcp_ok,
        "registered_mcp_servers": registered_servers,
        "registered_reqall_related_tools": registered_tools,
        "expected_mcp_tools_present": expected_present,
        "expected_mcp_tools_missing": expected_missing,
        "name_note": NAME_ALIASES_NOTE,
        "session_guidance": SESSION_GUIDANCE,
        "probe_errors": errors,
    }
