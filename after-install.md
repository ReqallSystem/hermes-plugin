# Reqall plugin installed

1. **Enable** (if you skipped `--enable`):

```bash
hermes plugins enable reqall
```

2. **Set secrets** in this profile’s `.env`:

```bash
REQALL_API_KEY=...
# REQALL_URL=https://www.reqall.net
```

3. **Optional MCP** in `config.yaml` so the model can call Reqall tools directly:

```yaml
mcp_servers:
  reqall:
    url: "https://www.reqall.net/mcp"
    headers:
      Authorization: "Bearer ${REQALL_API_KEY}"
```

4. **New session**, then:

```text
/reqall check
```

Skills: `reqall-context`, `reqall-persist`, `reqall-document`, …

Docs: https://github.com/ReqallSystem/hermes-plugin
