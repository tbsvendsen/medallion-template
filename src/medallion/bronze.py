"""Bronze layer: unpack raw JSON to Parquet with schema validation.

No transformation — bronze is a faithful copy of the raw data in a
columnar format. Schema validation ensures the data matches expectations
before downstream layers depend on it.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import polars as pl

logger = logging.getLogger("medallion.bronze")

SCHEMAS: dict[str, dict[str, pl.DataType]] = {
    "customers": {
        "customer_id": pl.String(),
        "name": pl.String(),
        "email": pl.String(),
        "address": pl.String(),
        "city": pl.String(),
        "country": pl.String(),
        "segment": pl.String(),
        "created_at": pl.String(),
    },
    "products": {
        "product_id": pl.String(),
        "name": pl.String(),
        "category": pl.String(),
        "subcategory": pl.String(),
        "unit_price": pl.Float64(),
        "weight_kg": pl.Float64(),
    },
    "orders": {
        "order_id": pl.String(),
        "customer_id": pl.String(),
        "order_date": pl.String(),
        "status": pl.String(),
    },
    "order_lines": {
        "order_id": pl.String(),
        "line_number": pl.Int64(),
        "product_id": pl.String(),
        "quantity": pl.Int64(),
        "unit_price": pl.Float64(),
        "discount_pct": pl.Float64(),
    },
    "deliveries": {
        "delivery_id": pl.String(),
        "order_id": pl.String(),
        "status": pl.String(),
        "shipped_date": pl.String(),
        "delivered_date": pl.String(),
        "tracking_id": pl.String(),
    },
}


class SchemaValidationError(Exception):
    """Raised when bronze data does not match the expected schema."""


def validate_schema(
    df: pl.DataFrame, entity: str, expected: dict[str, pl.DataType]
) -> None:
    """Check that all expected columns exist with compatible types."""
    actual_columns = set(df.columns)
    expected_columns = set(expected.keys())
    missing = expected_columns - actual_columns
    if missing:
        raise SchemaValidationError(f"{entity}: missing columns {sorted(missing)}")

    for col_name, expected_type in expected.items():
        actual_type = df.schema[col_name]
        if not _types_compatible(actual_type, expected_type):
            raise SchemaValidationError(
                f"{entity}.{col_name}: expected {expected_type}, got {actual_type}"
            )


def _types_compatible(actual: pl.DataType, expected: pl.DataType) -> bool:
    if actual == expected:
        return True
    numeric = (pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.Float32, pl.Float64)
    return isinstance(actual, numeric) and isinstance(expected, numeric)


def read_raw_json(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text())  # type: ignore[no-any-return]


def json_to_parquet(
    raw_dir: Path,
    bronze_dir: Path,
    entities: list[str],
) -> dict[str, Path]:
    """Convert raw JSON files to Parquet with schema validation.

    Idempotent: overwrites existing bronze files.
    """
    bronze_dir.mkdir(parents=True, exist_ok=True)
    output_paths: dict[str, Path] = {}

    for entity in entities:
        logger.info("Processing %s: JSON → Parquet", entity)
        raw_path = raw_dir / f"{entity}.json"
        records = read_raw_json(raw_path)
        df = pl.DataFrame(records)

        expected_schema = SCHEMAS.get(entity)
        if expected_schema:
            validate_schema(df, entity, expected_schema)
            logger.info("Schema validation passed for %s", entity)

        output_path = bronze_dir / f"{entity}.parquet"
        df.write_parquet(output_path)
        output_paths[entity] = output_path
        logger.info(
            "Wrote %d rows × %d cols to %s",
            df.height,
            df.width,
            output_path.name,
        )

    return output_paths
