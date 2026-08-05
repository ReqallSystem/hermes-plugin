---
name: reqall-sleep
description: Compress project memory — consolidate, split, compact, skip, and crosslink records
---

# SLEEP — compress project memory

> **Hermes host:** Prefer plugin tool `reqall` (`action` + `arguments`). Host MCP tools are named `mcp__reqall__*` (double underscore) when present in the session tool list; if missing, use `reqall` or `/new` after enabling MCP. Hooks inject recall via `pre_llm_call`. Use `/reqall status` or `reqall_status` to verify.

**Goal:** Preserve **knowledge** in a **minimal number of short, non-redundant records**.  
User invoked sleep → rewrite and delete are expected. Compression is the point.  
Knowledge = decisions, outcomes, constraints, IDs, contracts — not session prose.

Ops (fixed names): `consolidate` · `split` · `compact` · `skip` · `crosslink`

Rate-limited ~once per 24h per project. **Modest progress is success** — do not boil the ocean.

## Decision table

| Signal | Action |
|--------|--------|
| Server cluster of highly similar resolved/archived | **consolidate** → one terse record; **sources deleted** |
| Isolated resolved/archived; durable but verbose/redundant | **compact** |
| Isolated resolved/archived; pure noise (ack, empty, no durable fact) | **skip** |
| Active/open; 2+ clearly separable topics | **split** (original deleted by apply) |
| Active/open; single topic, already clear | leave (no op) |
| Cross-project pair; same concept, discovery-useful | **crosslink** |
| Cross-project pair; superficial token overlap | omit |
| Candidate unclear / not obvious | **omit this pass** (not a full-run refuse) |

Prefer clear, concise records and useful links over perfect coverage. A long but appropriate record can wait for a later sleep.

## Steps

1. **Project** — arg → `REQALL_PROJECT_NAME` → git `org/repo` → dir basename → `upsert_project` → `project_id`.
2. **Candidates** — `sleep_candidates` with `project_id`. If rate-limited, report next eligible time and stop.
3. **Summary** — counts: consolidate clusters, compact/skip pool, split, crosslink. Empty → "Nothing to do — graph is healthy."
4. **Select ops** — decision table only. Prefer obvious wins; small batch is fine. Bodies: terse, non-redundant.
   - **consolidate** — `kind: "arch"`, `status: "resolved"`; best title; keep knowledge from all members; wording is disposable.
   - **compact** — same id; leaner form.
   - **split** — focused sub-records; kind/status fit each topic (usually match original).
   - **crosslink** — only when useful for discovery.
5. **Apply** — one `sleep_apply` with the batch. No per-op confirmation.
6. **Report** — consolidated / compacted / split / crosslinked / skipped / errors. If candidates were capped: note to run again later.

## Rules

- Knowledge ≠ wording. Prose is disposable; durable facts are not.
- **consolidate always deletes sources** (server). Do not keep originals.
- Do not ask whether rewrite/delete is OK — user ran sleep.
- Unclear candidate → omit; do not invent merges or splits.
- Safety (ownership, active dependents) is enforced by `sleep_apply` — do not re-check.
