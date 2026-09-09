---
name: reqall-document
description: Document a meaningful work item with verified links.
---

# Document Work Item

## When to Use

Save a meaningful outcome or finding incrementally, without waiting until the
session ends. Skip read-only/no-op commands, routine chores, formatting-only work,
and tests with no durable findings. A failed command is not completed work; a
useful diagnosis of the failure may still merit a record.

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

1. Classify: fixed bug → `issue/resolved`; discovered bug → `issue/open`;
   completed task → `todo/resolved`; follow-up → `todo/open`; agreed decision →
   `arch/resolved`; specification → `spec/open`; test evidence → `test/resolved`;
   convention or how-to → `info/resolved`. Use a short `BUG:`, `TASK:`, `ARCH:`,
   `FEAT:`, `TEST:`, or `INFO:` title. Keep plans distinct from results.
2. Search conceptually within the project (not a raw filesystem path), read likely
   matches, and update by `id` instead of duplicating existing knowledge.
3. `reqall action=upsert_record` with the project, kind, explicit status, title,
   body, and known inline links. Body records what changed, why, actual evidence,
   acceptance coverage, and unfinished work. Link to the selected intent when valid.
4. Verify record and required links using the contract below, then report its ID
   and any partial failure in one line.
5. Documenting one item does **not** reconcile all session work. Use `reqall-persist`
   for a full status snapshot and verified `reqall_session action=acknowledge`
   with `record_ids`, `work_revision`, and `session_id`. Never clear work manually.

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

The exact record and every requested relationship must read back correctly.
A successful individual write is not proof that all session work was persisted.
