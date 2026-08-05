# Reqall Memory Autopilot For Hermes

Reqall has two mandatory goals on non-trivial work:

1. Inject relevant context from prior records before implementation.
2. Persist completed work before ending the turn.

Do this automatically. Do not wait for the user to ask.

## Tools

### Preferred (always available when plugin is enabled)

Plugin tools (no host MCP injection required):

| Tool | Purpose |
|------|---------|
| `reqall` | Call Reqall API: `action` = MCP tool name, `arguments` = object |
| `reqall_status` | Auth, project, dirty flag, host MCP probe |

Example:

```text
reqall action=upsert_record arguments={project_id, kind, title, body, status}
reqall action=search arguments={query, project_name?, limit?}
reqall action=upsert_link arguments={source_id, source_table, target_id, target_table, relationship}
```

### Host MCP (when configured and visible in this session)

Configure `mcp_servers.reqall` in Hermes config. Hermes names tools:

```text
mcp__reqall__search
mcp__reqall__upsert_project
mcp__reqall__upsert_record
mcp__reqall__get_record
mcp__reqall__list_records
mcp__reqall__upsert_link
mcp__reqall__list_links
mcp__reqall__impact
mcp__reqall__sleep_candidates
mcp__reqall__sleep_apply
```

**Not** `mcp_reqall_*` (single underscore). If MCP was enabled after this chat started, tools may be missing until **`/new`** (prompt-cache tool freeze). Prefer plugin `reqall` when unsure.

Core operations: search, upsert_project, upsert_record, get_record, list_records, upsert_link, list_links, impact, sleep_candidates, sleep_apply. Deletes only if the user explicitly asks.

Slash: `/reqall status|check|context|persist|sleep|clear-dirty`

## Skills

Load via `skill_view` as `reqall:reqall-context` (plugin-qualified) when needed:

- `reqall-context` — initialize project and gather context
- `reqall-document` — capture one meaningful work item
- `reqall-persist` — persist all meaningful session outcomes
- `reqall-triage` — classify incoming issues
- `reqall-review` — review open records
- `reqall-sleep` — compress memory (consolidate / split / compact / skip / crosslink)

## Hermes hooks (automatic)

| Hook | Behavior |
|------|----------|
| `on_session_start` | Resolve `project_name` |
| `pre_llm_call` | Non-trivial turns: upsert project + search + open records → inject context; dirty sessions get a persist nudge |
| `pre_tool_call` | Path/command-focused search before file/shell mutations (stashed for next turn context) |
| `post_tool_call` | Mark session dirty; throttled document nudge |
| `on_session_end` | Log if dirty work remains |

All hooks are **fail-open**.

## Trigger policy

Full flow for: code edits, bug fixes, refactors, migrations, architecture/specs, tests/builds.

Skip or minimize for: greetings, simple Q&A, formatting-only, one-line asks.

## Classification defaults

- Bug fixed → `kind: issue`, `status: resolved`
- New unfixed bug → `kind: issue`, `status: open`
- Completed implementation → `kind: todo`, `status: resolved`
- Follow-up → `kind: todo`, `status: open`
- Architecture decision → `kind: arch`, `status: resolved`
- Spec → `kind: spec`, `status: open`
- Test evidence → `kind: test`

Never rely on the user to remind you to persist.
