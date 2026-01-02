# Changelog

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
