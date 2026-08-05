# Reqall Memory Autopilot For Hermes

Reqall has two mandatory goals on non-trivial work:

1. Inject relevant context from prior records before implementation.
2. Persist completed work before ending the turn.

Do this automatically. Do not wait for the user to ask.

## Tools

Prefer the **Reqall MCP** tools once configured (`hermes` MCP server `reqall`).
Names may be prefixed by the host (for example `mcp_reqall_search`).

Core operations:

- `search` / `upsert_project` / `upsert_record` / `get_record` / `list_records`
- `upsert_link` / `list_links` / `impact`
- `sleep_candidates` / `sleep_apply`
- `delete_record` / `delete_link` (only if the user explicitly asks)

Plugin helper: `reqall_status` tool and `/reqall` slash command.

## Skills

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
