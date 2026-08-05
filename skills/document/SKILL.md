---
name: reqall-document
description: Document a single work item by upserting a record and any related links to Reqall
---

# Document Work Item

> **Hermes host:** Prefer plugin tool `reqall` (`action` + `arguments`). Host MCP tools are named `mcp__reqall__*` (double underscore) when present in the session tool list; if missing, use `reqall` or `/new` after enabling MCP. Hooks inject recall via `pre_llm_call`. Use `/reqall status` or `reqall_status` to verify.

Called after meaningful tool use (PostToolUse hook nudge, or a background
sub-agent) to incrementally persist work as it happens. This is lighter-weight
than the full `reqall:persist` skill — it documents a single tool action
rather than an entire session.

## When to Skip

Do **not** create a record if the tool use was:
- A read-only operation (reading files, searching, listing)
- A trivial or failed command (e.g. `ls`, `pwd`, a no-op edit)
- A test run that produced no new findings
- A formatting-only change with no semantic impact

Only document **meaningful** work: file creation, substantive edits,
build/deploy commands, database migrations, configuration changes, etc.

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
| Trivial / no-op                    | --      | skip     |

## Title Conventions

Prefix titles to aid scanning:
- Issues: `BUG:`, `TASK:`, `BLOCKER:`
- Specs: `ARCH:`, `API:`, `AUTH:`, `DATA:`, `UI:`
- Features: `FEAT:`, `REFACTOR:`

## Steps

1. **Identify the project** — Use the `project_name` provided in the
   sub-agent prompt. Call `reqall action=upsert_project` with that name to get
   the `project_id`.

2. **Evaluate the work** — Look at the tool name and summary provided.
   Decide whether this is worth documenting. If trivial, output
   "Nothing to document." and stop.

3. **Search for existing records** — Call `reqall action=search` with a short
   description of the work to find records that may already track this
   item. If an existing record covers this work, update it via
   `reqall action=upsert_record` (pass its `record_id`) rather than creating
   a duplicate.

4. **Upsert the record** — Call `reqall action=upsert_record` with:
   - `project_id` from step 1
   - `kind` and `status` from the classification table
   - A short, descriptive `title` with the appropriate prefix
   - A `body` summarizing what was done and why. Include file paths,
     command output, or other details useful for future semantic search.

5. **Upsert links** — If the search in step 3 found related records,
   call `reqall action=upsert_link` to connect them:
   - A bug fix `implements` a spec
   - A test `tests` an architecture decision
   - A new task is `related` to or `blocks` an existing record
   - A spec is `parent` of sub-specifications

6. **Summarize** — Output a one-line summary of what was documented
   (or "Nothing to document." if skipped).
