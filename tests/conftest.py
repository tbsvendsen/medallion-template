"""Shared fixtures for medallion pipeline tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from medallion.pipeline import ENTITIES, PipelineConfig
from medallion.synthetic import generate_raw_api_responses


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate synthetic data once for the entire test session."""
    base = tmp_path_factory.mktemp("pipeline")
    source = base / "source"
    generate_raw_api_responses(source, num_customers=20, num_products=10, num_orders=50)
    return base


@pytest.fixture(scope="session")
def pipeline_config(data_dir: Path) -> PipelineConfig:
    config = PipelineConfig(base_dir=data_dir)
    config.ensure_dirs()
    return config


@pytest.fixture(scope="session")
def entities() -> list[str]:
    return ENTITIES
