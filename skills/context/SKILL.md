---
name: reqall-context
description: Initialize project and gather relevant context from the Reqall knowledgebase
---

# Gather Context

> **Hermes host:** Prefer plugin tool `reqall` (`action` + `arguments`). Host MCP tools are named `mcp__reqall__*` (double underscore) when present in the session tool list; if missing, use `reqall` or `/new` after enabling MCP. Hooks inject recall via `pre_llm_call`. Use `/reqall status` or `reqall_status` to verify.

Load project context from Reqall before starting work.

## Steps

1. **Identify the project** — Use the project name provided by the hook
   output (look for `project_name=...` in the hook message). If no hook
   output is available, check the `REQALL_PROJECT_NAME` env var, then run
   `git remote get-url origin` to extract the `org/repo` name, falling
   back to the directory basename only if the git command fails.

2. **Ensure the project exists** — Call `reqall action=upsert_project` with the
   project name. Note the returned `project_id`.

3. **Search for relevant context** — Call `reqall action=search` with a natural
   language query derived from the user's prompt or task description. Use
   the project name as the `project_name` parameter to prioritize results
   from the current project.

4. **List open records** — Call `reqall action=list_records` with the `project_id`
   and `status: "open"` to surface active issues, specs, and todos.

5. **Check impact (if relevant)** — If the task involves changing an
   existing record or component, call `reqall action=impact` with the relevant
   entity to show downstream records that may be affected. Skip this step
   for new work or simple questions.

6. **Present context** — Summarize findings concisely:
   - Relevant records from search
   - Open items for this project
   - Impact analysis results (if run)

   Call `reqall action=get_record` for full details on any records that look
   particularly relevant.

## When to Skip Steps

- Simple question or chat (no coding task): only run step 3 (search).
- Search returns nothing: say so and proceed — the project may be new.
- No open records: skip step 4 output.

## Automatic Hooks

On Grok Build, lifecycle hooks already:

1. **UserPromptSubmit** — call `upsert_project` + semantic `search` + open
   `list_records` and inject results as additional context.
2. **PreToolUse** — path/command-focused search before file edits and
   mutating shell commands.

Use this skill when you need a deeper manual pass (impact analysis, full
record bodies) beyond what the hooks injected.
