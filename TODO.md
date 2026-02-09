# 📝 Implementation TODO List

This list tracks the progress of implementing high-performance and robust enhancements for KyCLI.

## Phase 1: Test Infrastructure 🧪
- [x] **Setup Testing Environment**
- [x] **Core Functionality Tests** 🎯

## Phase 2: Robustness Implementation 🛡️
- [x] **Input Validation & Sanitization**
- [x] **Error Handling**
- [x] **Safe Deletion Flow**
- [x] **Archiving & Auto-Purge** (15-day policy)
- [x] **Environment Variable Configuration** (`KYCLI_DB_PATH`)

## Phase 3: Advanced Enhancements 🚀
- [x] **Performance Overhaul** (Raw C API)
- [x] **Asynchronous I/O**
- [x] **Accident Recovery (Undo)**
- [x] **Data Intelligence** 🆕
    - [x] Implement structured JSON support.
    - [x] Implement FTS5 Full-Text Search.
    - [x] Integrate Pydantic schema validation.

## Phase 4: Documentation & UX 📚
- [x] **Detailed README Rewrite**
- [x] **Integration Guides** (FastAPI, Classes)
- [x] **New Feature Documentation** (Search, JSON, Pydantic)
- [x] **Performance Reporting**
## Phase 5: Enterprise Security 🔒
- [x] **Encryption at Rest** (AES-256-GCM)
- [x] **Value-Level TTL** (Time To Live)
- [x] **Master Key Management** (CLI flags & Env vars)
- [x] **Point-in-Time Recovery (PITR)**
- [x] **Database Compaction & Maintenance**
- [x] **Atomic Batch Support** (`save_many`)
- [x] **100% Code Coverage Maintenance**
## Phase 6: Maintenance & Refinement ⚙️
- [x] **Modular Refactoring** (Core engines split)
- [ ] **Lock Management**: Retry with exponential backoff for "Database is locked" in multi-process scenarios.
- [ ] **Activity Logs**: Background logging via Python `logging` module.
- [ ] **Atomic Rename Exports**: Write-to-temp-then-rename for export safety.
- [ ] **Compression**: Optional MsgPack/Zstd for large values.

## Phase 8: Roadmap (Planned Features) 🧭
- [ ] **Batch Queue Ops**: `kypush --file` and `kypop --n 100` for throughput.
- [ ] **Delayed Jobs**: `kypush --delay 30s` with scheduled dequeue.
- [ ] **Visibility Timeout**: `kypop --lease 30s` + `kyack`/`kynack` for retry flows.
- [ ] **Workspace TTL Policies**: Default TTL per workspace + `kyttl set/get`.
- [ ] **Interactive CLI Prompts**: Fuzzy key search + history in non-TUI mode.
- [ ] **Config Profiles**: `kyprofile use prod` to switch db path, master key, defaults.
- [ ] **Output Formatting**: `--json` everywhere; `--pretty` for tables.
- [ ] **Key ACLs / Scopes**: Read-only mode, write lock, per-workspace access key.
- [ ] **Audit Export**: `kyaudit export` with time filters.
- [ ] **Stats Command**: `kystats` for size, counts, TTL expirations, queue depth.
- [ ] **Metrics Endpoint**: Optional local HTTP for queue depth + ops/sec.
- [ ] **Namespace/Prefix Views**: `kyws view <prefix>` for large stores.
- [ ] **Backup/Restore**: `kybackup` with encryption and versioned snapshots.
## Phase 7: Community & Branding 🤝
- [x] **Community Guidelines** (COC, Contributing, Security)
- [x] **Issue Templates**
- [x] **Official Branding/Logo**
- [x] **GitHub Repository Cleanup**

---
*Optimized for Performance by Antigravity*
