# 🩺 Recovery & Maintenance

`kycli` is designed to be resilient against accidental data loss.

## Recovery Commands

### `kyr <key>` (Restore Single Key)
Restores the most recent *previous* version of a key from the archive/history.
- **Scenario**: You accidentally deleted `user_config` or overwrote it with bad data.
- **Action**: `kyr user_config`
- **Result**: The key is revived in the active store.

**Advanced**: Restore from a specific timestamp.
```bash
kyr user_config --at "2026-01-08 12:00:00"
```

### `kyrt <timestamp>` (Point-in-Time Recovery)
The "Time Machine" feature. This rolls back the **Entire Active Workspace** to a specific state.
- **How it works**: It replays the audit log up to the timestamp.
- **Scope**: Affects only the current workspace.

```bash
# Undo everything done in the last hour
kyrt "2026-01-09 10:00:00"
```

## Maintenance

### `kyco` (Compact)
`kycli` databases are SQLite files. Over time, "deleted" space (from writes/updates) can fragment the file.
`kyco` performs two actions:
1.  **Purge History**: Removes audit logs and archives older than `N` days (default 15).
2.  **Vacuum**: Rebuilds the database file to reclaim disk space and optimize B-Tree indexes.

```bash
# Keep only 7 days of history and optimize
kyco 7
```

**Recommendation**: Run `kyco` once a week for heavy-write workloads.
