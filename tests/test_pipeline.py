"""End-to-end pipeline tests: pre-bronze through gold."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from medallion.bronze import json_to_parquet
from medallion.gold import silver_to_gold
from medallion.pipeline import PipelineConfig
from medallion.pre_bronze import ingest_raw_copy
from medallion.silver import bronze_to_silver


class TestPreBronze:
    def test_ingest_copies_all_entities(
        self, data_dir: Path, pipeline_config: PipelineConfig, entities: list[str]
    ) -> None:
        source = data_dir / "source"
        paths = ingest_raw_copy(source, pipeline_config.raw_dir, entities)
        assert set(paths.keys()) == set(entities)
        for path in paths.values():
            assert path.exists()
            assert path.suffix == ".json"


class TestBronze:
    def test_json_to_parquet_creates_all_files(
        self, pipeline_config: PipelineConfig, entities: list[str]
    ) -> None:
        # Ensure raw data exists
        source = pipeline_config.base_dir / "source"
        ingest_raw_copy(source, pipeline_config.raw_dir, entities)

        paths = json_to_parquet(
            pipeline_config.raw_dir, pipeline_config.bronze_dir, entities
        )
        assert set(paths.keys()) == set(entities)
        for path in paths.values():
            assert path.exists()
            assert path.suffix == ".parquet"

    def test_bronze_preserves_row_count(self, pipeline_config: PipelineConfig) -> None:
        import json

        for entity in ["customers", "products"]:
            raw = json.loads((pipeline_config.raw_dir / f"{entity}.json").read_text())
            bronze = pl.read_parquet(pipeline_config.bronze_dir / f"{entity}.parquet")
            assert bronze.height == len(raw)


class TestSilver:
    def test_standardize_all_entities(
        self, pipeline_config: PipelineConfig, entities: list[str]
    ) -> None:
        paths = bronze_to_silver(
            pipeline_config.bronze_dir, pipeline_config.silver_dir, entities
        )
        assert set(paths.keys()) == set(entities)

    def test_customers_email_is_lowercase(
        self, pipeline_config: PipelineConfig
    ) -> None:
        df = pl.read_parquet(pipeline_config.silver_dir / "customers.parquet")
        emails = df["email"].to_list()
        assert all(e == e.lower() for e in emails)

    def test_customers_are_deduplicated(self, pipeline_config: PipelineConfig) -> None:
        df = pl.read_parquet(pipeline_config.silver_dir / "customers.parquet")
        assert df["customer_id"].n_unique() == df.height

    def test_orders_have_date_type(self, pipeline_config: PipelineConfig) -> None:
        df = pl.read_parquet(pipeline_config.silver_dir / "orders.parquet")
        assert df["order_date"].dtype == pl.Date

    def test_order_lines_discount_not_null(
        self, pipeline_config: PipelineConfig
    ) -> None:
        df = pl.read_parquet(pipeline_config.silver_dir / "order_lines.parquet")
        assert df["discount_pct"].null_count() == 0


class TestGold:
    def test_builds_all_dimensional_tables(
        self, pipeline_config: PipelineConfig
    ) -> None:
        paths = silver_to_gold(pipeline_config.silver_dir, pipeline_config.gold_dir)
        expected = {"dim_date", "dim_customer", "dim_product", "fact_order_lines"}
        assert set(paths.keys()) == expected

    def test_dim_date_covers_expected_range(
        self, pipeline_config: PipelineConfig
    ) -> None:
        df = pl.read_parquet(pipeline_config.gold_dir / "dim_date.parquet")
        assert df.height > 365
        assert "year" in df.columns
        assert "quarter" in df.columns
        assert "is_weekend" in df.columns

    def test_dim_customer_has_scd2_columns(
        self, pipeline_config: PipelineConfig
    ) -> None:
        df = pl.read_parquet(pipeline_config.gold_dir / "dim_customer.parquet")
        assert "customer_sk" in df.columns
        assert "is_current" in df.columns
        assert "valid_from" in df.columns
        assert "valid_to" in df.columns

    def test_fact_has_surrogate_keys(self, pipeline_config: PipelineConfig) -> None:
        df = pl.read_parquet(pipeline_config.gold_dir / "fact_order_lines.parquet")
        assert "customer_sk" in df.columns
        assert "product_sk" in df.columns
        assert "order_date_key" in df.columns
        assert "line_amount" in df.columns

    def test_fact_line_amount_is_positive(
        self, pipeline_config: PipelineConfig
    ) -> None:
        df = pl.read_parquet(pipeline_config.gold_dir / "fact_order_lines.parquet")
        assert (df["line_amount"] >= 0).all()

    def test_fact_references_valid_customers(
        self, pipeline_config: PipelineConfig
    ) -> None:
        fact = pl.read_parquet(pipeline_config.gold_dir / "fact_order_lines.parquet")
        dim = pl.read_parquet(pipeline_config.gold_dir / "dim_customer.parquet")
        valid_sks = set(dim["customer_sk"].to_list())
        fact_sks = set(fact["customer_sk"].drop_nulls().to_list())
        assert fact_sks <= valid_sks

    def test_fact_references_valid_products(
        self, pipeline_config: PipelineConfig
    ) -> None:
        fact = pl.read_parquet(pipeline_config.gold_dir / "fact_order_lines.parquet")
        dim = pl.read_parquet(pipeline_config.gold_dir / "dim_product.parquet")
        valid_sks = set(dim["product_sk"].to_list())
        fact_sks = set(fact["product_sk"].drop_nulls().to_list())
        assert fact_sks <= valid_sks
