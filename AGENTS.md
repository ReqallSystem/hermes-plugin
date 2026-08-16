# Reqall Memory Autopilot For Hermes

Reqall has two mandatory goals on non-trivial work:

1. Inject relevant context from prior records before implementation.
2. Persist completed work before ending the turn.

Do this automatically. Do not wait for the user to ask.

## Tools

### Preferred (always available when plugin is enabled)

| Tool | Purpose |
|------|---------|
| `reqall` | Call Reqall API: `action` = MCP tool name, `arguments` = object |
| `reqall_status` | Auth, project binding, dirty flag, MCP probe, profile-install gaps |
| `reqall_skill` | Dump a bundled skill when host `skill_view` is unavailable |

```text
reqall action=upsert_record arguments={project_id, kind, title, body, status}
reqall action=search arguments={query, project_name?, limit?}
reqall_skill name=reqall-persist
```

Deletes, `share_project`, `revoke_share`, and `delete_project` only if the user explicitly asked.

### Host MCP

`mcp_servers.reqall` or `mcp_servers.Reqall` → `mcp__reqall__*` / `mcp__Reqall__*` (same ops, any case). If MCP was enabled mid-chat, tools may be missing until `/new`. Prefer plugin `reqall` when unsure.

Auth: `REQALL_API_KEY` or `MCP_REQALL_API_KEY`.

Slash: `/reqall status|check|context|persist|sleep|prompt|ensure-install|clear-dirty`

If `reqall` / `reqall_status` are missing, this `$HERMES_HOME` does not have plugin files. Run `python3 ensure-install.py`, restart that profile’s gateway from an **external** shell, `/new`.

## Project binding

Never `upsert_project` from `$HOME`, `ubuntu`, `src`, or `workspace`.

Order: `REQALL_PROJECT_NAME` / `plugins.entries.reqall.settings.project_name` → git `org/repo` → `org/repo` mention in the prompt → **unbound** (cross-project search only).

## Skills

`skill_view` as `reqall:reqall-persist` when the skills toolset is on. Otherwise `reqall_skill` or `/reqall persist`:

- `reqall-context` — gather context
- `reqall-document` — one work item
- `reqall-persist` — session outcomes
- `reqall-triage` / `reqall-review`
- `reqall-sleep` — consolidate / split / compact / skip / crosslink / **promote** / **discard**

`/reqall prompt [name]` loads the **server** persist/how-to prompts when you need the live table.

## Hooks

| Hook | Behavior |
|------|----------|
| `on_session_start` | Bind project (unbound if cwd is generic) |
| `pre_llm_call` | Work-like prompts: search; upsert + open list only when bound |
| `pre_tool_call` | Conceptual query before mutations (not the raw path) |
| `post_tool_call` | Mark dirty; throttled document nudge |
| `pre_verify` | Continue **once** when dirty / `changed_paths` so persist can run |
| `on_session_end` / `on_session_finalize` | Log leftover dirty work |

All hooks **fail-open**.

## Classification

- Bug fixed → `issue` / resolved; new bug → `issue` / open
- Done work → `todo` / resolved; follow-up → `todo` / open
- Decision → `arch` / resolved; spec → `spec` / open
- Verification → `test`
- Durable note → `info`; ephemeral session log → `work` (SLEEP promote/discard)

Prefer durable kinds. Never persist secrets.

Never rely on the user to remind you to persist.
