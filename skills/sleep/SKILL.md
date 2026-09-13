---
name: reqall-sleep
description: Consolidate memory and promote or discard work logs.
---

# SLEEP — compress project memory

> **Hermes host:** Prefer plugin tool `reqall` (`action` + `arguments`). Host MCP: `mcp__reqall__*` / `mcp__Reqall__*`. `reqall_skill` / `/reqall sleep` if `skill_view` is off.

**Goal:** Preserve **knowledge** in a **minimal number of short, non-redundant records**.
User invoked sleep → rewrite and delete are expected. Compression is the point.
Knowledge = decisions, outcomes, constraints, IDs, contracts — not session prose.

Ops: `consolidate` · `split` · `compact` · `skip` · `crosslink` · `promote` · `discard`

Rate-limited ~once per 24h per project. **Modest progress is success**.

## Decision table

| Signal | Action |
|--------|--------|
| Server cluster of highly similar resolved/archived | **consolidate** → one terse durable record; **sources deleted** |
| Isolated resolved/archived; durable but verbose | **compact** |
| Isolated resolved/archived; pure noise | **skip** |
| Active/open; 2+ clearly separable topics | **split** (original deleted by apply) |
| Active/open; single topic, already clear | leave (no op) |
| Cross-project pair; same concept, discovery-useful | **crosslink** |
| Cross-project pair; superficial token overlap | omit |
| `work_review`: durable knowledge in a work log | **promote** → durable kind(s), then work log deleted |
| `work_review`: no durable knowledge | **discard** (deletes the work log) |
| Candidate unclear / not obvious | **omit this pass** |

`promote` / `discard` apply only to `kind: work`. Never emit `work` from
consolidate/split. Prefer `info` / `arch` / `todo` / `issue` when promoting.

## Steps

1. **Project** — preserve the explicit requested SLEEP target; otherwise use the
   authoritative session binding. Follow Project routing below; never silently
   replace an explicit target with cwd discovery.
2. **Candidates** — `sleep_candidates` with `project_id`. If rate-limited,
   report next eligible time and stop.
3. **Summary** — counts: consolidate, compact/skip, split, crosslink,
   work_review. Empty → "Nothing to do — graph is healthy."
4. **Select ops** — decision table only. Bodies: terse, non-redundant.
5. **Apply** — one `sleep_apply` with the batch. No per-op confirmation.
6. **Verify** — inspect every apply result for partial failures. Read back exact
   surviving/new records and required links; verify deleted source IDs are absent.
   Do not retry the whole destructive batch after an ambiguous response.
7. **Report** — consolidated / compacted / split / crosslinked / skipped /
   promoted / discarded / errors.

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

## Rules

- Knowledge ≠ wording. Prose is disposable; durable facts are not.
- **consolidate always deletes sources**. **promote** and **discard** delete
  the work log.
- Do not ask whether rewrite/delete is OK — user ran sleep.
- Unclear candidate → omit.
- Server validation does not replace result/readback verification.
- Never persist secrets. Prefer durable records, not raw transcripts.
