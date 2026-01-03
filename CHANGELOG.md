# Changelog

## [0.2.0] - 2026-01-03
### Added
- **Structured Types (JSON)**: Native support for Python dicts and lists. Values are automatically serialized to JSON on save and deserialized on retrieval.
- **Full-Text Search (FTS5)**: Added `kyf` command and `.search()` method for ultra-fast Google-like searching across the entire store.
- **Pydantic Integration**: Link a Pydantic model to `Kycore` for automatic schema validation on every `save` operation.
- **Improved CLI**: Enhanced `kys` and `kyg` to handle JSON strings and pretty-print complex outputs.

## [0.1.7] - 2026-01-03
### Added
- **Archiving & Auto-Purge**: Deleted keys are now moved to a secure `archive` table instead of being immediately wiped.
- **15-Day Data Retention**: Implemented a 15-day auto-purge policy. Archived keys are kept for 15 days, allowing for recovery via the `kyr` command before permanent deletion.

## [0.1.6] - 2026-01-03
### Added
- **Safe Deletion**: `kyd` now requires re-entering the key name for confirmation.
- **Accident Recovery**: Added `kyr` (restore) command to magically recover deleted keys from the audit history.
- **Improved CLI UX**: Added helpful tips and clearer confirmation prompts for destructive operations.

## [0.1.5] - 2026-01-03
### Added
- **Detailed Documentation**: Complete rewrite of `README.md` with deep-dive CLI examples, performance benchmarks, and architecture details.
- **Integration Guides**: Added step-by-step guides for class-based usage and FastAPI integration.
- **Restored Interface**: Re-implemented Pythonic dictionary methods (`__getitem__`, etc.) in the new direct C API core.

## [0.1.4] - 2026-01-03
### Added
- **Integration Documentation**: Added detailed examples for using `Kycore` in custom classes and FastAPI applications.

## [0.1.3] - 2026-01-03
### Changed
- **Metadata Update**: Refreshed README and PyPI documentation to accurately reflect Raw C API optimizations (direct `libsqlite3` binding).
- **Documentation**: Added Async API usage examples and performance comparison table.

## [0.1.2] - 2026-01-03
### Added
- **C-Level Core**: Replaced Python `sqlite3` with direct C API calls for 150x faster retrieval.
- **Async Support**: Added non-blocking `save_async` and `getkey_async` for high-throughput app integration.
- **Performance Suite**: Integrated a new benchmark script and performance reporting.
- **Improved Typing**: Enhanced Cython type definitions for critical paths.

### Fixed
- Fixed a validation bug in `save()` where empty strings were incorrectly allowed.

## [0.1.1] - 2026-01-02
### Fixed
- Fixed PyPI upload issue caused by filename reuse.

## [0.1.0] - 2026-01-02
### Added
- **Library API**: Enhanced `Kycore` with a Pythonic dictionary-like interface (`core['key'] = 'value'`).
- **Context Manager**: Added support for `with Kycore() as core:` for safe database operations.
- **Top-level Export**: `Kycore` is now importable directly from `kycli`.
- **Improved Metadata**: Added `__len__`, `__contains__`, and `__iter__` to `Kycore`.
- **API Documentation**: Added comprehensive docstrings for library usage.

## [0.0.5] - 2026-01-02
### Changed
- Improved PyPI project page with full README documentation.
- Included test suite in the source distribution.

## [0.0.4] - 2026-01-02
### Added
- **Audit Logging**: Full history of key-value changes (accessible via `kyv`).
- **Overwrite Protection**: Interactive (Y/N) confirmation before modifying existing keys.
- **Atomic Operations**: Safer exports using a temp-and-rename strategy.
- **Robustness**: Integrated input validation and database lock retry logic.
- **Testing**: A full 21-case test suite ensuring stability.
- **Enhanced CLI**: Improved emojis and status messages for better UX.

## [0.0.3] - 2025-06-07
- Add kyc - execute command support

## [0.0.2] - 2025-05-25
- Commit the version replace change
