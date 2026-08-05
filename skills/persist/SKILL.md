---
name: reqall-persist
description: Classify and persist all work completed in this session to Reqall
---

# Persist Work

> **Hermes host:** Prefer plugin tool `reqall` (`action` + `arguments`). Host MCP tools are named `mcp__reqall__*` (double underscore) when present in the session tool list; if missing, use `reqall` or `/new` after enabling MCP. Hooks inject recall via `pre_llm_call`. Use `/reqall status` or `reqall_status` to verify.

Classify the work completed in this session and save it to the Reqall
knowledgebase. Create one record per distinct work item — sessions often
produce multiple artifacts worth tracking.

## Classification Table

| Work type                          | kind    | status   |
|------------------------------------|---------|----------|
| Bug fix                            | issue   | resolved |
| New bug discovered (not yet fixed) | issue   | open     |
| Completed task                     | todo    | resolved |
| New task identified (not yet done) | todo    | open     |
| Architectural change or decision   | arch    | resolved |
| New or updated specification       | spec    | open     |
| Test scenario added                | test    | open     |
| Trivial / Q&A / unclassifiable     | --      | skip     |

## Title Conventions

Prefix titles to aid scanning:
- Issues: `BUG:`, `TASK:`, `BLOCKER:`, `QUESTION:`
- Specs: `ARCH:`, `API:`, `AUTH:`, `DATA:`, `UI:`

## Steps

1. **Identify the project** — Use the project name from the Stop hook
   message (`project_name="..."`) or earlier hook context. If none is
   available, check `REQALL_PROJECT_NAME`, then `git remote get-url origin`
   for `org/repo`, falling back to the directory basename. Call
   `reqall action=upsert_project` with that exact name to get the `project_id`.

   On Grok Build the **Stop** hook blocks once per non-trivial turn until
   this skill (or equivalent MCP upserts) has been run.

2. **Analyze the session** — Review the conversation to identify all
   distinct work items. Scan each category explicitly:
   - Files created or modified
   - Bugs fixed or discovered
   - Architectural or design decisions made
   - Specs written, changed, or discussed
   - Tests added or updated
   - Tasks identified for future work
   - Plans produced by subagents

   A session may produce multiple records, e.g. a bug fix
   (issue/resolved), a new spec (spec/open), and a follow-up task
   (todo/open).

3. **Create records** — For each non-trivial work item, call
   `reqall action=upsert_record` with:
   - `project_id` from step 1
   - `kind` and `status` from the classification table
   - A short, descriptive `title` with the appropriate prefix
   - A `body` summarizing what was done, why, and any relevant context.
     Include enough detail for semantic search to find this later.

4. **Create links** — For each meaningful relationship between records
   (new or existing), call `reqall action=upsert_link`:
   - A bug fix `implements` a spec
   - A test `tests` an architecture decision
   - A new task is `related` to or `blocks` an existing record
   - A spec is `parent` of sub-specifications

   Use `reqall action=search` to find existing records worth linking to.

5. **Summarize** — Tell the user what was persisted: records
   created/updated, links established.

6. **Verify** — Call `reqall action=list_records` with the `project_id` to
   review the records just created or updated. Cross-check against the
   work items identified in step 2. If anything was missed, create it
   now.

## When to Skip

If the session was purely Q&A, informational, or trivial (no code changes,
no decisions made), do not create any records. Say "Nothing to persist."
