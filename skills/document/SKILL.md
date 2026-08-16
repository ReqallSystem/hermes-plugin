---
name: reqall-document
description: Document a single work item by upserting a record and any related links to Reqall
---

# Document Work Item

> **Hermes host:** Prefer plugin tool `reqall` (`action` + `arguments`). Host MCP: `mcp__reqall__*` / `mcp__Reqall__*`. `reqall_skill` name=reqall-document if `skill_view` is off.

Called after meaningful tool use to persist one item. Lighter than
`reqall-persist`.

## When to Skip

Read-only, trivial/failed commands, formatting-only, tests with no findings.

## Classification Table

| Work type                          | kind    | status   |
|------------------------------------|---------|----------|
| Bug fix                            | issue   | resolved |
| New bug discovered (not yet fixed) | issue   | open     |
| Completed task                     | todo    | resolved |
| New task identified (not yet done) | todo    | open     |
| Architectural change or decision   | arch    | resolved |
| New or updated specification       | spec    | open     |
| Test / verification evidence       | test    | resolved |
| Durable note (convention, how-to)  | info    | resolved |
| Ephemeral session / progress log   | work    | resolved |
| Trivial / no-op                    | --      | skip     |

Prefer durable kinds. `work` is ephemeral (SLEEP promote/discard).

## Title Conventions

- Issues: `BUG:`, `TASK:`, `BLOCKER:`
- Specs: `ARCH:`, `API:`, `AUTH:`, `DATA:`, `UI:`
- Features: `FEAT:`, `REFACTOR:`
- Notes: `INFO:`, `WORK:`

## Steps

1. **Identify the project** — Hook `project_name` if `safe_to_upsert`. Else
   `REQALL_PROJECT_NAME` or git `org/repo`. Never upsert `ubuntu` / `$HOME`.
   `reqall action=upsert_project` → `project_id`.

2. **Evaluate** — If trivial, output "Nothing to document." and stop.

3. **Search** — `reqall action=search` with a conceptual query (not a raw
   filesystem path). Update an existing record instead of duplicating.

4. **Upsert** — `reqall action=upsert_record` with kind/status/title/body.

5. **Link** related records when the relationship is clear.

6. **Summarize** in one line.
