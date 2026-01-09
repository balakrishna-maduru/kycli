# 📦 Data Management: Import, Export & Backups

`kycli` provides robust tools for moving data in and out of your workspaces.

## Scope Warning ⚠️
All Data Management commands operate strictly on the **Active Workspace**.
To export data from "Project A", you must first `kyuse project_a`.

## Export (`kye`)

Export the entire active store to a file.
Supported Formats:
- **CSV** (Default): best for spreadsheets and simple analysis.
- **JSON**: best for programmatic backup and complex nested structures.

```bash
# Export to CSV
kye backup_2026.csv

# Export to JSON
kye data_dump.json json
```

### Encrypted Exports
If your data is encrypted at rest, `kye` will decrypt it before exporting. The resulting file will be **Plaintext**. Ensure you store your exports securely.

## Import (`kyi`)

Bullk import data from a CSV or JSON file into the **Active Workspace**.
- **Upsert Behavior**: If a key in the file already exists in the database, it will be **Overwritten**.
- **New Keys**: Standard creation.

```bash
# Import from a backup
kyuse project_alpha
kyi old_backup.json
```

## Archive Strategy
`kycli` uses a "Soft Delete" strategy.
- When you `kyd` (Delete) or `kypatch` (Update), the *old* version is moved to a hidden `archive` table.
- This archive is local to the `.db` file.
- Archives are automatically purged after **15 days** by default (customizable via `kyco`).
