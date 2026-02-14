# Changelog


## [Unreleased]
### Added

## [0.3.0] - 2026-02-15
### Added
- **Database Optimization**: Normalized database schema (Symbol -> Integer ID).
- **Performance**: Reduced database size by ~86% (18MB -> 2.5MB).

### Changed
- **Repo Reorganization**: Moved core logic to `src/mtfck/` and database to `db/` for a cleaner structure.
- **Dependency**: Upgraded `nse` library to v2.0.0.
- **Refactor**: Updated `mtfck.py`, `ingestion.py`, and `app.py` to support normalized schema and new structure.
- **Fix**: Updated `app.py` to handle breaking changes in `nse` v2.0.0 (list return types).
- **Fix**: Updated `mtfck.py` to use `chClosingPrice` instead of `CH_CLOSING_PRICE` for NSE historical data response handling, and enabled return calculations for "Newly Added MTF Stocks" which were previously commented out. This resolves broken `p2p`, `1y`, and `3yr` return calculations across the dashboard.

### Removed
- `requirements.txt`: Removed in favor of `uv` dependency management.
- Updated `README.md` to use `uv` commands.

## [0.2.0] - 2026-02-04
### Added
- **Automation**: Added GitHub Action for daily database updates at 06:00 IST.
- `ingestion.py`: Dedicated module for database updates and NSE data handling.
- GitHub Actions workflow (`daily_update.yml`) for automated daily database updates.
- `update_to_today()` helper for checking and downloading missing data relative to `date.today()`.

### Changed
- **Refactor**: Extracted database ingestion logic to `ingestion.py`.
- **Refactor**: Cleaned up `mtfck.py` to use `ingestion` module.

## [0.1.1] - 2026-02-03
### Added
- Standardized project structure using `uv`.
- Added `.context` documentation.
- Configured git and `.gitignore`.
### Fixed
- Code style and formatting issues via `ruff`.
