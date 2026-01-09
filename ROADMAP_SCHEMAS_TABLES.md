# Roadmap: Schemas & Multi-Table Support

This document outlines the strategic roadmap for introducing **Schemas** (Namespace Isolation) and **Tables** (Logical Collections) to KyCLI. This enhancement will allow users to manage multiple projects or contexts within the same tool without needing separate database files.

## 🌟 The Vision
Users should be able to switch contexts seamlessly:
```bash
kycli use project_alpha  # Switch everything to 'project_alpha' scope
kys user.name "Alice"    # Saved in project_alpha
kycli use project_beta   # Switch to 'project_beta'
kyg user.name            # Key not found (or returns 'Bob' if set in this scope)
```

## 🗺️ Phases

### Phase 1: Core Architecture Update (Storage Layer) 🏗️
The underlying SQLite schema must be updated to support namespacing without breaking existing data.

- [ ] **Schema Migration**: Add a `scope` (or `table_name`) column to the `kvstore`, `audit_log`, and `archive` tables.
    - Default existing rows to scope=`default`.
- [ ] **Composite Primary Key**: Change Primary Key from `(key)` to `(scope, key)`.
- [ ] **FTS5 Update**: Update `fts_kvstore` triggers to include `scope`.
- [ ] **API Update**: Update `Kycore.save()`, `getkey()`, `delete()`, etc., to accept an optional `scope` argument.

### Phase 2: CLI State Management 🎮
We need a way to persist the "current active scope" between CLI runs.

- [ ] **Config Persistence**: Add a mechanism to write back to `~/.kyclirc` (currently read-only).
- [ ] **New Command: `use`**: Implement `kycli use <scope>` command.
    - Updates the config file with `current_scope = <scope>`.
- [ ] **New Command: `list-scopes`**: Show all available scopes in the DB.
- [ ] **CLI Injection**: Update `main()` to load `current_scope` from config and pass it to `Kycore`.

### Phase 3: Schema Enforcement (Optional Rigidness) 🔒
Allow users to define strict schemas for specific tables/scopes.

- [ ] **Schema Registry**: A new internal table `_schemas` to store validation rules per scope.
    - e.g., `scope='users'` -> `{"name": "str", "age": "int"}`.
- [ ] **Pydantic Integration**: Enhance the existing Pydantic support to load these dynamic schemas at runtime.
- [ ] **Command: `create-table`**: `kycli create table users --schema schema.json`.

### Phase 4: TUI Integration 🖥️
- [ ] **Status Bar**: Show current scope (e.g., `[Scope: project_alpha]`) in the TUI footer.
- [ ] **Live Switching**: Allow typing `use <scope>` strictly inside the interactive shell.

## 🛠️ Detailed Implementation Steps

#### 1. Database Migration (Python/Cython)
Modify `kycli/core/storage.pyx`:
```python
# Pseudo-code for automatic migration
try:
    self._engine._execute_raw("ALTER TABLE kvstore ADD COLUMN scope TEXT DEFAULT 'default'")
    # Note: Changing PK in SQLite requires table re-creation
    # 1. Rename old table
    # 2. Create new table with (scope, key) PK
    # 3. Copy data
except:
    pass # Already exists
```

#### 2. CLI Command (`cli.py`)
```python
elif cmd == "use":
    new_scope = args[0]
    update_config("current_scope", new_scope)
    print(f"Switched to scope: {new_scope}")
```

#### 3. Config Manager (`config.py`)
Add `save_config(key, value)` function to safely update `.kyclirc.json`.

## ⚠️ Breaking Changes & Risks
- **Primary Key Change**: SQLite does not support `ALTER TABLE ADD PRIMARY KEY`. We must perform a "Copy-Table-Swap" migration. This is risky for large datasets.
- **Backward Compatibility**: Older versions of KyCLI accessing the new DB might fail or ignore the scope column (seeing duplicates across scopes).

## 📅 Timeline Estimate
- **Design & prototyping**: 2 days
- **Core Storage Update (Migration logic)**: 3 days
- **CLI & Config features**: 2 days
- **Testing & Validation**: 2 days
**Total**: ~1.5 weeks
