# CONVENTIONS

- Work on a branch; never commit directly to `main`.
- Install/update dependencies with `uv sync`.
- Run lint with `uv run ruff check .` before opening a PR.
- Run tests with `uv run pytest -q` before opening a PR.
- Lint docs with `npx --yes markdownlint-cli2 AGENTS.md README.md "context/**/*.md"` before opening a PR.
- Keep NSE client construction in app modules via `NSEClient(...).nse`.
- Wrap plain `requests` network calls with `retry_request()`.
- Use `get_connection()` from `src/mtfck/db.py` for SQL access; do not open ad-hoc DuckDB connections in feature code.
