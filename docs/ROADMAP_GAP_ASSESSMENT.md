# Roadmap Gap Assessment

## Summary

Most of the Phase 8 roadmap items in `TODO.md` are already implemented in the codebase, but the checklist has not been updated to reflect that work.

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

## Remaining gaps

### 1. TODO roadmap status is stale

`TODO.md` still marks most Phase 8 items as incomplete even though the features already exist and have roadmap coverage tests.

### 2. Interactive non-TUI prompts are still a gap

The roadmap item says:

- **Interactive CLI Prompts**: fuzzy key search + history in non-TUI mode

Current state:

- `kycli/tui.py` has prompt-toolkit completions for the TUI shell.
- `kycli/cli.py` remains a standard one-shot CLI and only uses basic `input()` confirmations.

Gap:

- No fuzzy key search in the normal CLI path.
- No reusable command history for non-TUI commands.

### 3. Output formatting is only partially complete

The roadmap item says:

- **Output Formatting**: `--json` everywhere; `--pretty` for tables

Current state:

- Structured rendering exists for commands like `kyg`, `kyl`, `kypop`, `kystats`, and prefix view.

Gap:

- Formatting is not consistent across the full command surface.
- Several commands still print plain strings or ad hoc text only, including `kypeek`, `kycount`, `kyack`, `kynack`, backup success messages, and audit export success messages.

### 4. ACL/RBAC roadmap remains unimplemented

Phase 9 in `TODO.md` is still open, and `docs/ROLES_PERMISSIONS.md` explicitly says the RBAC work is **design only — not yet implemented**.

Current state:

- Implemented: workspace-wide `readonly` and one shared `access_key`.
- Missing: principals, roles, per-key allow/deny rules, `--token` / `KYCLI_TOKEN`, `kyacl user`, `kyacl role`, `kyacl whoami`, and RBAC-aware audit/stats.

## Recommended plan

### Priority 1: Reconcile roadmap tracking

1. Update `TODO.md` so implemented Phase 8 items are checked off.
2. Keep only the real open gaps unchecked.
3. Add one short note pointing readers to the RBAC design doc for Phase 9.

### Priority 2: Finish the remaining Phase 8 usability gaps

1. Standardize response rendering so every read-style and status-style command can emit `--json`.
2. Define a consistent `--pretty` table format for multi-row outputs.
3. Add non-TUI interactive enhancements only where they fit the existing CLI model:
   - history-backed prompts for optional interactive flows
   - fuzzy key/workspace selection for commands that currently require exact names
4. Add regression coverage for all newly structured outputs.

### Priority 3: Implement RBAC in phases

1. **Storage foundation**
   - add `principals`, `workspace_roles`, `key_acl`
   - add `rbac_enabled` workspace metadata
   - hash tokens instead of storing plaintext
2. **Policy engine**
   - generalize write checks into verb-based authorization
   - enforce permissions on both reads and writes
   - preserve current readonly/access-key behavior when RBAC is disabled
3. **CLI surface**
   - add `kyacl enable|disable|status`
   - add `kyacl user ...`
   - add `kyacl role ...`
   - add `kyacl whoami`
   - add `--token` and `KYCLI_TOKEN`
4. **Audit and observability**
   - log grants, revokes, enable/disable events, and denials
   - surface RBAC state in `kystats`
5. **Docs and migration**
   - document opt-in migration from shared access-key mode
   - add compatibility tests for legacy workspaces

## Recommended execution order

1. Refresh roadmap tracking in `TODO.md`.
2. Close the Phase 8 formatting gap.
3. Decide whether non-TUI fuzzy/history is still a desired feature or should be formally deferred in favor of `kyshell`.
4. Start RBAC Phase A only after the Phase 8 tracking/documentation is accurate.
