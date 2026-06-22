# MTFCK

MTFCK is a Streamlit dashboard and ingestion CLI for analyzing NSE Margin Trading Facility (MTF) data.

## What it does

- Tracks MTF financing data over time from NSE archive disclosures.
- Stores local snapshots as parquet (`mtf_data/stock_data.parquet`, `mtf_data/daily_summary.parquet`).
- Loads parquet into in-memory DuckDB for analytical queries.
- Renders interactive dashboard views for top financed stocks, exposure, newly-added names, and trend overlays.

## Run locally

```bash
uv sync
uv run streamlit run app.py
```

## CLI ingestion update

```bash
uv run mtfck update
# optional manual backfill start
uv run mtfck update --from-date 2026-01-01
```

## Tests and lint

```bash
uv run ruff check .
uv run pytest -q
npx --yes markdownlint-cli2 AGENTS.md README.md "context/**/*.md"
```

## Project map

- `app.py` — Streamlit dashboard UI and cloud-sync action.
- `src/mtfck/main.py` — CLI entrypoint.
- `src/mtfck/ingestion.py` — NSE ingest + parquet export pipeline.
- `src/mtfck/mtfck.py` — analytics/query functions and NSE lookups.
- `src/mtfck/db.py` — in-memory DuckDB bootstrap from parquet.
- `src/mtfck/utils.py` — retry decorator for plain HTTP requests.
- `context/` — durable agent-maintained structure/tradeoff/rule docs.
