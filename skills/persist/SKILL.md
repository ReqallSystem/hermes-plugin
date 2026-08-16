---
name: reqall-persist
description: Classify and persist all work completed in this session to Reqall
---

# Persist Work

> **Hermes host:** Prefer plugin tool `reqall` (`action` + `arguments`). Host MCP tools are `mcp__reqall__*` or `mcp__Reqall__*`. If `skill_view` is off, this file is also dumped by `reqall_skill` / `/reqall persist`. Hooks: `pre_llm_call` recall, `pre_verify` persist gate.

Classify the work completed in this session and save it to the Reqall
knowledgebase. Create one record per distinct work item.

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
| Trivial / Q&A / unclassifiable     | --      | skip     |

Prefer **durable** kinds. Use `work` only for a session log you expect SLEEP
to `promote` or `discard` later. Do not persist secrets.

## Title Conventions

- Issues: `BUG:`, `TASK:`, `BLOCKER:`, `QUESTION:`
- Specs/architecture: `ARCH:`, `API:`, `AUTH:`, `DATA:`, `UI:`
- Features: `FEAT:`, `REFACTOR:`
- Notes: `INFO:`, `WORK:`

## Steps

1. **Identify the project** — Use hook `project_name` / `project_binding` when
   `safe_to_upsert` is true. Else `REQALL_PROJECT_NAME`, then git `org/repo`.
   **Never** upsert from a generic cwd (`ubuntu`, `$HOME`, `src`, `workspace`).
   If unbound, search first; only `upsert_project` after you have a real name
   (org/repo or an existing project). Call `reqall action=upsert_project` with
   that exact name to get `project_id`.

   Hermes `pre_verify` may keep the turn open once when the session is dirty.
   That is the persist gate (not a Grok Stop hook).

2. **Analyze the session** — Files changed, bugs, decisions, specs, tests,
   follow-ups, subagent plans. One session can yield several records.

3. **Create records** — `reqall action=upsert_record` with `project_id`,
   `kind`, `status`, prefixed `title`, and a body that will retrieve later.

4. **Create links** — `reqall action=upsert_link` when the relationship is
   clear (`implements`, `tests`, `related`, `blocks`, `parent`).

5. **Summarize** — Tell the user what was persisted.

6. **Verify** — `reqall action=list_records` for the `project_id`. Then
   `/reqall clear-dirty`.

## When to Skip

Pure Q&A, formatting-only, or no decisions: say "Nothing to persist."
