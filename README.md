# medallion-template

A reference implementation of [medallion architecture](https://www.databricks.com/glossary/medallion-architecture) for data pipelines, using synthetic order data.

## What it does

Processes data through four layers:

| Layer | Input | Output | Purpose |
|-------|-------|--------|---------|
| Pre-bronze | API (simulated) | Raw JSON | Ingest with retry, backoff, jitter |
| Bronze | Raw JSON | Parquet | Schema validation, no transformation |
| Silver | Bronze Parquet | Parquet | Standardize types, dedup, null handling |
| Gold | Silver Parquet | Parquet | Kimball dimensional model |

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m medallion.run
```

The pipeline generates synthetic data (customers, products, orders, deliveries) and processes it through all layers. Output lands in `data/`.

## Run tests

```bash
pytest --cov
```

## Tech stack

- **Python** 3.11+
- **Polars** for data processing
- **DuckDB** for analytical queries
- **Pydantic** for data models and validation
- **Faker** for synthetic data generation
- **pytest** for testing

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for design decisions.

## License

MIT
