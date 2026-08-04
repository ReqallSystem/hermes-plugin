---
name: reqall-sleep
description: Run SLEEP maintenance on a project — consolidate, compact, split, and cross-link records to keep the knowledge graph healthy
---

# SLEEP — Knowledge Graph Maintenance

> **Hermes host:** MCP tools appear as `mcp_reqall_*` or similar once the Reqall MCP server is configured. Hooks inject recall via `pre_llm_call`. Use `/reqall status` to verify auth.

Run the SLEEP pipeline (Synthesis, Linking, Extraction, Enrichment Pipeline)
on a project to consolidate resolved records, compact isolated records, split
dense records, and discover cross-project links.

Rate-limited to once per 24 hours per project.

## Steps

1. **Identify the project** — Use the project name from the argument
   (e.g. `/sleep myorg/myrepo`). If none provided, check the
   `REQALL_PROJECT_NAME` env var, then run `git remote get-url origin`
   to extract the `org/repo` name, falling back to the directory basename
   only if the git command fails. Call `reqall:upsert_project` with that
   exact name to get the `project_id`.

2. **Fetch candidates** — Call `sleep_candidates` with the `project_id`.
   If rate-limited, inform the user of the next eligible time and stop.

3. **Report summary** — Tell the user what was found before reasoning:
   - Number of consolidation clusters and total records in them
   - Number of rollup candidates
   - Number of split candidates
   - Number of crosslink pairs
   If all stages are empty, say "Nothing to do — graph is healthy." and stop.

4. **Process consolidation clusters** — For each cluster, synthesize the
   records into a single durable knowledge record. Follow these rules:
   - Incorporate ALL information from every input record — nothing may be lost
   - Output a concise, well-structured summary (markdown)
   - Use the most specific and accurate title
   - Preserve actionable details, decisions, and outcomes
   - Set `kind: "arch"` and `status: "resolved"` for the synthesized record
   - Emit a `consolidate` operation

5. **Process rollup candidates** — For each isolated resolved record,
   decide whether to compact or skip:
   - **Compact** if the record has lasting value — transform it into durable
     knowledge suitable for long-term reference. Tighten prose, remove
     ephemeral details, keep decisions and outcomes.
   - **Skip** if the record is trivial (one-liner with no lasting value,
     ephemeral note, pure acknowledgment).
   - Emit `compact` or `skip` operations accordingly.

6. **Process split candidates** — For each dense/long active record,
   decide whether to split or keep:
   - **Split** if the record covers 2+ clearly separable topics or
     responsibilities. Create focused sub-records, each with its own
     `kind` and `status` matching the original.
   - **Keep** if the record is focused on a single topic, even if long.
   - Emit `split` operations for records that should be split.

7. **Process crosslink candidates** — For each proposed pair, decide
   whether the relationship is genuinely useful for discovery:
   - **Confirm** if the records share meaningful conceptual overlap that
     a user would benefit from discovering.
   - **Reject** if the similarity is superficial (e.g., both mention a
     common term but are about different things).
   - Emit `crosslink` operations for confirmed pairs.

8. **Apply operations** — Collect all operations from steps 4–7 and call
   `sleep_apply` with the full batch.

9. **Report results** — Summarize what was done:
   - Clusters consolidated (N clusters, M records merged)
   - Records compacted
   - Records split (originals removed, new records created)
   - Cross-links created
   - Errors (if any)

## Important

- This skill runs **autonomously** — do not ask the user for confirmation
  on each operation. The reasoning visible in the conversation is the
  accountability layer.
- If candidates were capped/truncated, note this: "Some candidates were
  capped — run `/sleep` again tomorrow for the next batch."
- All safety invariants are enforced server-side by `sleep_apply`. You
  do not need to verify ownership or check for active dependents.
