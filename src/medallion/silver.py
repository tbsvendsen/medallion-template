"""Silver layer: standardize, conform and cleanse bronze data.

Applies consistent types, deduplication, null handling and naming
conventions. Output is ready for cross-source joins and analytics.
"""

from __future__ import annotations

import logging
from pathlib import Path

import polars as pl

logger = logging.getLogger("medallion.silver")


def standardize_customers(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.with_columns(
            pl.col("created_at").str.to_datetime().alias("created_at"),
            pl.col("name").str.strip_chars().alias("name"),
            pl.col("email").str.to_lowercase().str.strip_chars().alias("email"),
            pl.col("city").str.strip_chars().alias("city"),
            pl.col("country").str.strip_chars().alias("country"),
            pl.col("segment").str.to_lowercase().alias("segment"),
        )
        .unique(subset=["customer_id"], keep="last")
        .sort("customer_id")
    )


def standardize_products(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.with_columns(
            pl.col("name").str.strip_chars().alias("name"),
            pl.col("category").str.to_lowercase().str.strip_chars().alias("category"),
            pl.col("subcategory")
            .str.to_lowercase()
            .str.strip_chars()
            .alias("subcategory"),
            pl.col("unit_price").round(2),
            pl.col("weight_kg").round(2),
        )
        .unique(subset=["product_id"], keep="last")
        .sort("product_id")
    )


def standardize_orders(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.with_columns(
            pl.col("order_date").str.to_date().alias("order_date"),
            pl.col("status").str.to_lowercase().alias("status"),
        )
        .unique(subset=["order_id"], keep="last")
        .sort("order_id")
    )


def standardize_order_lines(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.with_columns(
            pl.col("unit_price").round(2),
            pl.col("discount_pct").fill_null(0.0).round(2),
        )
        .unique(subset=["order_id", "line_number"], keep="last")
        .sort("order_id", "line_number")
    )


def standardize_deliveries(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.with_columns(
            pl.col("shipped_date").str.to_date().alias("shipped_date"),
            pl.col("delivered_date").str.to_date().alias("delivered_date"),
            pl.col("status").str.to_lowercase().alias("status"),
        )
        .unique(subset=["delivery_id"], keep="last")
        .sort("delivery_id")
    )


STANDARDIZERS = {
    "customers": standardize_customers,
    "products": standardize_products,
    "orders": standardize_orders,
    "order_lines": standardize_order_lines,
    "deliveries": standardize_deliveries,
}


def bronze_to_silver(
    bronze_dir: Path,
    silver_dir: Path,
    entities: list[str],
) -> dict[str, Path]:
    """Standardize bronze Parquet files to silver.

    Idempotent: overwrites existing silver files.
    """
    silver_dir.mkdir(parents=True, exist_ok=True)
    output_paths: dict[str, Path] = {}

    for entity in entities:
        logger.info("Standardizing %s", entity)
        bronze_path = bronze_dir / f"{entity}.parquet"
        df = pl.read_parquet(bronze_path)

        standardizer = STANDARDIZERS.get(entity)
        if standardizer is None:
            raise ValueError(f"No standardizer defined for {entity}")

        result = standardizer(df)
        rows_removed = df.height - result.height

        output_path = silver_dir / f"{entity}.parquet"
        result.write_parquet(output_path)
        output_paths[entity] = output_path

        logger.info(
            "%s: %d → %d rows (removed %d duplicates), %d columns",
            entity,
            df.height,
            result.height,
            rows_removed,
            result.width,
        )

    return output_paths
