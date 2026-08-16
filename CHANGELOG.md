# Changelog

## 2026.8.9

- **Fix:** Project binding no longer treats `$HOME` / `ubuntu` / `src` /
  `workspace` as a Reqall project. Hooks search unbound (cross-project) and
  **do not** `upsert_project` until there is an override, git `org/repo`, or
  an org/repo mention in the prompt. `/reqall check` pings via `list_projects`
  when unbound.
- **Fix:** `pre_llm_call` full recall requires work-like language, not merely
  a long message. `pre_tool_call` searches a conceptual query (basename +
  task), not the raw filesystem path.
- **Feat:** Hermes persist gate — `pre_verify` continues once when the session
  is dirty / has `changed_paths`. `on_session_finalize` logs leftover dirty
  work (Slack threads rarely end).
- **Feat:** Skills know `info` + `work` and SLEEP `work_review` /
  `promote` / `discard`. Persist prefers durable kinds.

## 2026.8.8

- **Fix:** Hermes profiles are separate `$HERMES_HOME`s. Enabling `reqall` in
  a profile config does not load `~/.hermes/plugins/reqall`. The plugin now
  diagnoses every home, can symlink itself into enabled-but-empty profiles
  (`python3 ensure-install.py`, `/reqall ensure-install`, or automatic
  fail-open sync on `register()`), and reports gaps from `reqall_status`.
- **Fix:** Host MCP probe matches `mcp__reqall__*` case-insensitively
  (`mcp_servers.Reqall` → `mcp__Reqall__search` is no longer “missing”).
- **Fix:** Auth accepts `REQALL_API_KEY`, `MCP_REQALL_API_KEY`, and
  `REQALL_MCP_API_KEY` so hook HTTP and host MCP can share one secret.
- **Fix:** Skills remain usable when the host `skills` toolset is disabled:
  new `reqall_skill` tool; `/reqall persist|context|sleep|…` dumps the
  skill body instead of telling the agent to call `skill_view`.
- **Docs:** README / after-install / AGENTS — per-profile install, key
  aliases, MCP name case.

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
