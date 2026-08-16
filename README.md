# Reqall Hermes Plugin

Persistent semantic memory for [Hermes Agent](https://hermes-agent.nousresearch.com).

Automatically retrieves project context on non-trivial turns, surfaces file-focused
recall before edits, and nudges persistence after meaningful tool use — backed by
the [Reqall](https://www.reqall.net) knowledge base (plugin HTTP client + optional host MCP).

Sibling of the Claude / Codex / Grok Build Reqall plugins, adapted to Hermes’
Python plugin surface (`register(ctx)`, hooks, skills, tools).

## Install

```bash
hermes plugins install ReqallSystem/hermes-plugin --enable
# or from a clone:
hermes plugins install /path/to/hermes-plugin --enable
```

Hermes copies the plugin into **the current `$HERMES_HOME/plugins/reqall`**.
Named profiles (`~/.hermes/profiles/<name>`) are separate homes. Listing
`reqall` in that profile’s `plugins.enabled` does **not** load the default-home
checkout.

After install, sync into every profile that already enabled the plugin:

```bash
python3 /path/to/plugins/reqall/ensure-install.py
# or, once any session has the plugin loaded:
# /reqall ensure-install
```

That creates `$HERMES_HOME/plugins/reqall` as a symlink to this tree. It never
overwrites an existing checkout. Opt out of the automatic `register()` sync
with `REQALL_SKIP_PROFILE_SYNC=1`.

Per-profile install (equivalent):

```bash
HERMES_HOME=~/.hermes/profiles/<profile> hermes plugins install ReqallSystem/hermes-plugin --enable
```

Dev symlink:

```bash
ln -sfn ~/dev/Reqall/hermes-plugin ~/.hermes/profiles/<profile>/plugins/reqall
HERMES_HOME=~/.hermes/profiles/<profile> hermes plugins enable reqall
```

Restart **that profile’s** gateway from an **external** shell, then `/new` on
long-lived chats so hooks and tools load.

## Authentication

1. Create an API key at [reqall.net](https://www.reqall.net)
2. Set in the **active profile** `.env` (secrets only). Any one of:

```bash
REQALL_API_KEY=your-key-here
# MCP_REQALL_API_KEY=your-key-here
# REQALL_MCP_API_KEY=your-key-here
# optional:
# REQALL_URL=https://www.reqall.net
# REQALL_PROJECT_NAME=org/repo
```

### MCP server (optional but recommended)

Add to the **same profile** `config.yaml`. The config key’s case becomes the
Hermes tool prefix (`reqall` → `mcp__reqall__*`, `Reqall` → `mcp__Reqall__*`).
The plugin treats those names as equivalent.

```yaml
mcp_servers:
  reqall:
    url: "https://www.reqall.net/mcp"
    headers:
      Authorization: "Bearer ${REQALL_API_KEY}"
      # or ${MCP_REQALL_API_KEY}
```

After enabling MCP: **restart the gateway** (external shell) and **`/new`**.
Hermes freezes the tool list for prompt caching; mid-session discovery will not
add MCP tools to an already-open conversation.

The plugin still works **without** host MCP: use the `reqall` tool (`action` + `arguments`).

## What it does

### Hooks

| Event | Behavior |
|-------|----------|
| `on_session_start` | Bind project (`REQALL_PROJECT_NAME` → git `org/repo` → prompt hint). Generic home dirs stay **unbound** |
| `pre_llm_call` | Work-like prompts: search (upsert + open list only when bound); dirty-session persist nudge |
| `pre_tool_call` | Before mutations: conceptual search (not the raw path) |
| `post_tool_call` | Mark dirty; throttled document nudge |
| `pre_verify` | If dirty / `changed_paths`, continue once so persist can run |
| `on_session_end` / `on_session_finalize` | Log remaining dirty work |

All handlers **fail-open** (never trap the agent).

### Skills

| Skill | Purpose |
|-------|---------|
| `reqall-context` | Deep manual context gather |
| `reqall-document` | One work item |
| `reqall-persist` | Full session persistence |
| `reqall-triage` | Incoming issue triage |
| `reqall-review` | Open-record review |
| `reqall-sleep` | Compress memory (consolidate / split / compact / skip / crosslink / promote / discard) |

Qualified name: `reqall:reqall-persist` via `skill_view` when that toolset is
enabled. If the host disabled `skills`, use plugin tool `reqall_skill` or
`/reqall persist` (dumps the skill markdown).

### Tools / slash

| Surface | Name | Notes |
|---------|------|--------|
| Tool | `reqall` | `action` = MCP op (`upsert_record`, `search`, …), `arguments` = object |
| Tool | `reqall_status` | Auth + project + dirty + MCP probe + **profile-install gaps** |
| Tool | `reqall_skill` | Return a bundled skill body without `skill_view` |
| Slash | `/reqall` | `status \| check \| persist \| sleep \| prompt \| ensure-install \| clear-dirty` |
| Host MCP | `mcp__reqall__*` / `mcp__Reqall__*` | When `mcp_servers.reqall` (any case) is connected |

## Environment and config

Secrets stay in the profile `.env`. Behavioral settings belong in
`config.yaml` under `plugins.entries.reqall.settings` (env still overrides):

```yaml
plugins:
  enabled: [reqall]
  entries:
    reqall:
      settings:
        project_name: org/repo          # optional default
        doc_interval_min: 10
        persist_interval_min: 30
        skip_profile_sync: false
```

| Variable / setting | Default | Description |
|----------|---------|-------------|
| `REQALL_API_KEY` | required* | Bearer token |
| `MCP_REQALL_API_KEY` | — | Alias accepted by the plugin HTTP client |
| `REQALL_MCP_API_KEY` | — | Alias accepted by the plugin HTTP client |
| `REQALL_URL` | `https://www.reqall.net` | API base |
| `REQALL_PROJECT_NAME` / `settings.project_name` | auto | Override project id string |
| `REQALL_DOC_INTERVAL_MIN` / `settings.doc_interval_min` | `10` | Minutes between document nudges (`0` = every time) |
| `REQALL_PERSIST_INTERVAL_MIN` / `settings.persist_interval_min` | `30` | Minutes between persist nudges |
| `REQALL_SKIP_PROFILE_SYNC` / `settings.skip_profile_sync` | unset | Disable automatic sibling-profile symlinks on `register()` |

\*One of `REQALL_API_KEY` / `MCP_REQALL_API_KEY` / `REQALL_MCP_API_KEY` (or the
shared Reqall CLI auth file) must be set.

## Development

```bash
cd hermes-plugin
python3 -m unittest discover -s tests -v
```

No build step — pure Python, stdlib HTTP client.

## License

MIT
