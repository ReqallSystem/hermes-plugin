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

1. **Project** — use the explicit requested SLEEP target, otherwise read the
   binding from `reqall_session action=status`: explicit override → git origin
   → explicit labelled project selection → `.machine/<hostname>/<os-user>`.
   `REQALL_MACHINE_NAME` overrides hostname. Never use a cwd basename or a prose
   path. `upsert_project` with the exact name → `project_id`. Do not migrate
   historical records or touch another profile.
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

## Rules

- Knowledge ≠ wording. Prose is disposable; durable facts are not.
- **consolidate always deletes sources**. **promote** and **discard** delete
  the work log.
- Do not ask whether rewrite/delete is OK — user ran sleep.
- Unclear candidate → omit.
- Server validation does not replace result/readback verification.
- Never persist secrets. Prefer durable records, not raw transcripts.
