# DECISIONS

## 2026-06-22 — Construct NSE access through exchange-access client wrapper

Context: NSE integration points existed in app-local modules and needed consolidation on the shared `exchange-access` abstraction.
Decision: `src/mtfck/ingestion.py` and `src/mtfck/mtfck.py` each construct NSE access via `NSEClient(str(DATA_DIR), server=True).nse`, and no direct `nse.NSE(...)` constructor is kept in this repo.
Tradeoff: This adds a cross-repo dependency and version coordination burden, but centralizes NSE session/bootstrap behavior on the shared client path used across constellation repos.
Status: active

## 2026-06-22 — Keep app-local generic requests retry decorator and tenacity dependency

Context: After routing NSE construction through `exchange-access`, this repo still has plain `requests.get` fetches for non-client HTTP calls (for example symbol-change CSV and industry JSON).
Decision: Keep `src/mtfck/utils.py:retry_request` (tenacity, retries on broad `RequestException`/`ConnectionError`/`TimeoutError`, reraises final failure) and retain direct `tenacity` dependency instead of replacing it with exchange-access retry behavior.
Tradeoff: Retry behavior is split between shared-client internals and app-local wrappers, but preserves distinct semantics for generic HTTP scrape paths that are not status-predicate retries from the shared client.
Status: active

## 2026-06-22 — Use parquet snapshots as system-of-record for app runtime

Context: The project needs lightweight distribution of historical MTF datasets to local dashboards without maintaining a mutable checked-in DB file.
Decision: Hydrate in-memory DuckDB tables from `mtf_data/*.parquet`, run all queries against in-memory tables, and export updated tables back to parquet in ingestion.
Tradeoff: Full-table parquet rewrite on export is simpler and portable but can be heavier than incremental DB-file mutation.
Status: active
