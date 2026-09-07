# After installing Reqall

Install/update only the active `$HERMES_HOME/plugins/reqall`. Named profiles are
separate. Registration never installs into another profile. Do not run
`ensure-install.py` unless the user explicitly requests cross-profile installation.

1. Configure `REQALL_API_KEY` (or an accepted MCP alias) in the active profile's
   secrets. Put project/machine/interval settings in config via `hermes config set`.
2. Start a fresh Hermes process/session to load the plugin. Restart gateways only
   from an external shell, not their own agent session.
3. `/reqall status` diagnoses; `/reqall check` performs a read-only auth check.
4. Use `reqall_skill name=reqall-context` then `reqall-intend` for substantial
   agreed work, and `reqall-persist` for outcomes.
5. Capture `reqall_session action=status` before persisting; acknowledge with
   exact `session_id`, `record_ids`, and snapshot `work_revision` only after records
   and links are verified. The tool performs readbacks before clearing pending work.

Host MCP OAuth alone does not supply the typed readbacks required by this plugin's
acknowledgement yet. Keep a profile-scoped API key for native `reqall` operations.
The old `/reqall clear-dirty` no longer bypasses persistence checks. Existing records
and session markers are preserved; no migration/deletion is performed.
