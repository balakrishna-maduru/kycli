# 🏢 Multi-Tenancy (Workspaces)

`kycli` allows you to organize your data into **Workspaces**. 

## Concepts
- **Default Isolation**: By default, you are in the `default` workspace.
- **File-Per-Workspace**: Each workspace gets its own database file (`~/.kycli/data/<name>.db`).
- **Performance**: Operations in one workspace do not impact others (no locking contention).
- **Security**: Encryption keys can be shared or unique per workspace (via CLI flags or ENV vars changing per session).

## Commands

### `kyuse <workspace>`
Switch to a new or existing workspace.
- If the workspace does not exist, it is "lazy-created" (the file appears only when you first write data).
- **Migration**: If you have an old `~/kydata.db` from a previous version, it is automatically migrated to the `default` workspace.

```bash
kyuse project_alpha
# Result: ➡️ Switched to workspace: project_alpha
```

### `kyws`
List all currently available workspaces. The active one is marked with `✨`.

```bash
kyws
# Result:
# 📂 Workspaces:
#    default
# ✨ project_alpha
#    staging
```

### `kymv <key> <target_workspace>`
Move a key (and its value) from the *current* workspace to a *target* workspace.
- This is an **Atomic Move**:
    1.  Read from Source.
    2.  Write to Target.
    3.  Delete from Source.
- **Safety**: If the key already exists in the target, `kycli` will ask for confirmation before overwriting.

```bash
# Move 'api_key' to 'production' workspace
kymv api_key production
```
