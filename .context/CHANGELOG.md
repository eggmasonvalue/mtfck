# Changelog

## [Unreleased]

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
