# Reqall Hermes Plugin

Persistent project memory for [Hermes Agent](https://hermes-agent.nousresearch.com),
backed by [Reqall](https://www.reqall.net).

Workflow: **recall → record agreed intent → work → persist records and links →
verify and acknowledge**. Python 3.11+, standard library runtime.

## Installation and upgrade

```bash
hermes plugins install ReqallSystem/hermes-plugin --enable
# Or install the reviewed checkout into the active profile:
hermes plugins install /path/to/hermes-plugin --enable
```

Only the active profile should be installed or updated. Loading the plugin does
**not** synchronize other profiles, regardless of old `skip_profile_sync` settings.
The explicit `ensure-install.py` / `/reqall ensure-install` operation still exists
for users who deliberately request cross-profile installation; it is not part of
normal setup or status checks. It may link multiple enabled profiles.

Start a new Hermes process/session after upgrading to load the new Python code and
tool registrations. Do not restart a gateway from inside its own session. No record
migration, deletion, or state reset is required. Existing JSON session markers remain
readable; new writes use transactional locking and revision checks.

## Authentication

Set a key in the **active profile's** `.env` / supported secret configuration:

```text
REQALL_API_KEY=your-key
```

`MCP_REQALL_API_KEY` and `REQALL_MCP_API_KEY` are also accepted. Runtime credential
resolution respects Hermes's profile-local secret scope; it must not fall through
to another profile's environment or a shared CLI login under a scoped deployment.
Behavioral settings belong in config, not the secret file.

Optional host MCP tools (`mcp__reqall__*`, or `mcp__Reqall__*`) can be configured with
Hermes's supported MCP commands. Host MCP OAuth is supported by Hermes itself, but
**OAuth-only verified plugin persistence is not implemented in this release**.
The current host renderer can discard `structuredContent` when human-readable text
exists, losing the typed IDs and links required by acknowledgement. Use the plugin's
API-key-backed `reqall` tool for verifiable writes/readbacks. Do not copy host token
files or expect the native client to refresh host OAuth tokens.

`/reqall check` makes a read-only `list_projects` request; it never creates a project.
Failures remain failures, including JSON-RPC errors, MCP `isError`, malformed replies,
and failed inline links. A partially successful write is not retried automatically.

## Project routing

1. `REQALL_PROJECT_NAME` or scoped `settings.project_name`.
2. Actual git `origin` repository identity.
3. Explicit labelled project selection in the prompt (`project_name=org/repo`).
4. Reserved `.machine/<short-host>/<os-user>` project.

Use `REQALL_MACHINE_NAME` or `settings.machine_name` for stable CI/container identity.
Directory basenames and ordinary prose paths such as `src/auth.py` never become
project names. Existing records are not renamed or migrated. Deliberately route
account-wide preferences to `.user`; do not accidentally record them as repo work.

## Tools and skills

| Tool | Purpose |
|---|---|
| `reqall` | Reqall operation in `action`, payload in `arguments` |
| `reqall_status` | Auth/project/host status; optional read-only auth check and explicit `session_id` |
| `reqall_skill` | Load bundled skill text even without the host skills toolset |
| `reqall_session` | Session status, explicit intent selection, verified persistence acknowledgement |

Skills: `reqall-context`, **`reqall-intend`**, `reqall-document`, `reqall-persist`,
`reqall-triage`, `reqall-review`, `reqall-sleep`. Qualified `skill_view` name example:
`reqall:reqall-intend`. Slash skill loaders include `/reqall intend` and `/reqall persist`.

`reqall-intend` records only substantial agreed scope, with acceptance criteria and
non-goals. Search and reuse existing specs first. A spec merely consulted for
background is not a commitment. Select existing agreed intent explicitly with
`reqall_session action=select_intent record_id=...`.

### Verified acknowledgement

1. `reqall_session action=status` → capture `session_id`, `work_revision`, and pending intent.
2. Persist outcomes through `reqall action=upsert_record`, supplying inline `links`.
3. Verify each record and edge. Fulfilled intent has an outcome `implements` the
   spec; remaining work has an open gap todo `blocks` the spec.
4. `reqall_session action=acknowledge` with that `session_id`, snapshot `work_revision`,
   and persisted `record_ids`.

Acknowledgement reads the exact records/links again. Missing reconciliation, wrong
projects, unavailable service, or a newer work revision leaves work pending. When
the host cannot supply a session identifier, pass the one injected at turn start;
never invent it or substitute a project name. No mutation silently targets `default`.
The old `/reqall clear-dirty` command explains the replacement but cannot clear state.

Inline links save round trips, **not an all-or-nothing transaction**. Check every
requested link result (`created`, `existing`, `error`) and use exact readbacks after
uncertain results. `upsert_link` remains available for existing pairs or older servers.
Never recreate a saved record merely because one link failed.

## Honest lifecycle guarantees

| Hook | Behavior |
|---|---|
| `on_session_start` | Initialize session binding without cross-profile installation |
| `pre_llm_call` | Once per user turn: recall and pending intent/persistence guidance |
| `pre_tool_call` | Cheap, non-blocking observer; no remote lookup and no false pre-edit injection |
| `post_tool_call` | Successful activity tracking and typed intent/result bookkeeping |
| `pre_verify` | Bounded edited-code persistence reminder; no permanent session latch |
| Session end/finalize | Log outstanding work; do not claim it was saved |

Hermes does not call `pre_llm_call` between tools. The old queued “pre-edit recall”
was too late and has been removed. Use `reqall-context` / explicit search before a
specific edit when more context is needed. `pre_verify` is an edited-file gate,
**not** a universal Stop hook: persist meaningful chat, research, and delegated
findings explicitly. There is no general-plugin pre-compaction tool round; save
intent incrementally. This plugin does not replace the active memory provider.

Failed/blocked tool attempts are not completed work. Shell compounds and redirects
are classified conservatively. Hooks fail open on errors without claiming success.
SLEEP retains `work_review`, `promote`, and `discard`, alongside consolidation,
splitting, compaction and crosslinks. Destructive and sharing operations require
an explicit user request. Never persist credentials or unrelated private data.

## Settings

Set active-profile behavior with `hermes config set`, for example:

```bash
hermes config set plugins.entries.reqall.settings.project_name ReqallSystem/hermes-plugin
hermes config set plugins.entries.reqall.settings.machine_name stable-dev-box
```

| Setting | Environment override | Default |
|---|---|---|
| `project_name` | `REQALL_PROJECT_NAME` | routing above |
| `machine_name` | `REQALL_MACHINE_NAME` | short hostname |
| `api_url` | `REQALL_URL`, `REQALL_API_URL` | `https://www.reqall.net` |
| `doc_interval_min` | `REQALL_DOC_INTERVAL_MIN` | 10 |
| `persist_interval_min` | `REQALL_PERSIST_INTERVAL_MIN` | 30 |

The interval settings remain readable for configuration compatibility. Current
persistence reminders are turn-based (bounded once per turn), not timers; these
legacy intervals do not change that behavior.

## Development and verification

```bash
python3 scripts/test_offline.py
hermes plugins compat /path/to/hermes-plugin
```

The test runner uses temporary HOME/HERMES_HOME/XDG_CONFIG_HOME and rejects socket
connections. It covers host-shaped payloads, scoped state/auth, revisions,
acknowledgement, machine routing, semantic failures and partial writes. Test results
are not a claim that production OAuth or live service writes were exercised.

No build step. Do not deploy until tests and the host compatibility scan pass.

## License

MIT
