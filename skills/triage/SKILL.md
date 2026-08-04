---
name: reqall-triage
description: Classify incoming issues, gather structured details, and create prioritized Reqall records
---

# Triage Incoming Issue

> **Hermes host:** MCP tools appear as `mcp_reqall_*` or similar once the Reqall MCP server is configured. Hooks inject recall via `pre_llm_call`. Use `/reqall status` to verify auth.

Interactively classify a new issue or request from the user, gather
structured details, check for duplicates, and create a well-formed
Reqall record with priority.

## Category Table

| Category             | kind  | prefix    | priority hint         |
|----------------------|-------|-----------|-----------------------|
| Bug report           | issue | BUG:      | P0-P2 based on impact |
| Feature request      | spec  | FEAT:     | P2-P4 typically       |
| Account / billing    | issue | ACCOUNT:  | P1-P2 typically       |
| How-to / docs gap    | todo  | DOCS:     | P3-P4 typically       |
| Integration question | issue | INTEG:    | P2-P3 typically       |

## Priority Scale

| Level | Meaning                                                    |
|-------|------------------------------------------------------------|
| P0    | Critical -- system down, data loss, security, no workaround  |
| P1    | High -- major functionality broken, painful workaround       |
| P2    | Medium -- degraded feature, reasonable workaround            |
| P3    | Low -- minor issue, cosmetic, nice-to-have                   |
| P4    | Wishlist -- enhancement idea, future consideration           |

## Steps

1. **Identify the project** -- Use the project name provided by the hook
   output (look for `project_name=...` in the hook message). If no hook
   output is available, check the `REQALL_PROJECT_NAME` env var, then run
   `git remote get-url origin` to extract the `org/repo` name, falling
   back to the directory basename only if the git command fails. Call
   `reqall:upsert_project` with that exact name to get the `project_id`.

2. **Get the initial description** -- Ask the user to describe their issue
   or request in their own words. If they already provided a description
   in the same message that invoked this skill, use that directly.

3. **Classify the category** -- Based on the description, determine the
   category from the Category Table. Tell the user the classification
   and ask them to confirm or correct it.

4. **Gather structured details** -- Based on the confirmed category, ask
   targeted follow-up questions. Ask only what is missing from the
   initial description -- skip questions already answered.

   **Bug report:**
   - Steps to reproduce (numbered)
   - Expected behavior vs actual behavior
   - Environment (OS, browser, runtime version, relevant config)
   - Frequency (always, intermittent, one-time)
   - Error messages or log output
   - Severity self-assessment (blocking work? workaround available?)

   **Feature request:**
   - Use case / user story ("As a ___, I want ___ so that ___")
   - Who benefits and how many users affected
   - Current workaround (if any)
   - Desired behavior in detail
   - Acceptance criteria (how to know it is done)

   **Account / billing:**
   - Account identifier or context
   - Plan or tier
   - Specific charge, feature, or access issue
   - Urgency (blocking work? time-sensitive?)

   **How-to / docs gap:**
   - What they are trying to accomplish
   - What they have tried so far
   - Which documentation they consulted
   - Where the gap or confusion is

   **Integration question:**
   - Which integration, API, or service
   - Version numbers (SDK, API, runtime)
   - Error messages or unexpected responses
   - Code snippet or configuration (if relevant)

5. **Search for duplicates** -- Call `reqall:search` with a natural
   language summary of the issue, using the `project_name` parameter.
   Also call `reqall:list_records` with `project_id`, `kind` matching
   the category, and `status: "open"` to scan existing open records.

   If potential duplicates are found:
   - Show them to the user with title and body summary
   - Ask: "Is this the same issue, related, or a new issue?"
   - If duplicate: update the existing record with new details via
     `reqall:upsert_record` (pass its `record_id`), add a note about
     the additional report, and stop
   - If related: proceed to create a new record and link it in step 8

6. **Determine priority** -- Assess priority using the Priority Scale
   based on these signals:
   - Severity from the user's description and answers
   - Scope of impact (one user vs many, core feature vs edge case)
   - Workaround availability
   - Category default hints from the Category Table

   Present the proposed priority to the user and let them confirm or
   override it.

7. **Create the record** -- Call `reqall:upsert_record` with:
   - `project_id` from step 1
   - `kind` from the Category Table
   - `status`: `open`
   - `title`: `{PREFIX} {PRIORITY}: {concise title}`
     Example: `BUG: P1: Login fails silently on Safari 18`
   - `body`: a structured summary including:
     - **Category:** the classification
     - **Priority:** level and justification
     - **Description:** the user's original description
     - **Details:** all gathered structured details
     - **Reporter context:** any relevant user/session context

8. **Create links** -- If step 5 found related (non-duplicate) records,
   call `reqall:upsert_link` for each:
   - Bug that may be caused by an arch decision: `related`
   - Feature request that extends an existing spec: `related`
   - Bug that blocks a todo: `blocks`
   - Duplicate or near-duplicate: `related` with a note

9. **Summarize** -- Report to the user:
   - Record created (title, kind, priority)
   - Any links established
   - Any duplicates noted
   - Suggested next steps (e.g., "This P1 bug should be investigated
     soon" or "This P4 feature request has been queued")

## When to Skip

If the user's description is too vague to classify after one round of
follow-up questions, ask once more for clarification. If still
insufficient, create the record as `kind: issue` with `P3` priority
and a `TRIAGE:` prefix, noting in the body that further clarification
is needed.
