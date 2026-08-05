# Changelog

## 2026.8.7

- **Fix:** `register_skill` now passes `pathlib.Path` (not `str`). Hermes calls
  `.exists()` on the path; strings caused all six skills to fail registration
  (`'str' object has no attribute 'exists'`).
- **Feat:** Plugin tool `reqall` — multi-action HTTP client for MCP ops
  (`search`, `upsert_record`, `upsert_link`, `sleep_*`, …) so agents can
  persist without host `mcp__reqall__*` tools in the session tool list.
- **Feat:** `reqall_status` reports host MCP probe (`mcp__reqall__*` registry
  presence), correct double-underscore names, and `/new` guidance when tools
  were enabled mid-session.
- **Docs:** AGENTS/README/after-install — MCP naming, session freeze, plugin API tool.

## 2026.8.6

Release tag for Hermes host install. Includes SLEEP memory-compression skill
aligned with Claude/Grok (decision table: consolidate / split / compact /
skip / crosslink), slash `/reqall sleep`, and prior 2026.8.5 work.

## 2026.8.5

- Port SLEEP skill rewrite from Claude/Grok plugins
- `/reqall sleep [org/repo]`
- Docs/AGENTS/README alignment

## 2026.8.4

- Initial Hermes Reqall plugin (hooks, skills, MCP client, status tool)
