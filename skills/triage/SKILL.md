---
name: reqall-triage
description: Triage requests into prioritized, linked records.
---

# Triage Incoming Issue

> **Hermes host:** Prefer plugin tool `reqall` (`action` + `arguments`). Host MCP tools are named `mcp__reqall__*` (double underscore) when present in the session tool list; if missing, use `reqall` or `/new` after enabling MCP. Hooks inject recall via `pre_llm_call`. Use `/reqall status` or `reqall_status` to verify.

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

1. **Identify the project** -- Use the authoritative session binding and Project
   routing below. `upsert_project` with the exact name gives `project_id` if needed.

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

5. **Search for duplicates** -- Call `reqall action=search` with a natural
   language summary of the issue, using the `project_name` parameter.
   Also call `reqall action=list_records` with `project_id`, `kind` matching
   the category, and `status: "open"` to scan existing open records.

   If potential duplicates are found:
   - Show them to the user with title and body summary
   - Ask: "Is this the same issue, related, or a new issue?"
   - If duplicate: update the existing record with new details via
     `reqall action=upsert_record` (pass its `id`), add only relevant new
     details, verify the readback, and stop
   - If related: proceed to create a new record and link it in step 8

6. **Determine priority** -- Assess priority using the Priority Scale
   based on these signals:
   - Severity from the user's description and answers
   - Scope of impact (one user vs many, core feature vs edge case)
   - Workaround availability
   - Category default hints from the Category Table

   Present the proposed priority to the user and let them confirm or
   override it.

7. **Create the record** -- Call `reqall action=upsert_record` with:
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

8. **Verify links included in step 7** -- If step 5 found related records,
   include inline `links` in that `upsert_record`, then verify each result:

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

## Project routing

Read `reqall_session action=status`: its bound session identity is authoritative
for recall, work, persistence, and verification. Do not recompute a different name
between steps. Preserve deliberate operation targets (including SLEEP) and `.user`.
Automatic precedence: trimmed `REQALL_PROJECT_NAME` / scoped `settings.project_name`
→ network git origin → explicit labelled `project_name` / `project` prompt or retained
session selection → nearest valid `.reqall.yml` / `.reqall.yaml` → nearest valid
package (`package.json` > `go.mod` > `Cargo.toml` per directory) → exact path relative
to `REQALL_WORKSPACE_ROOT` or nearest `.reqall-workspace` marker → reserved
`.machine/<short-lower-host>/<os-user>`. `REQALL_MACHINE_NAME` / scoped
`settings.machine_name` overrides the whole host (dots retained); use actual OS user.
Never use an unconstrained cwd basename, incidental prose path, or synthetic report
example. Git accepts HTTP(S)/SSH/git URLs or SCP, not local/file origins; retain
final two path segments, trimming trailing slashes and `.git`, without migrations.
Use only regular UTF-8 metadata files of at most 64 KiB. YAML supports simple
top-level `project` / `name` strings (project preferred, .yml before .yaml), matching
quotes and comments; reject null/boolean/numeric values, malformed quoting and
contradictory duplicates. JSON `name` must be a string; only valid npm `@scope/name`
removes one `@`. Go preserves the complete module path after comments; Cargo reads
only a simple quoted `[package]` name, never bin/dependency names. Validate ASCII
alphanumeric `._-` slash segments before normalization; reject absolute/drive/UNC,
backslash/tilde and empty/dot/dotdot segments. Metadata named `src` is valid.
Scan nearest valid ancestors, stopping at a containing workspace root inclusively.
Workspace settings default to process environment; relative roots resolve from cwd,
`~/` from home. Resolve real paths before containment; reject symlink escapes and
invalid/nonancestor configured roots without marker fallback. Root equality gives
no relative identity. Keep every relative segment. Explicit names are preserved,
not subjected to new metadata validation. Never migrate records or touch profiles.
Use `upsert_project` with the exact binding only when needed to obtain `project_id`.

## Inline links and verification

When creating or updating a record, prefer `links` in `upsert_record`. Each entry
explicitly sets `target_id`, `target_table` (`records` or `projects`), `relationship`,
and `direction`. `outgoing` is this record → target; `incoming` is target → this
record. Use `implements` for outcome → intent, `tests` for evidence → subject,
`blocks` for blocker → blocked item, and `parent` / `related` only when justified.
Use at most 20 inline links per upsert.

Check record success and every per-link result: `action: created` / `existing`
succeeds; `error`, a missing result, or a count mismatch is partial failure. The
record can be saved even when links fail. Read back the exact `get_record` (`id`)
and `list_links` targets, including endpoint tables and relationship, before success.

For an existing-pair relationship with no record change, or a legacy server that
explicitly rejects inline links, use `upsert_link` with `source_id`, `source_table`,
`target_id`, `target_table`, and `relationship`. Reverse endpoints for incoming
links. On an ambiguous response, inspect readbacks before retrying; retry only
missing links, never recreate a record that already saved. Report remaining
failures rather than treating transport success as persistence success.

## Pitfalls

Never persist secrets or unnecessary personal data. Prefer durable records; reserve
`work` for ephemeral logs handled by SLEEP `work_review` → `promote` / `discard`.
`pre_llm_call` runs once per user turn. `pre_verify` is only a file-edit finalization
gate, not an all-turn Stop hook. There is no guaranteed pre-edit injection or
pre-compaction persistence; act incrementally, and do not rely on hook timing.

## Verification

Read back the exact record and each required relationship before reporting success.
For an agreed substantial spec or architecture choice, use `reqall-intend`; an
unchanged existing intent is selected with `reqall_session action=select_intent`
using `record_id` and `session_id`, then confirmed via status. Do not manufacture
intent for a routine chore, question, or trivial fix.

## When to Skip

If the user's description is too vague to classify after one round of
follow-up questions, ask once more for clarification. If still
insufficient, create the record as `kind: issue` with `P3` priority
and a `TRIAGE:` prefix, noting in the body that further clarification
is needed.
