# Roadmap: Advanced Workspaces & UX

This document outlines the plan for refining the user experience of Multi-Tenancy (Workspaces), focusing on visibility, data segregation (Import/Export/Archive), and consistency.

## 1. TUI Improvements (`kyshell`)
**Goal**: The user should always know exactly which database they are operating on.

### 1.1 Status Bar / Header
- **Current**: The "Audit Trail" pane title changes to `Audit Trail [workspace]`. This is subtle and easily missed.
- **Proposed**: Add a dedicated **Status Bar** at the bottom of the TUI.
    - **Left**: `User: <system_user>`
    - **Center**: `Workspace: <active_workspace>` (Color-coded if possible: Blue=Default, Magenta=Custom)
    - **Right**: `DB: <filename>.db`

### 1.2 "Magic" Prompt
- Change the input prompt from `kycli> ` to `kycli(<workspace>)> ` (e.g., `kycli(prod)> `).

## 2. Documentation Segregation
**Goal**: Split the monolithic README into clear, task-oriented guides.

- **`docs/WORKSPACES.md`**: Guide on creating `kyuse`, switching, and moving data `kymv`.
- **`docs/EXPORT_IMPORT.md`**: Detailed guide on backing up data, formats (CSV/JSON), and scope.
- **`docs/RECOVERY.md`**: Deep dive into `kyr` (restore single key), `kyrt` (Point-in-Time Recovery), and `kyco` (Compaction).

## 3. Advanced Features Logic in Multi-Tenancy

### 3.1 Scope of Operations
Crucial Logic: **All commands operate ONLY on the Active Workspace.**

| Feature | Scope | Logic |
| :--- | :--- | :--- |
| **Save/Get** (`kys`/`kyg`) | **Active DB** | Reads/Writes to `~/.kycli/data/<active>.db`. Keys in other DBs are invisible. |
| **Search** (`kyg -s`) | **Active DB** | FTS5 index is local to the `.db` file. You only search the current context. |
| **Export** (`kye`) | **Active DB** | Exports keys/values from the current workspace ONLY. Does NOT create a "mega backup" of all workspaces. |
| **Import** (`kyi`) | **Active DB** | Imports data INTO the current workspace. |
| **Restore** (`kyr`) | **Active DB** | Restores a key from the `archive` table inside the current `.db` file. You cannot restore a key that was deleted in a *different* workspace. |
| **PITR** (`kyrt`) | **Active DB** | Replays the `history` table of the current `.db` file. Restores the state of *this specific project* to a past time. |
| **Compact** (`kyco`) | **Active DB** | Vacuums/analyzes only the current `.db` file. |

### 3.2 Cross-Workspace Interactions
- **Move** (`kymv`): The *only* command that touches two databases (Source -> Target). 
    - **Logic**: Transactionally reads from Source, Writes to Target, Deletes from Source.

### 3.3 Scenarios & FAQs

**Q: How do I backup EVERYTHING?**
- **Current**: You must `kyuse` each workspace and `kye`.
- **Proposed Feature**: `kycli export-all`? (Out of scope for now, but logical next step).

**Q: If I `kyrt` (Time Travel) in 'Project A', does it affect 'Default'?**
- **A**: No. The databases are physically separate files. Time travel is isolated.

**Q: What if I move a key to a workspace, then restore it in the old workspace?**
- **A**: The old workspace treats the move as a "Delete". If you `kyr` it in the old workspace, it comes back (duplicate). This is standard "Soft Delete" behavior.

## 4. Implementation Plan

1.  **Phase 1: TUI Visualization**
    - Update `tui.py` to include a `VSplit` or `HSplit` footer with status info.
    - Update prompt text dynamically in `handle_command`.

2.  **Phase 2: Documentation Refactor**
    - Extract sections from `README.md` into `docs/` folder.
    - Rewrite `README.md` as a high-level index.

3.  **Phase 3: Validation**
    - Verify that `kye` and `kyi` respect the boundaries strictly. (Tests already cover isolation, but manual verification of export content helps).
