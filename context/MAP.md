# MAP

## Repository layout

- `app.py` — Streamlit UI entrypoint. Downloads parquet snapshots from `eggmasonvalue/MTFDB`, renders dashboard controls, and drives analytics/trend views.
- `src/mtfck/main.py` — CLI entrypoint (`mtfck update`) for ingestion updates.
- `src/mtfck/ingestion.py` — MTF ingestion pipeline: download NSE daily ZIP, parse summary + scrip rows, merge into in-memory DuckDB tables, export parquet snapshots.
- `src/mtfck/mtfck.py` — Analytics/query layer over DuckDB tables, return calculations, exposure/FFMC lookups, and industry enrichment fetch.
- `src/mtfck/db.py` — Shared in-memory DuckDB connection bootstrap + parquet hydration/export paths.
- `src/mtfck/utils.py` — Generic tenacity retry decorator (`retry_request`) used around plain HTTP request flows.
- `tests/` — unit tests for imports, retry behavior, symbol-merge behavior, and sequence sync expectations.
- `assets/` — README/UI screenshots.
- `data/` — runtime cache for NSE cookies/download artifacts.
- `mtf_data/` (runtime generated, gitignored) — local parquet snapshots used by app/query paths.

## MTF ingestion pipeline

```mermaid
flowchart TD
    A[mtfck update CLI\nmain.py] --> B[update_to_today\ningestion.py]
    B --> C[process_symbol_changes\nplain requests.get + retry_request]
    B --> D[download_and_store_range]
    D --> E[_download_for_date\nNSEClient(...).nse.download_document]
    E --> F[parse_and_insert]
    F --> G[(DuckDB in-memory\nstock_data + daily_summary)]
    G --> H[COPY TO parquet\nmtf_data/*.parquet]
```

## Dashboard query flow

```mermaid
flowchart TD
    U[Streamlit user action] --> A[app.py]
    A --> B[download_database optional sync\nfrom MTFDB raw URLs]
    A --> C[get_connection\ndb.py]
    C --> D[(DuckDB in-memory tables\nloaded from parquet)]
    A --> E[mtfck.py analytics functions]
    E --> D
    E --> F[NSEClient(...).nse for quotes/history]
    E --> G[Industry JSON fetch\nraw GitHub + retry_request]
    A --> H[Tables + Plotly charts]
```
