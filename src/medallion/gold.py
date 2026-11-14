"""Gold layer: Kimball dimensional model.

Builds fact and dimension tables from silver data:
- dim_customer: SCD type 2 aware customer dimension
- dim_product: product dimension with category hierarchy
- dim_date: date dimension
- fact_order_lines: grain = one order line, with surrogate keys
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date, timedelta
from pathlib import Path

import polars as pl

logger = logging.getLogger("medallion.gold")


def build_dim_date(
    start_date: date = date(2023, 1, 1),
    end_date: date = date(2026, 12, 31),
) -> pl.DataFrame:
    """Generate a date dimension covering the pipeline's date range."""
    days = (end_date - start_date).days + 1
    dates = [start_date + timedelta(days=i) for i in range(days)]

    return pl.DataFrame(
        {
            "date_key": [int(d.strftime("%Y%m%d")) for d in dates],
            "full_date": dates,
            "year": [d.year for d in dates],
            "quarter": [(d.month - 1) // 3 + 1 for d in dates],
            "month": [d.month for d in dates],
            "month_name": [d.strftime("%B") for d in dates],
            "week": [d.isocalendar()[1] for d in dates],
            "day_of_week": [d.isoweekday() for d in dates],
            "day_name": [d.strftime("%A") for d in dates],
            "is_weekend": [d.isoweekday() >= 6 for d in dates],
        }
    )


def _surrogate_key(natural_key: str) -> int:
    """Deterministic surrogate key from natural key."""
    return int(hashlib.sha256(natural_key.encode()).hexdigest()[:12], 16)


def build_dim_customer(silver_dir: Path) -> pl.DataFrame:
    """Build customer dimension with SCD type 2 columns."""
    customers = pl.read_parquet(silver_dir / "customers.parquet")

    return customers.with_columns(
        pl.col("customer_id")
        .map_elements(_surrogate_key, return_dtype=pl.Int64)
        .alias("customer_sk"),
        pl.lit(True).alias("is_current"),
        pl.col("created_at").cast(pl.Date).alias("valid_from"),
        pl.lit(date(9999, 12, 31)).alias("valid_to"),
    ).select(
        "customer_sk",
        "customer_id",
        "name",
        "email",
        "city",
        "country",
        "segment",
        "is_current",
        "valid_from",
        "valid_to",
    )


def build_dim_product(silver_dir: Path) -> pl.DataFrame:
    """Build product dimension with category hierarchy."""
    products = pl.read_parquet(silver_dir / "products.parquet")

    return products.with_columns(
        pl.col("product_id")
        .map_elements(_surrogate_key, return_dtype=pl.Int64)
        .alias("product_sk"),
    ).select(
        "product_sk",
        "product_id",
        "name",
        "category",
        "subcategory",
        "unit_price",
        "weight_kg",
    )


def build_fact_order_lines(
    silver_dir: Path,
    dim_customer: pl.DataFrame,
    dim_product: pl.DataFrame,
) -> pl.DataFrame:
    """Build fact table at order line grain with surrogate keys."""
    orders = pl.read_parquet(silver_dir / "orders.parquet")
    order_lines = pl.read_parquet(silver_dir / "order_lines.parquet")
    deliveries = pl.read_parquet(silver_dir / "deliveries.parquet")

    customer_lookup = dim_customer.filter(pl.col("is_current")).select(
        "customer_id", "customer_sk"
    )
    product_lookup = dim_product.select("product_id", "product_sk")

    fact = (
        order_lines.join(orders, on="order_id", how="left")
        .join(
            deliveries.select("order_id", "delivered_date"),
            on="order_id",
            how="left",
        )
        .join(customer_lookup, on="customer_id", how="left")
        .join(product_lookup, on="product_id", how="left")
        .with_columns(
            (
                pl.col("quantity")
                * pl.col("unit_price")
                * (1 - pl.col("discount_pct") / 100)
            )
            .round(2)
            .alias("line_amount"),
            pl.col("order_date")
            .cast(pl.Utf8)
            .str.replace_all("-", "")
            .cast(pl.Int32)
            .alias("order_date_key"),
        )
        .select(
            "order_id",
            "line_number",
            "customer_sk",
            "product_sk",
            "order_date_key",
            "quantity",
            pl.col("unit_price").alias("unit_price_at_sale"),
            "discount_pct",
            "line_amount",
            "status",
            "delivered_date",
        )
        .sort("order_id", "line_number")
    )

    return fact


def silver_to_gold(silver_dir: Path, gold_dir: Path) -> dict[str, Path]:
    """Build dimensional model from silver layer.

    Idempotent: overwrites existing gold files.
    """
    gold_dir.mkdir(parents=True, exist_ok=True)
    output_paths: dict[str, Path] = {}

    logger.info("Building dim_date")
    dim_date = build_dim_date()
    path = gold_dir / "dim_date.parquet"
    dim_date.write_parquet(path)
    output_paths["dim_date"] = path

    logger.info("Building dim_customer")
    dim_customer = build_dim_customer(silver_dir)
    path = gold_dir / "dim_customer.parquet"
    dim_customer.write_parquet(path)
    output_paths["dim_customer"] = path

    logger.info("Building dim_product")
    dim_product = build_dim_product(silver_dir)
    path = gold_dir / "dim_product.parquet"
    dim_product.write_parquet(path)
    output_paths["dim_product"] = path

    logger.info("Building fact_order_lines")
    fact = build_fact_order_lines(silver_dir, dim_customer, dim_product)
    path = gold_dir / "fact_order_lines.parquet"
    fact.write_parquet(path)
    output_paths["fact_order_lines"] = path

    for name, p in output_paths.items():
        df = pl.read_parquet(p)
        logger.info("%s: %d rows × %d cols", name, df.height, df.width)

    return output_paths
