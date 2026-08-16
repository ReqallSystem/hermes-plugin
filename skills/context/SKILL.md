---
name: reqall-context
description: Initialize project and gather relevant context from the Reqall knowledgebase
---

# Gather Context

> **Hermes host:** Prefer plugin tool `reqall` (`action` + `arguments`). Host MCP: `mcp__reqall__*` / `mcp__Reqall__*`. `reqall_skill` / `/reqall context` if `skill_view` is off.

Load project context from Reqall before starting work.

## Steps

1. **Identify the project** — Hook `project_name` / `project_binding` when
   `safe_to_upsert`. Else `REQALL_PROJECT_NAME`, then git `org/repo`.
   **Never** treat `$HOME`, `ubuntu`, `src`, or `workspace` as a project.
   If unbound, skip upsert and search across projects (step 3 only).

2. **Ensure the project exists** — Only if bound: `reqall action=upsert_project`
   → `project_id`.

3. **Search** — `reqall action=search` with a *conceptual* query from the user
   task (not a raw filesystem path). Pass `project_name` only when bound.

4. **List open records** — If you have a real `project_id`,
   `reqall action=list_records` with `status: "open"`.

5. **Impact** — If changing an existing tracked record, `reqall action=impact`.

6. **Present context** — Search hits, open items, impact. `get_record` for
   the few that matter.

## When to Skip Steps

- Simple question: only search (step 3).
- Unbound project: do not upsert; search only.
- Search empty: say so and proceed.
- No open records: skip step 4 output.

## Automatic Hooks

Hermes hooks already:

1. **pre_llm_call** — search (and upsert + open list only when the project is
   bound). Generic home directories stay unbound.
2. **pre_tool_call** — conceptual query from the edited file, not the raw path.
3. **pre_verify** — one persist continue when the session is dirty.

Use this skill for a deeper pass (impact, full bodies) beyond hook injection.
