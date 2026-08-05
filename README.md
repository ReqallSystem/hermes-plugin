# Reqall Hermes Plugin

Persistent semantic memory for [Hermes Agent](https://hermes-agent.nousresearch.com).

Automatically retrieves project context on non-trivial turns, surfaces file-focused
recall before edits, and nudges persistence after meaningful tool use — backed by
the [Reqall](https://www.reqall.net) knowledge base (MCP + HTTP tools/call).

Sibling of the Claude / Codex / Grok Build Reqall plugins, adapted to Hermes’
Python plugin surface (`register(ctx)`, hooks, skills, tools).

## Install

```bash
hermes plugins install ReqallSystem/hermes-plugin --enable
# or from a clone:
hermes plugins install /path/to/hermes-plugin --enable
```

```bash
hermes plugins enable reqall
```

Dev symlink (example profile):

```bash
ln -sfn ~/fingerskier/hermes-plugin ~/.hermes/profiles/<profile>/plugins/reqall
HERMES_HOME=~/.hermes/profiles/<profile> hermes plugins enable reqall
```

Restart the gateway / start a **new session** so hooks load.

## Authentication

1. Create an API key at [reqall.net](https://www.reqall.net)
2. Set in the active profile `.env` (secrets only):

```bash
REQALL_API_KEY=your-key-here
# optional:
# REQALL_URL=https://www.reqall.net
# REQALL_PROJECT_NAME=org/repo
```

### MCP server (recommended)

Add to the profile `config.yaml` so the agent can call Reqall tools natively:

```yaml
mcp_servers:
  reqall:
    url: "https://www.reqall.net/mcp"
    headers:
      Authorization: "Bearer ${REQALL_API_KEY}"
```

(Exact MCP config keys may follow your Hermes version — see `hermes mcp --help`
and the MCP docs. The hook layer also calls `/mcp` tools/call directly with the
same Bearer token for recall injection.)

## What it does

### Hooks

| Event | Behavior |
|-------|----------|
| `on_session_start` | Resolve project name (`REQALL_PROJECT_NAME` → git `org/repo` → cwd) |
| `pre_llm_call` | Non-trivial prompts: `upsert_project` + `search` + open `list_records`, inject as context; dirty-session **persist nudge** |
| `pre_tool_call` | Before `write_file` / `patch` / mutating `terminal`: path-focused search |
| `post_tool_call` | Mark dirty; throttled **document** nudge |
| `on_session_end` | Log remaining dirty work |

All handlers **fail-open** (never trap the agent).

### Skills

| Skill | Purpose |
|-------|---------|
| `reqall-context` | Deep manual context gather |
| `reqall-document` | One work item |
| `reqall-persist` | Full session persistence |
| `reqall-triage` | Incoming issue triage |
| `reqall-review` | Open-record review |
| `reqall-sleep` | Compress memory (consolidate / split / compact / skip / crosslink) |

### Tools / slash

- Tool: `reqall_status` — auth/project/session snapshot (`check_auth=true` pings API)
- Slash: `/reqall status|check|context|persist|clear-dirty`

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `REQALL_API_KEY` | required | Bearer token |
| `REQALL_URL` | `https://www.reqall.net` | API base |
| `REQALL_PROJECT_NAME` | auto | Override project id string |
| `REQALL_DOC_INTERVAL_MIN` | `10` | Min minutes between document nudges (`0` = every time) |
| `REQALL_PERSIST_INTERVAL_MIN` | `30` | Min minutes between persist nudges |

## Development

```bash
cd hermes-plugin
python3 -m unittest discover -s tests -v
```

No build step — pure Python, stdlib HTTP client.

## License

MIT
