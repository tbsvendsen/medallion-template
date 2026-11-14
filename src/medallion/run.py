"""Run the full medallion pipeline end to end."""

from __future__ import annotations

import argparse
from pathlib import Path

from medallion.bronze import json_to_parquet
from medallion.gold import silver_to_gold
from medallion.pipeline import ENTITIES, PipelineConfig, setup_logging
from medallion.silver import bronze_to_silver
from medallion.synthetic import generate_raw_api_responses


def run_pipeline(
    data_dir: Path,
    num_customers: int = 200,
    num_products: int = 50,
    num_orders: int = 1000,
) -> None:
    """Execute the complete pipeline: generate → raw → bronze → silver → gold."""
    config = PipelineConfig(base_dir=data_dir)
    config.ensure_dirs()

    setup_logging()

    print("=== Generating synthetic data ===")
    source_dir = data_dir / "source"
    generate_raw_api_responses(
        source_dir,
        num_customers=num_customers,
        num_products=num_products,
        num_orders=num_orders,
    )

    print("\n=== Pre-bronze → Raw ===")
    from medallion.pre_bronze import ingest_to_raw

    ingest_to_raw(source_dir, config.raw_dir, ENTITIES)

    print("\n=== Bronze: JSON → Parquet ===")
    json_to_parquet(config.raw_dir, config.bronze_dir, ENTITIES)

    print("\n=== Silver: Standardize ===")
    bronze_to_silver(config.bronze_dir, config.silver_dir, ENTITIES)

    print("\n=== Gold: Dimensional model ===")
    gold_paths = silver_to_gold(config.silver_dir, config.gold_dir)

    print(f"\nPipeline complete. Output in {data_dir}")
    print(f"Gold tables: {', '.join(gold_paths.keys())}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the medallion architecture pipeline"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Base directory for pipeline data (default: data/)",
    )
    parser.add_argument("--customers", type=int, default=200)
    parser.add_argument("--products", type=int, default=50)
    parser.add_argument("--orders", type=int, default=1000)
    args = parser.parse_args()

    run_pipeline(
        args.data_dir,
        num_customers=args.customers,
        num_products=args.products,
        num_orders=args.orders,
    )


if __name__ == "__main__":
    main()
