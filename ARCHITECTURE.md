# Architecture

## Overview

This pipeline implements a four-layer medallion architecture that transforms synthetic order data into a Kimball dimensional model.

```
API (simulated) → Pre-bronze → Bronze → Silver → Gold
     JSON           JSON       Parquet   Parquet   Parquet
```

## Layers

### Pre-bronze: Ingestion

**Module:** `pre_bronze.py`

Simulates fetching data from an unreliable external API. The `ApiClient` has a configurable failure rate; `fetch_with_retry` wraps it with exponential backoff and jitter to avoid thundering herd.

The raw JSON lands in `data/raw/` — an exact copy of the source, no transformation.

### Bronze: Schema validation

**Module:** `bronze.py`

Converts JSON to Parquet and validates each entity against a predefined schema (`SCHEMAS` dict). Validation checks column presence and type compatibility, allowing numeric promotion (e.g. Int64 where Float64 is expected).

No data transformation happens here. If the schema doesn't match, the pipeline fails fast.

### Silver: Standardization

**Module:** `silver.py`

Per-entity standardizers clean and normalize the data:

- **Customers:** Parse datetime, lowercase emails, deduplicate by customer_id
- **Products:** Lowercase categories, round prices to 2 decimals
- **Orders:** Parse date strings to proper Date type, lowercase status
- **Order lines:** Fill null discounts with 0, deduplicate
- **Deliveries:** Parse date strings

Each standardizer is a function that takes a Polars DataFrame and returns one. The `STANDARDIZERS` dict maps entity names to functions.

### Gold: Dimensional model

**Module:** `gold.py`

Builds a Kimball star schema:

| Table | Type | Grain | Key columns |
|-------|------|-------|-------------|
| `dim_date` | Dimension | One row per calendar day | `date_key` (YYYYMMDD int) |
| `dim_customer` | Dimension (SCD2) | One row per customer version | `customer_sk` (surrogate) |
| `dim_product` | Dimension | One row per product | `product_sk` (surrogate) |
| `fact_order_lines` | Fact | One row per order line | FK to all dimensions |

Surrogate keys are deterministic SHA-256 hashes of the natural key, truncated to fit Int64.

SCD type 2 on `dim_customer` tracks `valid_from`, `valid_to`, and `is_current`. With a single data snapshot this gives one row per customer; the structure supports future incremental loads.

## Data generation

**Module:** `synthetic.py`

Uses Faker with `seed=42` for deterministic, reproducible data. Generates five entities (customers, products, orders, order lines, deliveries) with realistic distributions:

- Customer segments weighted 60/30/10 (retail/wholesale/enterprise)
- Order statuses weighted toward delivered
- Deliveries only created for confirmed/shipped/delivered orders

## Pipeline orchestration

**Module:** `pipeline.py` + `run.py`

`PipelineConfig` is a frozen dataclass that derives all directory paths from a single `base_dir`. The CLI entry point (`python -m medallion.run`) runs all layers in sequence.

All operations are idempotent — rerunning overwrites existing output.

## Design decisions

1. **Polars over Pandas** — Lazy evaluation, no index confusion, better type safety, faster for this workload.
2. **Parquet between layers** — Columnar, typed, compressed. No ambiguity about types across layer boundaries.
3. **No database for storage** — Files are simpler to inspect and version. DuckDB can query the Parquet files directly for ad-hoc analysis.
4. **Deterministic surrogate keys** — SHA-256 hash instead of auto-increment means keys are stable across pipeline runs.
5. **Schema validation at bronze** — Catch structural problems before any transformation. Fail fast.
6. **One standardizer per entity** — Explicit, readable, testable. No generic "clean everything" function.

## Testing

28 tests across three modules:

- `test_synthetic.py` — Data generation: determinism, referential integrity, valid ranges
- `test_pre_bronze.py` — API client: retry logic, failure handling, backoff
- `test_pipeline.py` — End-to-end: each layer produces expected output, gold referential integrity

Tests use a session-scoped fixture that generates a small dataset (20 customers, 10 products, 50 orders) and runs the full pipeline once.

## Dependencies

| Package | Role |
|---------|------|
| Polars | Data processing |
| DuckDB | Available for analytical queries on gold layer |
| Pydantic | Domain models, data validation |
| Faker | Synthetic data generation |

All dependencies are free, open-source, and platform-independent.
