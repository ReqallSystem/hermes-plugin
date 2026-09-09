---
name: reqall-intend
description: Capture agreed substantial specifications and decisions.
version: 0.1.0
author: Reqall contributors, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [reqall, memory, intent]
    related_skills: [reqall-context, reqall-persist]
---

# Capture Intent

Persist the agreed scope of substantial work before implementation when possible.
Use durable `spec` or `arch` records, not a scratchpad or speculative commitment.

## When to Use

- The user has agreed a substantial feature, behavior contract, or architectural decision.
- A design discussion reaches concrete acceptance criteria worth retaining.
- Existing agreed intent needs to be selected for the current session.
- Skip pure questions, brainstorming without agreement, routine chores, formatting,
  and trivial fixes. Do not turn an implementation request into unnecessary questions.

## Prerequisites

Use plugin tool `reqall` with `action` and `arguments`; host equivalents are
`mcp__reqall__*` / `mcp__Reqall__*`. Use `reqall_session` for local session bookkeeping.
Read `reqall_session action=status`; keep its `session_id` and project binding.
Routing is explicit override → git origin → explicit labelled `project_name` /
`project` selection → `.machine/<hostname>/<os-user>` (`REQALL_MACHINE_NAME`
overrides hostname). Never use a cwd basename or a path mentioned in prose.
Do not migrate old records or touch another profile.

## Procedure

1. **Confirm agreement from the conversation.** Capture requirements already given;
   ask only when unresolved ambiguity changes scope. Do not record guesses as agreed.
2. **Deduplicate.** Search conceptually within the selected project, then get the
   relevant `spec` / `arch` records in full. Prefer the existing agreed record;
   server deduplication alone does not prove equivalent scope.
3. **Persist only a meaningful change.** Use `upsert_project` with the exact binding
   if needed. `upsert_record` creates `kind: spec`, `status: open` for intended
   behavior, or `kind: arch`, `status: resolved` for an agreed decision. Updates use
   `id` from the fetched record; preserve unrelated details. Body contains:
   - agreed goal, constraints, and rationale;
   - observable **acceptance criteria**, not unverified completion claims;
   - explicit **non-goals**, dependencies, and unresolved questions if any.
4. **Link in the upsert.** For known relationships, include `links` entries with
   `target_id`, `target_table: records` (or `projects`), `relationship`, and explicit
   `direction: outgoing` (this record → target) or `incoming` (target → this record).
   Check every returned link result: `created` / `existing` succeeds; `error`, a
   missing result, or an unexpected count is partial failure even if the record saved.
   For an existing-pair link without a record change, or legacy servers that reject
   inline links, use `upsert_link` with explicit source/target IDs and tables. Check
   readbacks first after an ambiguous write; retry only missing relationships.
   **Partial-save recovery:** link repair alone does not clear
   `pending_write_failures`. After repaired links and exact record/link readback
   (`get_record` and `list_links`), perform a successful same-ID `upsert_record`
   with the saved `id` and verified fields; omit inline links on a legacy server.
   Do not recreate the record or omit its `id`. Verify the recovery write and
   readback, then refresh `reqall_session action=status` before selecting intent
   and persisting outcomes. A failed recovery stays pending; selection alone
   does not clear it. Use the refreshed snapshot for subsequent reconciliation.
5. **Select the verified intent.** Read back the exact record with `get_record`.
   For either an existing unchanged record or the newly saved one, call
   `reqall_session action=select_intent record_id=<id> session_id=<session_id>`.
   Check success and read `reqall_session action=status` to confirm selection.
   Selection is not evidence that implementation is complete and does not clear work.
6. Report the selected record ID and any persistence/link failure briefly.

## Pitfalls

- Never persist secrets, credentials, private transcripts, or unrelated personal data.
- `pre_llm_call` runs once per user turn, not before every tool-loop edit.
  `pre_verify` is only a file-edit finalization gate, not an all-turn Stop hook.
  There is no guaranteed pre-edit injection or pre-compaction persistence hook;
  save agreed intent incrementally rather than relying on either guarantee.
- Prefer durable records. Ephemeral `work` logs are for later SLEEP
  `work_review` → `promote` / `discard`, not the source of agreed intent.

## Verification

Finish only after the exact intent readback and session selection succeed. Keep
partial failures visible; do not recreate an existing record simply to select it.
