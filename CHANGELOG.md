# Changelog

## 2026.9.10

- **Feat:** Project subscriptions (reqall_net #110). Once a session's project is bound,
  `pre_llm_call` subscribes it once (`subscriber` = session id) and polls
  `poll_subscriptions` at every turn start, injecting "Reqall updates since last
  turn" for changes made by other sessions, teammates, or SLEEP. The session's own
  writes are filtered out; session end releases the cursor.
- **Feat:** `reqall` actions `subscribe_project`, `unsubscribe_project`,
  `list_subscriptions`, `poll_subscriptions`; `reqall_status` reports the session
  subscription.
- Older servers without the subscription tools are detected once per session and
  left alone; transient failures fail open and retry next turn.
- **Fix:** turn-start recall now reads the project id from the server's actual
  `upsert_project` shape (`data.project.id`), so the session binds its project on the
  first non-trivial turn instead of waiting for an explicit `upsert_project` call.

## 2026.9.9

- Resolve explicit `HERMES_HOME` file settings and cached settings from the same profile, never the active profile's cache.
- Require all current-revision outcomes in acknowledgement; reject subset batches without forgetting unverified records, while allowing newer outcomes to supersede older records.
- Allow standalone resolved architecture decisions as verified design-only outcomes. Selected/written commitments cannot self-acknowledge through status changes; pending intent still requires verified coverage links.
- Track executed, potentially mutating terminal and Python calls even after nonzero exits or partial failures; keep blocked/unexecuted calls and failed atomic file edits clean.
- Add offline regressions, clarify commitment versus design-outcome persistence, and label legacy interval settings as compatibility-only.

## 2026.9.7

- Use canonical Hermes MCP discovery imports; remove the compatibility-expiring alias.
- Stop cross-profile installation during registration. Authentication checks are read-only.
- Resolve profile-local state, settings caches, and host-scoped secrets; lock state transactions across threads/processes.
- Normalize structured MCP results and preserve partial inline-link failures without declaring persistence complete.
- Track actual host `args`, successful mutations, and typed Reqall results. Remove ineffective deferred pre-edit recall.
- Add explicit `reqall_session` intent selection and readback-verified acknowledgement, with work/ledger revision guards and project-isolated pending state.
- Add reserved machine-project routing, `reqall-intend`, and inline-link workflows; preserve SLEEP work review/promote/discard.
- Disable the unverified dirty-state clearing shortcut. Document actual turn-start/file-edit-gate limits and deferred OAuth support.
- Add offline regression tests and smoke checks using real Hermes hook/secret-scope helpers. Replace POSIX-only locking with standard-library SQLite while retaining atomic JSON state.

- Bind outcomes to their work revision; reject old records as acknowledgement of newer work.
- Support same-ID partial-save recovery, explicit existing spec/architecture selection, and verified project initialization recovery.
- Align AGENTS.md with verified persistence, reserved machine routing, and actual Hermes hook timing.

## 2026.8.10

- **Fix:** Streamable-HTTP SSE client reads every `data:` frame and selects
  the JSON-RPC result matching the request id (no longer the first event).
- **Feat:** Behavioral knobs via Hermes `plugins.entries.reqall.settings`
  (`project_name`, `doc_interval_min`, `persist_interval_min`,
  `skip_profile_sync`). Env vars still override.
- **Feat:** Plugin `reqall` actions include `share_project`, `revoke_share`,
  `delete_project`, `list_prompts`, `get_prompt`. `/reqall prompt [name]`
  loads server prompts. Deletes/share still require an explicit user ask.

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
