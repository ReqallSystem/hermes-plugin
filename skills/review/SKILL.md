---
name: reqall-review
description: Review open records and verify agreed updates.
---

# Review Open Records

## When to Use

The user wants to review, prioritize, or update open project records interactively.
Do not turn a general question into unsolicited record mutations.

## Project and tools

Prefer plugin `reqall` (`action` + `arguments`); host tools are `mcp__reqall__*`
/ `mcp__Reqall__*`. `reqall_skill` loads this skill when `skill_view` is off.
Read `reqall_session action=status` for the session and safe project binding.
Resolution: explicit override (`REQALL_PROJECT_NAME` or scoped plugin setting)
→ git origin → explicit labelled `project_name` / `project` selection → reserved
`.machine/<hostname>/<os-user>`. `REQALL_MACHINE_NAME` overrides hostname.
Never use a cwd basename or a slash token from prose. Use the exact binding for
`upsert_project` to get `project_id`; never migrate records or touch another profile.

## Procedure

1. Fetch `list_records` with `project_id`, `status: open`, and any requested `kind`
   filter. Follow pagination, deduplicate IDs, and verify counts before claiming
   to have reviewed every record.
2. Show each record's kind, title, and status; fetch its full body using
   `get_record` when needed. Ask whether it remains relevant, whether status
   should change, what details need updating, and which relationships are valid.
3. Apply agreed updates with `upsert_record` using `id` and only changed fields.
   Include inline links with the update, using the contract below. For unchanged
   records use the existing-pair fallback rather than a needless record rewrite.
   `reqall action=delete_record` is permitted only when explicitly requested.
4. If the user selects an existing agreed `spec` / `arch` as current work, call
   `reqall_session action=select_intent record_id=<id> session_id=<session_id>`
   and confirm selection via status. A status change alone is not implementation
   evidence; do not mark acceptance complete without verification.
5. Read back each changed record and link. Report verified updated, resolved,
   archived, and linked IDs separately from failed operations.

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

Every claimed update must match the exact record/link readback. Leave ambiguous
items unchanged and report partial failures instead of silently dropping them.
