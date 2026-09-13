---
name: reqall-context
description: Recall project knowledge before substantial work.
---

# Gather Context

## When to Use

Recall relevant decisions, constraints, and open items before substantial work.
For a simple question, search only; do not create records just to provide context.

## Project and tools

Prefer plugin `reqall` (`action` + `arguments`); host tools are `mcp__reqall__*`
/ `mcp__Reqall__*`. `reqall_skill` loads this skill when `skill_view` is off.
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

## Procedure

1. Search with a conceptual query from the task, scoped to `project_name`. If
   results are weak, broaden the concept or search across projects without
   changing the selected write project. Say when recall returns no relevant hits.
2. For substantial project work, ensure the selected project exists and list open
   records with `project_id` and `status: open`. Follow pagination if reporting
   all results; do not claim totals from one partial page.
3. Fetch the few relevant records with `get_record`; use `impact` and `list_links`
   for affected dependencies. Distinguish direct evidence from inferred relevance.
4. If an existing agreed `spec` / `arch` is the current intent, select it using
   `reqall_session action=select_intent record_id=<id> session_id=<session_id>`
   and verify via status; do not create a duplicate merely to mark it selected.
   Use `reqall-intend` only when substantial agreed intent needs to be saved.
5. Present a concise context summary with record IDs and actionable constraints.
   Recall is normally read-only apart from ensuring the project exists. If a
   meaningful record correction or supported relationship should be persisted,
   use the inline-link contract below; do not mutate records just because they
   appeared in search results.

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

## Subscribed updates

The turn-start hook subscribes the bound project and injects `## Reqall updates since
last turn` when other sessions, teammates, or SLEEP changed records. Read the cited
records with `get_record` before relying on them. For long tasks, drain more with
`reqall action=poll_subscriptions`; `list_subscriptions` shows pending counts.

## Pitfalls

Never persist secrets or unnecessary personal data. Prefer durable records; reserve
`work` for ephemeral logs handled by SLEEP `work_review` → `promote` / `discard`.
`pre_llm_call` runs once per user turn. `pre_verify` is only a file-edit finalization
gate, not an all-turn Stop hook. There is no guaranteed pre-edit injection or
pre-compaction persistence; act incrementally, and do not rely on hook timing.

## Verification

Check that cited IDs and full bodies support the summary and selected intent.
Explicitly call recall tools when context is needed before an edit: a queued
`pre_tool_call` note is not guaranteed to reach the model before that edit.
