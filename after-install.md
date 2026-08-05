# After installing the Reqall Hermes plugin

```bash
hermes plugins enable reqall
```

1. Put secrets in the active profile `.env` only:

```bash
REQALL_API_KEY=…
# REQALL_URL=https://www.reqall.net
# REQALL_PROJECT_NAME=org/repo
```

2. **Optional host MCP** in `config.yaml` (exposes `mcp__reqall__*` to the model):

```yaml
mcp_servers:
  reqall:
    url: https://www.reqall.net/mcp
    headers:
      Authorization: Bearer ${REQALL_API_KEY}
```

3. Restart the gateway. On long-lived chats run **`/new`** so the tool list can include MCP tools (prompt-cache freeze).

4. Verify:

```text
/reqall check
```

or tool `reqall_status` with `check_auth=true`. Confirm `mcp_host.host_mcp_registered` and/or use plugin tool `reqall` with `action=search`.

5. Persist without MCP: `reqall` action=`upsert_record` arguments=`{…}`.
