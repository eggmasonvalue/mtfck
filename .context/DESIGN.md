# Design

## Current Status
- [x] Dashboard UI (Streamlit)
- [x] Parquet Data Lake (MTFDB Repo)
- [x] Automated Daily Pipeline (GitHub Actions)
- [x] Just-In-Time Industry Enrichment
- [x] Multi-line hierarchy hover tooltips
- [x] Chunked NSE Historical Fetching

## Decisions
- **Storage Format**: Switched from DuckDB binary files to **Apache Parquet**. Parquet provides superior compression (reduced repo from 44MB to 2.6MB) and is natively supported by DuckDB for high-speed analytical queries.
- **Stateless Client**: The app no longer manages a persistent local database file via Git. Instead, it downloads the latest "Gold" dataset from GitHub on-demand, ensuring every user sees exactly the same synchronized data.
- **Denormalization**: Removed the `stock_master` normalization. Storing symbols directly as strings in Parquet is actually more efficient due to dictionary encoding and significantly simplifies the ingestion logic.
- **JIT Enrichment**: Industry metadata is kept outside the database in a JSON file. This allows the core data lake to stay extremely lean (just dates and numbers) while the UI handles rich metadata mapping at runtime.
