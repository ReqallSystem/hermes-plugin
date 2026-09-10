# Reqall Memory Workflow for Hermes

For non-trivial work: recall relevant context, record substantial agreed intent,
perform the work, then persist and verify outcomes. Respect an explicit read-only
or no-service-writes request; report deferred persistence rather than violating it.
Skip trivial questions and formatting-only work. Never persist credentials.

## Tools and skills

- `reqall`: operation in `action`, MCP payload in `arguments`.
- `reqall_status`: profile/auth/project diagnostics; provide the actual session ID.
- `reqall_session`: `status`, `select_intent`, and verified `acknowledge`.
- `reqall_skill`: load bundled guidance when host skill loading is unavailable.
- Skills: `reqall-context`, `reqall-intend`, `reqall-document`, `reqall-persist`,
  `reqall-triage`, `reqall-review`, and `reqall-sleep`.

Host tools may be named `mcp__reqall__*` or `mcp__Reqall__*`. Prefer native `reqall`
for typed verification: host MCP rendering can discard structured record identity.
OAuth-only automatic verification is not implemented. Do not copy host token files.
Use active-profile secrets; never borrow another profile's credentials or settings.
Deletes and sharing/revocation require the user's explicit request.

## Project routing

Use `REQALL_PROJECT_NAME` / scoped `settings.project_name`, then actual git origin,
then an explicitly labelled selection such as `project_name=org/repo`. Otherwise
use the reserved `.machine/<short-host>/<os-user>` binding. `REQALL_MACHINE_NAME`
or scoped `settings.machine_name` provides stable machine identity. Never infer a
project from directory basenames, arbitrary prose, URLs, or paths like `src/auth.py`.
Route account-wide preferences deliberately to `.user`. Do not migrate old records.
If automatic initialization failed, an explicit successful `upsert_project` for the
exact binding can initialize its missing session project ID; check session status.
Plugin loading and status checks must not install into sibling profiles. Request
explicit user direction before any cross-profile installation or gateway restart.

## Agreed intent

Use `reqall-intend` for substantial agreed scope, acceptance criteria, and non-goals.
Search and deduplicate before creating a `spec` or `arch`. Do not turn questions,
chores, or speculative ideas into commitments. Background reads alone are not intent.
Select an existing same-project commitment explicitly using `reqall_session
 action=select_intent record_id=... session_id=...` and check its result.

## Persistence and reconciliation

1. Load `reqall-persist`. Before outcome writes, capture `reqall_session action=status`
   with the actual `session_id`, `work_revision`, and pending intent/work snapshot.
2. Save durable outcomes using `upsert_record`. Prefer inline `links` with explicit
   `target_id`, `target_table`, `relationship`, and `direction`. Fulfilled intent is
   covered by an outcome that `implements` it; remaining work by an open gap todo
   that `blocks` it. Do not fabricate coverage or links merely to clear a gate.
3. Check record success and every per-link result: `created` / `existing` succeed;
   `error`, missing results, or mismatched counts mean partial persistence.
4. Read back exact records with `get_record` and required edges with `list_links`.
   For existing-pair or legacy-server repairs use `upsert_link`, reversing endpoints
   for incoming relationships. A saved record must not be recreated after link failure.
   Link repair alone cannot clear `pending_write_failures`: after record/link readback,
   perform a successful same-ID `upsert_record` recovery preserving verified fields,
   verify again, and fetch a fresh session snapshot. Follow the persist skill.
5. Only after reconciliation call `reqall_session action=acknowledge` with the captured
   `session_id`, `work_revision`, and verified `record_ids`. Check its response and
   read session status back. Never invent a session ID or manually clear dirty state.
   Older outcomes cannot cover newer work by merely supplying a newer revision;
   document the additional work and re-upsert the outcome in the current batch.
6. If verification, links, or recovery fail, keep work pending and report the gap.
   A successful transport response or record write alone is not proof of completion.

Prefer `issue`, `todo`, `spec`, `arch`, `test`, or `info`; `work` is an ephemeral log.
SLEEP retains `work_review`, `promote`, and `discard` plus its other operations.

## Actual hook timing

`pre_llm_call` runs once per user turn, not between tools. It also polls the bound
project's subscription and may inject `## Reqall updates since last turn`: changes
from other sessions, teammates, or SLEEP. Treat them as background context; fetch
with `get_record` before acting. `reqall action=poll_subscriptions` drains more. Perform explicit recall
before a specific edit if needed. `pre_tool_call` does not inject remote context;
`post_tool_call` observes results, including explicitly reported partial saves.
`pre_verify` is a bounded file-edit finalization reminder, not an all-chat Stop hook.
Session end/finalize only log pending work. No general-plugin pre-compaction tool
round is guaranteed: persist intent and outcomes incrementally, including meaningful
research/chat/delegation results. Hooks fail open without claiming persistence.
