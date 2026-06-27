KyCLI Completion Plan

Goals
- Complete roadmap items in TODO.md with robust error handling and performance-first implementation.
- Maintain or restore 100% test coverage across Python/Cython surfaces.
- Prioritize speed by implementing core data-path logic in Cython where feasible.
- Update documentation and validate_install.sh to cover all corner cases and validation paths.

Non-Goals
- Changing existing CLI commands or breaking current behavior.
- Introducing new runtime dependencies without clear benefit.

Guiding Principles
- Preserve backward compatibility and CLI outputs.
- Prefer Cython for hot paths and heavy validation.
- Fail fast with clear error messages; never silently corrupt data.
- Tests must exercise both success and error paths, including legacy migration flows.

Milestones and Sequence
Milestone A: Maintenance hardening (Phase 6)
- Lock retries, atomic exports, activity logs, compression (MsgPack/Zstd).

Milestone B: Roadmap features (Phase 8)
- Queue/visibility features, TTL policies, output formatting, profiles, ACLs, audit export, stats, metrics, namespace views, backup/restore.

Milestone C: Coverage and validation closure
- Python + Cython coverage at 100% with explicit error-path tests.
- validate_install.sh expanded to include all corner cases.

Phase 1: Roadmap Audit and Baselines
1) Freeze current behavior
- Confirm CLI outputs and error strings for existing commands.
- Snapshot current tests and coverage report for baseline.
- Identify Cython modules for extension: core/storage.pyx, core/query.pyx, core/security.pyx, core/audit.pyx.

2) TODO.md gap analysis
- Map each unchecked item to code locations, doc sections, and test coverage gaps.
- Define acceptance criteria for each item.

Deliverables
- Roadmap matrix: item, owner file(s), required tests, expected output.

Acceptance Criteria
- Baseline CLI outputs recorded for all existing commands.
- Coverage report saved (Python + Cython).
- Roadmap matrix complete and reviewed.

Phase 2: Robustness and Error Handling (Core)
1) Lock Management (exponential backoff)
- Implement retry logic in Cython storage path for SQLITE_BUSY/SQLITE_LOCKED.
- Expose parameters for retries/initial backoff/jitter via config or internal constants.
- Add a safe fallback path when retries are exhausted with explicit error.

2) Activity Logs (Python logging)
- Add structured logging in CLI and TUI for operations, exceptions, and warnings.
- Ensure logging is optional and does not impact hot paths.
- Provide log level control via env var/config.

3) Atomic Rename Exports
- Write exports to temp file then atomic rename (os.replace) on success.
- Ensure temporary files are cleaned on failure.
- Cover JSON/CSV formats with controlled error cases.

4) Compression (MsgPack/Zstd)
- Implement optional value compression for large payloads.
- Store metadata for compression type and size.
- Ensure backward compatibility for uncompressed reads.
- Add guard rails on size thresholds and invalid compressed data.

Deliverables
- Cython changes for lock retry/backoff and compression.
- Python changes for logging and export safety.

Acceptance Criteria
- Lock retry behavior verified with deterministic tests for lock/busy conditions.
- Export uses atomic rename and cleans temp files on error.
- Compression supports enable/disable with compatibility for existing data.
- Logging is optional, configured by env, and does not change CLI output.

Phase 3: Roadmap Features (Planned)
1) Batch Queue Ops
- Add kypush --file (bulk load) and kypop --n N.
- Define consistent output format and error behavior.

2) Delayed Jobs
- Extend queue schema to store delivery timestamp.
- Update pop semantics to ignore future jobs.

3) Visibility Timeout + Ack/Nack
- Add lease columns and tokenization for ack/nack flow.
- Introduce kyack/kynack commands; keep CLI conventions consistent.

4) Workspace TTL Policies
- Add workspace config for default TTL (kyttl set/get).

5) Output Formatting
- Add --json and --pretty options across read/list commands.

6) Config Profiles
- Add kyprofile use <name> with isolated config values.

7) ACLs/Scopes
- Add read-only mode and per-workspace access key.

8) Audit Export
- Filter audit log by time range and export format.

9) Stats Command
- kystats: size, counts, TTL expirations, queue depth.

10) Metrics Endpoint
- Optional local HTTP endpoint for metrics.

11) Namespace/Prefix Views
- kyws view <prefix> with pagination.

12) Backup/Restore
- Encrypted backups, versioned snapshots, and restore command.

Deliverables
- Each feature with code, tests, and docs updates.

Acceptance Criteria
- New commands and flags added without changing existing command behavior.
- All features have tests for success, validation errors, and persistence.
- Queue semantics remain atomic and consistent under concurrency.

Phase 4: Test Coverage to 100%
1) Coverage audit
- Run coverage report and list lines/branches not covered.
- Expand tests for Cython edge cases through Python wrappers.

2) Corner case matrix
- Invalid inputs, I/O failures, busy db, corrupt data, migration conflicts.
- Ensure tests assert exact error messages.

3) CI and local validation
- Add or update tests for platform-specific behaviors.

Deliverables
- Tests for all new and existing error paths.
- Coverage report at 100%.

Acceptance Criteria
- Python + Cython line coverage at 100%.
- No flaky tests and no skipped tests for critical paths.

Phase 5: Documentation and Validation Script
1) Documentation updates
- README: new commands, flags, and behavior.
- docs/*: detailed guides for queues, security, recovery, and performance.

2) validate_install.sh expansion
- Add corner case validations for new features.
- Include legacy migration, wrong key handling, corrupted export detection.
- Ensure deterministic outputs and clear failure signals.

Deliverables
- Updated docs and validation script with edge coverage.

Acceptance Criteria
- Docs match CLI behavior and output.
- validate_install.sh covers all new flags and negative cases.

Execution Order Recommendation
1) Lock Management and Export Safety
2) Compression
3) Queue/Visibility features
4) Remaining roadmap features
5) Tests and docs updates interleaved after each feature

Acceptance Criteria
- All TODO roadmap items implemented or formally deferred with rationale.
- 100% test coverage achieved with no flaky tests.
- validate_install.sh exercises full command matrix including edge cases.
- Documentation matches behavior and CLI output.

Execution Checklist
- Implement Phase 6 changes first to stabilize core behavior.
- Implement Phase 8 features in priority order: queue/visibility, TTL policies, output formatting, profiles, ACLs, audit export, stats, metrics, namespace views, backup/restore.
- After each feature: add tests, update docs, and add validation script cases.
