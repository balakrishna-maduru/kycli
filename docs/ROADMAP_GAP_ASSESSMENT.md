# Roadmap Gap Assessment

## Summary

Phase 8 is now reconciled with the shipped feature set, and the core RBAC work described for Phase 9 has been implemented. The main remaining roadmap gap is the non-TUI fuzzy/history prompt idea, which is now formally deferred in favor of `kyshell`.

## Implemented roadmap items

The following planned items are already present in the current repository:

- **Batch Queue Ops**: `kypush --file` and `kypop --n` are implemented in `kycli/cli.py` and covered by `tests/test_cli_roadmap.py`.
- **Delayed Jobs**: queue delay support exists through `kypush --delay` and the queue availability logic in `kycli/core/storage.pyx`.
- **Visibility Timeout / Ack / Nack**: `kypop --lease`, `kyack`, and `kynack` are implemented in `kycli/cli.py` and `kycli/core/storage.pyx`.
- **Workspace TTL Policies**: `kyttl set|get` is implemented in `kycli/cli.py` and `kycli/core/storage.pyx`.
- **Config Profiles**: `kyprofile list|use|save` is implemented in `kycli/cli.py`.
- **Audit Export**: `kyaudit export` with `since` / `until` support is implemented in `kycli/cli.py` and `kycli/core/storage.pyx`.
- **Stats Command**: `kystats` is implemented in `kycli/cli.py` and `kycli/core/storage.pyx`.
- **Metrics Endpoint**: `kymetrics` is implemented in `kycli/cli.py`.
- **Namespace/Prefix Views**: `kyws view <prefix>` is implemented in `kycli/cli.py` and backed by `view_prefix` in `kycli/core/storage.pyx`.
- **Backup/Restore**: `kybackup` create/restore is implemented in `kycli/cli.py` and `kycli/core/storage.pyx`.
- **Current ACL baseline**: workspace-wide read-only mode and shared access-key gating exist today under `kyacl readonly` and `kyacl key`.
- **RBAC**: `kyacl enable|disable|status`, principals, roles, `--token` / `KYCLI_TOKEN`, key-level allow/deny rules, and RBAC-aware stats/audit hooks are implemented in `kycli/cli.py`, `kycli/core/storage.pyx`, and `kycli/core/security.pyx`.

## Remaining gaps

### 1. Interactive non-TUI prompts are still a gap

The roadmap item says:

- **Interactive CLI Prompts**: fuzzy key search + history in non-TUI mode

Current state:

- `kycli/tui.py` has prompt-toolkit completions for the TUI shell.
- `kycli/cli.py` remains a standard one-shot CLI and only uses basic `input()` confirmations.

Gap:

- No fuzzy key search in the normal CLI path.
- No reusable command history for non-TUI commands.

### 2. Future RBAC stretch work remains

The core RBAC phases are implemented, but the stretch items remain future work:

- custom roles
- principal groups
- workspace-wide default key policies independent of a principal

## Recommended plan

### Priority 1: Keep roadmap tracking current

1. Keep `TODO.md` aligned with shipped behavior as roadmap items land.
2. Keep deferred items explicitly marked as deferred rather than silently open.
3. Keep `docs/ROLES_PERMISSIONS.md` aligned with the shipped RBAC surface.

### Priority 2: Revisit the deferred interactive CLI idea only if needed

1. Reassess whether one-shot CLI commands truly benefit from prompt-toolkit flows.
2. If yes, limit the scope to opt-in selectors so scripts stay unaffected.
3. Otherwise, keep `kyshell` as the interactive path and leave the roadmap item deferred.

### Priority 3: Extend RBAC only with clearly scoped follow-ups

1. Add custom roles only if the fixed role model proves insufficient.
2. Add principal groups only if there is a real multi-user management need.
3. Add default key policies only if repeated per-principal ACL rules become a maintenance issue.

## Recommended execution order

1. Keep roadmap tracking current.
2. Revisit the deferred non-TUI prompt feature only if user demand justifies it.
3. Treat RBAC follow-ups as separate enhancements rather than unfinished baseline work.
