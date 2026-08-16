---
name: reqall-sleep
description: Compress project memory — consolidate, split, compact, skip, crosslink, promote, discard
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

1. **Project** — arg → `REQALL_PROJECT_NAME` → git `org/repo`. Do not invent
   a name from `$HOME` / `ubuntu` / `src`. `upsert_project` → `project_id`.
2. **Candidates** — `sleep_candidates` with `project_id`. If rate-limited,
   report next eligible time and stop.
3. **Summary** — counts: consolidate, compact/skip, split, crosslink,
   work_review. Empty → "Nothing to do — graph is healthy."
4. **Select ops** — decision table only. Bodies: terse, non-redundant.
5. **Apply** — one `sleep_apply` with the batch. No per-op confirmation.
6. **Report** — consolidated / compacted / split / crosslinked / skipped /
   promoted / discarded / errors.

## Rules

- Knowledge ≠ wording. Prose is disposable; durable facts are not.
- **consolidate always deletes sources**. **promote** and **discard** delete
  the work log.
- Do not ask whether rewrite/delete is OK — user ran sleep.
- Unclear candidate → omit.
- Safety is enforced by `sleep_apply` — do not re-check.
