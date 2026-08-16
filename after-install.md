# After installing the Reqall Hermes plugin

Hermes loads user plugins only from **`$HERMES_HOME/plugins/reqall`**.
Each named profile is a separate home (`~/.hermes/profiles/<name>`).
`plugins.enabled: [reqall]` in a profile does **not** copy the files.

```bash
# Install into the *current* HERMES_HOME, then enable:
hermes plugins enable reqall

# Sync this checkout into every profile that already enabled reqall:
python3 ensure-install.py
# or: python3 -m reqall.install   (from the plugin directory)
```

1. Put secrets in the **active profile** `.env` only. Either name works:

```bash
REQALL_API_KEY=…
# or the host-MCP alias:
# MCP_REQALL_API_KEY=…
# REQALL_URL=https://www.reqall.net
# REQALL_PROJECT_NAME=org/repo
```

2. **Optional host MCP** in that same profile `config.yaml` (any key case):

```yaml
mcp_servers:
  reqall:   # or Reqall — tools become mcp__reqall__* or mcp__Reqall__*
    url: https://www.reqall.net/mcp
    headers:
      Authorization: Bearer ${REQALL_API_KEY}
      # ${MCP_REQALL_API_KEY} is also accepted by the plugin HTTP client
```

3. Restart **that profile's** gateway from an **external** shell (a gateway
   session cannot restart itself). On long-lived chats run **`/new`**.

4. Verify:

```text
/reqall check
/reqall ensure-install
```

`reqall_status` should show `plugin_loaded: true`. If
`profile_installs_missing` is non-empty, run `/reqall ensure-install`,
restart those profiles, then `/new`.

5. Persist without host MCP: `reqall` action=`upsert_record`.
   If `skill_view` is disabled: `reqall_skill` name=`reqall-persist`
   or `/reqall persist` (dumps the skill body).
