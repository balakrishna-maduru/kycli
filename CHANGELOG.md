# Changelog

## [0.1.7] - 2026-01-06
### Added
- **Encryption at Rest**: Implemented transparent **AES-256-GCM** encryption. All data is encrypted/decrypted in the Cython layer using a user-provided Master Key.
- **Value-Level TTL (Time To Live)**: Keys can now have an expiration time (e.g., `kys session_id "data" --ttl 1h`). Supports human-readable suffixes: `s`, `m`, `h`, `d`, `w`, `M`, `y`.
- **Global --key & --ttl Flags**: Added global CLI support for passing security keys and TTL values.
- **Auto-Purge for TTL**: Expired keys are automatically filtered and purged on startup.
- **Environment Variable Security**: Support for `KYCLI_MASTER_KEY` for seamless encrypted operations.
- **Dependencies**: Added `cryptography` for secure AES operations.

## [0.1.6] - 2026-01-05
### Fixed
- **ModuleNotFoundError Fix**: Fixed critical installation issue where `kycli.kycore` module was not found after pip installation
- **Build System**: Updated setup.py to properly handle Cython compilation with fallback to pre-generated C files
- **Dependencies**: Added missing `install_requires` for prompt-toolkit, rich, and tomli
- **Distribution**: Ensured generated C files are included in source distributions for users without Cython

## [0.1.5] - 2026-01-04
### Added
- **Structured Types (JSON)**: Native support for Python dicts and lists. Values are automatically serialized to JSON on save and deserialized on retrieval.
- **Full-Text Search (FTS5)**: Added `kyf` command and `.search()` method for ultra-fast Google-like searching across the entire store.
- **Pydantic Integration**: Link a Pydantic model to `Kycore` for automatic schema validation on every `save` operation.
- **Environment Variable Configuration**: Set `KYCLI_DB_PATH` to customize the database location dynamically.
- **Execute Mode (kyc)**: Run stored values directly as shell commands, supporting both static and dynamic execution.
- **Interactive TUI Shell (kyshell)**: Multi-pane terminal interface with real-time audit trails and background command execution.
- **Archiving & Auto-Purge**: Deleted keys are now moved to a secure `archive` table with a 15-day auto-purge policy.
- **Safe Deletion**: `kyd` now requires re-entering the key name for confirmation.
- **Accident Recovery**: Added `kyr` (restore) command to magically recover deleted keys from the archive.
- **100% Test Coverage**: Comprehensive test suite covering all edge cases, CLI commands, and TUI interactions.
- **Improved CLI UX**: Detailed help examples (`kyh`), emojis, and micro-animations in the TUI.

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
