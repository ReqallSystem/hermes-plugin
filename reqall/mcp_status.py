"""Detect whether Hermes host has Reqall MCP tools registered."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

# Canonical (lower-case) MCP names. Hermes prefixes mcp__<server>__<tool>
# using the config key as-is, so `mcp_servers.Reqall` becomes mcp__Reqall__*.
EXPECTED_MCP_OPS = (
    "search",
    "upsert_project",
    "upsert_record",
    "get_record",
    "list_records",
    "upsert_link",
    "list_links",
    "impact",
    "sleep_candidates",
    "sleep_apply",
)

EXPECTED_MCP_TOOLS = tuple(f"mcp__reqall__{op}" for op in EXPECTED_MCP_OPS)

# Legacy / docs aliases agents may still search for
NAME_ALIASES_NOTE = (
    "Host MCP names use double underscores and the mcp_servers key as-is: "
    "mcp__reqall__search or mcp__Reqall__search (not mcp_reqall_search). "
    "Match case-insensitively."
)

SESSION_GUIDANCE = (
    "If MCP tools are registered on the host but missing from this chat's "
    "tool list, start a new session (/new) after enabling MCP or restarting "
    "the gateway — Hermes freezes the tool set for prompt cache on long-lived "
    "conversations. Prefer the plugin tool `reqall` (action=...) which calls "
    "Reqall over HTTP and does not require host MCP injection."
)


def _norm(name: str) -> str:
    return (name or "").strip().lower()


def is_reqall_mcp_tool(name: str) -> bool:
    return _norm(name).startswith("mcp__reqall__")


def mcp_op_name(name: str) -> str:
    n = _norm(name)
    prefix = "mcp__reqall__"
    return n[len(prefix) :] if n.startswith(prefix) else ""


def match_expected(
    registered_tools: Iterable[str],
) -> Dict[str, List[str]]:
    by_op = {op: [] for op in EXPECTED_MCP_OPS}
    extras: List[str] = []
    for raw in registered_tools:
        if not is_reqall_mcp_tool(raw):
            continue
        op = mcp_op_name(raw)
        if op in by_op:
            by_op[op].append(raw)
        else:
            extras.append(raw)
    present = [f"mcp__reqall__{op}" for op, found in by_op.items() if found]
    missing = [f"mcp__reqall__{op}" for op, found in by_op.items() if not found]
    actual = [name for found in by_op.values() for name in found]
    return {
        "expected_mcp_tools_present": present,
        "expected_mcp_tools_missing": missing,
        "actual_mcp_tool_names": actual,
        "extra_reqall_mcp_tools": extras,
    }


def skills_host_probe(all_tool_names: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    names = list(all_tool_names or [])
    lower = {_norm(n) for n in names}
    return {
        "skill_view_available": "skill_view" in lower,
        "skill_manage_available": "skill_manage" in lower,
        "hint": (
            None
            if "skill_view" in lower
            else (
                "Host skills toolset is not in this session (often "
                "agent.disabled_toolsets: [skills]). Use plugin tool "
                "`reqall_skill` or `/reqall persist|context|sleep` to "
                "load skill text without skill_view."
            )
        ),
    }


def probe_mcp_host() -> Dict[str, Any]:
    """Best-effort snapshot of Reqall MCP visibility inside this process."""
    registered_servers: List[str] = []
    registered_tools: List[str] = []
    all_tool_names: List[str] = []
    errors: List[str] = []

    try:
        from tools.mcp_tool import get_registered_mcp_server_names  # type: ignore

        registered_servers = sorted(get_registered_mcp_server_names() or [])
    except Exception as exc:  # pragma: no cover - host optional
        errors.append(f"mcp_server_probe: {exc}")

    try:
        from tools.registry import registry  # type: ignore

        all_tool_names = list(registry.get_all_tool_names() or [])
        registered_tools = sorted(
            n
            for n in all_tool_names
            if "reqall" in n.lower() or _norm(n).startswith("mcp__reqall")
        )
    except Exception as exc:  # pragma: no cover
        errors.append(f"registry_probe: {exc}")

    matched = match_expected(registered_tools)
    server_hit = any(_norm(s) == "reqall" for s in registered_servers)
    host_mcp_ok = server_hit or bool(matched["expected_mcp_tools_present"])

    return {
        "host_mcp_registered": host_mcp_ok,
        "registered_mcp_servers": registered_servers,
        "registered_reqall_related_tools": registered_tools,
        "expected_mcp_tools_present": matched["expected_mcp_tools_present"],
        "expected_mcp_tools_missing": matched["expected_mcp_tools_missing"],
        "actual_mcp_tool_names": matched["actual_mcp_tool_names"],
        "name_note": NAME_ALIASES_NOTE,
        "session_guidance": SESSION_GUIDANCE,
        "skills_host": skills_host_probe(all_tool_names),
        "probe_errors": errors,
    }
