---
name: reqall-persist
description: Persist verified session outcomes and reconcile work.
---

# Persist Work

Use plugin tool `reqall` (`action` + `arguments`); host equivalents are
`mcp__reqall__*` / `mcp__Reqall__*`. `reqall_skill name=reqall-persist` loads this
workflow when `skill_view` is off. Use `reqall_session` for local bookkeeping.
Native key-backed readback verification is required for acknowledgement. Host
OAuth tools may work independently, but automatic OAuth delegation is deferred
because that path can lose structured record IDs. If native verification cannot
authenticate, report the blocker and leave work pending; OAuth-only acknowledgement
is not guaranteed.

## When to Use

Persist meaningful outcomes before finishing, including substantial decisions in
chat-only turns. Do not wait for a hook. Pure Q&A, routine chores, formatting-only,
and no-op work with no durable finding can be skipped; never manufacture records
or acknowledge unrelated IDs merely to silence a reminder.

## Classification

| Work type | kind | status |
|---|---|---|
| Bug fixed / new bug found | issue | resolved / open |
| Completed task / follow-up | todo | resolved / open |
| Agreed architectural decision | arch | resolved |
| New or updated specification | spec | open |
| Verification evidence | test | resolved |
| Durable convention or how-to | info | resolved |
| Ephemeral progress log | work | resolved |

Prefer durable kinds; `work` is only for a log eligible for SLEEP `work_review`
→ `promote` / `discard`. Titles use `BUG:`, `TASK:`, `ARCH:`, `API:`, `FEAT:`,
`TEST:`, `INFO:`, or `WORK:` as appropriate. Never persist secrets.

## Procedure

1. **Snapshot before writing.** Call `reqall_session action=status`. Retain the
   exact returned `session_id` and `work_revision` for this persistence batch,
   plus work evidence and selected intents. The revision identifies the work being
   documented; do not replace it with a later revision just to pass acknowledgement.
2. **Use the selected project.** Take the safe project binding from status/context.
   Resolution is explicit override (`REQALL_PROJECT_NAME` or scoped plugin setting)
   → git origin → explicit labelled `project_name` / `project` selection → reserved
   `.machine/<hostname>/<os-user>`. `REQALL_MACHINE_NAME` overrides hostname.
   Never use a cwd basename or a slash token such as `src/auth.py` from prose.
   `reqall action=upsert_project` with the exact name returns `project_id`.
   Do not migrate historical records or touch another profile.
3. **Reconcile actual outcomes.** Account for every meaningful item in the snapshot:
   changed files, executed commands, findings, decisions, tests, subagent results,
   and follow-ups. Distinguish completed work from plans and failed attempts.
   Search conceptually and read candidate records; update an existing matching
   record (`id`) instead of duplicating. Do not resolve intent until its acceptance
   criteria are verified. Select existing intent with `reqall_session
   action=select_intent record_id=<id> session_id=<session_id>` when needed.
4. **Upsert records with inline links.** Call `reqall action=upsert_record` with
   `project_id`, `kind`, explicit `status`, `title`, `body`, and known `links`.
   Each link has `target_id`, `target_table: records` (or `projects`), `relationship`,
   and explicit `direction`. `outgoing` means this record → target; `incoming`
   means target → this record. Example: an implementation outcome `implements`
   a selected spec; verification evidence `tests` it. Do not invent relationships.
   Limit each upsert to the server's supported number of links (currently 20).
   Check top-level success **and every per-link result**. Expected link `action`
   values are `created` / `existing`; `error`, missing entries, or a count mismatch
   means partial failure. A saved record is not proof that its links saved.
5. **Repair links without duplicate records.** For an existing-pair relationship
   without a record change, or a legacy server explicitly rejecting inline links,
   use `reqall action=upsert_link` with `source_id`, `source_table`, `target_id`,
   `target_table`, and `relationship`. Map incoming direction by reversing endpoints.
   After uncertain responses, get the record and `list_links` before retrying;
   retry only missing links. Do not recreate a successfully saved record.
   **Partial-save recovery:** link repair alone does not clear
   `pending_write_failures`. After repaired links and exact record/link readback,
   a successful same-ID `upsert_record` is required: supply the saved `id` and
   preserve the verified record fields (omit inline links on a legacy server).
   Do not recreate the record or omit its `id`. Check the recovery write and its
   readback, then fetch `reqall_session action=status` for a fresh snapshot.
   Reconcile any additional work and re-upsert its outcomes before acknowledging;
   older outcome IDs cannot cover a newer work revision merely by changing the
   supplied revision. Keep failures pending if the same-ID recovery fails.
6. **Verify exact targets.** Read back each saved record using `get_record` with
   `id` and check its project, body, kind, and status. Read back required links via
   `list_links` and check source, target, tables, and relationship. Retain verified
   record IDs for this batch. If any record or required link failed, report partial
   persistence and leave work pending; do not acknowledge the batch.
7. **Acknowledge the snapshot.** Only once all snapshot work is represented and
   readbacks succeed, call `reqall_session action=acknowledge
   record_ids=[<verified IDs>] work_revision=<snapshot revision>
   session_id=<snapshot session ID>`. This tool performs its own record readbacks
   before clearing work. Check its result, then read `reqall_session action=status`
   for the same session to verify the effect. A stale revision, readback failure,
   wrong project/session, or new pending work is not success: retain pending work,
   fetch a new snapshot, and document the additional work before retrying. Never
   clear dirty state manually or use a later revision with an old record batch.
8. **Report briefly.** Give verified record IDs, useful links, and any remaining
   persistence failures. Do not claim all work persisted when only a subset did.

## Pitfalls

`pre_llm_call` runs once per user turn. `pre_verify` is only a file-edit finalization
gate, not an all-turn Stop hook. It may allow a bounded continuation for persistence,
but does not replace this workflow. No guaranteed pre-edit injection or pre-compaction
persistence exists; save intent and outcomes incrementally. Hooks fail open.

## Verification

Success means exact record/link readbacks and a successful acknowledgement of the
captured session/revision, followed by status confirming no remaining snapshot work.
