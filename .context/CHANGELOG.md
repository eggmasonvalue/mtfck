# Changelog


## [Unreleased]

### Changed
- **Database**: Migrated backend storage from SQLite (`stock_data.db`) to DuckDB (`stock_data.duckdb`) for ~10-20x storage efficiency gains using columnar compression.
- **Dependencies**: Added `duckdb` (v1.2.0+).
- **Ingestion**: Refactored `ingestion.py` to use DuckDB's native SQL engine for faster bulk inserts.
- **Schema**: Updated `schema.sql` to use DuckDB-compatible `SEQUENCE` for auto-incrementing IDs.
- **Fix**: Replaced legacy `sqlite3` usage in `app.py` with DuckDB shared connection.
- **Fix**: Updated `get_available_dates` to handle DuckDB/Pandas timestamps correctly, fixing `ValueError`.
- **Migration**: Added auto-migration in `app.py` to import legacy SQLite data if DuckDB is essentially empty (preserves history).
- **Concurrency**: Implemented `db.py` singleton to allow Streamlit app to handle ingestion and querying simultaneously without file locking errors.

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
