---
name: reqall-review
description: Interactive review and triage of open records for the current project
---

# Review Open Records

> **Hermes host:** Prefer plugin tool `reqall` (`action` + `arguments`). Host MCP tools are named `mcp__reqall__*` (double underscore) when present in the session tool list; if missing, use `reqall` or `/new` after enabling MCP. Hooks inject recall via `pre_llm_call`. Use `/reqall status` or `reqall_status` to verify.

Walk through open records for the current project and triage them
interactively with the user.

## Steps

1. **Identify the project** — Determine the project name and call
   `reqall action=upsert_project` to get the `project_id`.

2. **Fetch open records** — Call `reqall action=list_records` with `project_id`
   and `status: "open"`. If the user specified a kind filter (e.g.
   "review my issues"), add `kind` accordingly. Otherwise fetch all kinds.

3. **Present each record** — For each open record, show its kind, title,
   and status. Call `reqall action=get_record` for the full body if needed.
   Ask the user:
   - Is this still relevant?
   - Should the status change? (resolve, archive)
   - Does it need more detail or updates?
   - Are there related records to link?

4. **Apply updates** — Based on user responses:
   - `reqall action=upsert_record` to update status, title, or body
   - `reqall action=upsert_link` to create new relationships
   - `reqall:delete_record` only if explicitly requested

5. **Summarize** — Report what changed: records updated, resolved,
   archived, and links created.
