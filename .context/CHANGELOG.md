# Changelog


## [Unreleased]

### Added
- **Documentation**: Updated `README.md` to be proper and comprehensive, integrating interactive screenshots of main features, trends, and market overlays.
- **Parquet Migration**: Switched storage from monolithic DuckDB files to Apache Parquet format. Reduced storage footprint from 44MB to ~2.6MB (94% reduction) via ZSTD compression and dictionary encoding.
- **One-Click Sync**: Re-engineered the UI to download latest parquet data directly from GitHub, replacing the local-only ingestion button.
- **Improved Industry Filter**: Implemented a "Space Padding" hack in multiselect to hide long hierarchy strings in the dropdown while maintaining full searchability and native browser hover tooltips.
- **Trend Overlays**: Fixed and chunked NSE historical data fetches (90-day windows) to ensure overlapping price charts work for multi-year ranges without truncation.
- **Manual Override**: Added `--from-date` support to the CLI and GitHub Action for manual historical data recovery.

### Changed
- **Dependencies**: Upgraded `nse` to v3.1.0 and migrated API call sites to the new interface:
  - `quote(symbol, section="trade_info")` → `quote(symbol)`: `section` parameter removed; FFMC is now at `tradeInfo.ffmc` (in rupees) instead of `marketDeptOrderBook.tradeInfo.ffmc` (in crores).
  - Historical data key `chClosingPrice` → `CH_CLOSING_PRICE` in `fetch_equity_historical_data` responses.
  - `download_document` now auto-extracts zip files; callers receive an extracted file path instead of a zip path.
- **Architecture**: Completely removed Git submodules and Git LFS. Data is now fetched via standard HTTP streaming from the `MTFDB` repository.
- **Dependencies (prior)**: Upgraded `nse` to `nse[server]>=2.1.0`.
- **Reliability**: Enabled `server=True` in `NSE` initialization to ensure stable HTTP/2 connections in server environments.
- **Database Refactor**: Completely flattened `stock_data` schema. Dropped `stock_master` table and integer IDs to directly store strings (`symbol`), relying on DuckDB's native dictionary encoding for compression.
- **Ingestion**: Stripped out slow API fetches for industry data and complex ID-mapping logic from the CSV ingestion pipeline. Inserts are now practically instantaneous.
- **Runtime Enrichment**: Integrated Just-In-Time (JIT) metadata mapping. Industry data is now fetched at runtime as a JSON file from GitHub and merged in Pandas, removing the need for slow `JOIN`s in analytical SQL queries.
- **Database**: Fixed DuckDB concurrency patchwork. Connections now default to read-only for safe concurrent access by the Streamlit app, while the ingestion CLI requests explicit write access.
- **Cleanup**: Removed the obsolete `migrate_legacy_data` function and LLM thinking trace comments from `ingestion.py`. Docstrings upgraded to professional standards.
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
