# Roadmap: Multi-Tenancy (File-Per-Schema Strategy)

This document outlines the strategic roadmap for introducing **Workspaces** (Schemas) to KyCLI. 
Based on performance and isolation analysis, we will adopt a **File-Per-Workspace** strategy. 

## 🏗️ Architecture Decision: File-Per-Workspace
Instead of cramming all data into a single `sqlite` file with a massive composite key, we will create separate database files for each workspace.

### Why this is better?
1.  **🚀 Performance & Concurrency**: Writes to *Project A* will never block writes to *Project B*. Each file has its own WAL (Write-Ahead Log) and lock.
2.  **🛡️ Isolation**: Corruption or accidental deletion in one workspace does not affect others.
3.  **📂 Portability**: Users can easily share `project_x.db` with a colleague without extracting data from a giant monolithic DB.
4.  **📉 Simplicity**: No complex SQL schema migrations (`ALTER TABLE`) required. The internal structure of `kvstore` remains exacty the same.

## 🌟 The Vision
The data directory will evolve from a single file to a managed folder:
```text
~/.kycli/
  ├── data/
  │   ├── default.db
  │   ├── project_alpha.db
  │   └── production.db
  └── config.toml
```

## 🗺️ Implementation Phases

### Phase 1: Directory Restructuring & Migration 📦
We need to move the user's existing data to the new structure without data loss.

- [ ] **Migration Script**: On first run of v0.2.0:
    1.  Create `~/.kycli/data/`.
    2.  Check for legacy `~/kydata.db`.
    3.  Move it to `~/.kycli/data/default.db`.
    4.  Update internal Config loader to look in this new path by default.

### Phase 2: CLI Context Management 🎮
Implement the logic to switch the "active" database file.

- [ ] **Config Update**: Add `current_workspace = "default"` to configuration.
- [ ] **New Command: `kycli use <name>`**:
    - Checks if `~/.kycli/data/<name>.db` exists.
    - If not, prompts to create it.
    - Updates `current_workspace` in config.
- [ ] **New Command: `kycli list-workspaces`**: 
    - Scans `~/.kycli/data/*.db` and prints them, highlighting the active one.
- [ ] **Runtime Swapping**: Update `cli.py` to read `current_workspace`, resolve the full path, and pass it to `Kycore`.

### Phase 3: Workspace Lifecycle Management ♻️
- [ ] **Command: `kycli create <name>`**: Explicitly create a new empty workspace.
- [ ] **Command: `kycli drop <name>`**: Delete a workspace file (with "ARE YOU SURE?" confirmation).
- [ ] **Command: `kycli rename <old> <new>`**: Rename the database file safely.

### Phase 4: TUI Enhancements 🖥️
- [ ] **Status Bar**: Display `[Workspace: project_alpha]` in the footer.
- [ ] **Hot-Swapping**: Allow switching workspaces inside the generic TUI session.

## ⚠️ Breaking Changes & Risks
- **Path Change**: Users hardcoding `~/kydata.db` in scripts will need to update their paths or environment variables.
- **Environment Var**: `KYCLI_DB_PATH` will take precedence over the "active workspace" setting, allowing per-command overrides.

## 📅 Revised Timeline
- **Migration Logic**: 1 day
- **Context Commands (use, list)**: 2 days
- **Config & CLI Glue**: 1 day
- **Testing**: 2 days
**Total**: ~1 week (Faster than single-file approach!)
