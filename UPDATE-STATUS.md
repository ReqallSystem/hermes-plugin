# Reqall Hermes 2026.9.7 — GitHub round-trip verification

## Completed

- Fresh user authorization and normal protected-file approval allowed AGENTS.md to be updated. The prior documentation blocker is resolved.
- Bumped plugin.yaml and changelog to 2026.9.7.
- Committed the reviewed implementation, skills, documentation and regression tests:
  `be73b3cff9915f78ecd7eb83d710336c6f32c2ba`.
- Pushed `fix/hermes-memory-workflow` to `https://github.com/ReqallSystem/hermes-plugin.git`.
- Verified GitHub branch SHA matches the local commit.
- Backed up the previous default-profile plugin, including its local import hotfix,
  to `/home/fingerskier/.hermes/reqall-release-backup.JKZVbe/plugin`; recursive comparison passed before installation.
- Reinstalled FROM GITHUB, not the development checkout:
  `HERMES_HOME=/home/fingerskier/.hermes hermes plugins install ReqallSystem/hermes-plugin --force --ref be73b3cff9915f78ecd7eb83d710336c6f32c2ba --enable`.
- Installed target: `/home/fingerskier/.hermes/plugins/reqall`.
- Installed HEAD matches the pushed commit exactly; tracked files match that commit and git status is clean.
- Hermes reports `reqall v2026.9.7`, enabled, source git.

## Verification

- Development checkout: all 87 offline tests pass, including AGENTS.md contract.
- GitHub-installed checkout: all 87 offline tests pass.
- Real-Hermes offline hook/secret-scope smoke passes on both checkouts, with temporary state and network denied.
- Installed compatibility scan passes (no imports scheduled for removal on 2026-09-14).
- Installed native client read-only get_record probe of #5084 passes with typed id, project_id and kind; no body or credential printed.
- Independent spec and quality reviews were completed and reported defects fixed/re-reviewed before publication.

## Scope and caveats

- Published to the feature branch only; main was not merged, and no GitHub release/tag was created.
- Installation is pinned to the exact SHA. Future pinned upgrades require an explicit new `--ref`; ordinary update will not advance the pin.
- The running Hermes process was not restarted. Start a fresh Hermes process before expecting new live tool registrations/hooks; the smoke test used a separate process.
- Only the default profile was installed. No sibling-profile installs, record migration, or host-core changes were performed.
- Live workflow write/acknowledgement and OAuth-only verification were not exercised. OAuth remains deliberately deferred because the inspected host renderer may lose structured identity.
- SQLite thread/process transaction tests ran on Linux, not native Windows.
- This handoff and verification-static.json are local-only artifacts, not part of the pushed commit.
