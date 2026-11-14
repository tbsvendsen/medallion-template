"""Tests for the pre-bronze API client with retry logic."""

from __future__ import annotations

from pathlib import Path

import pytest

from medallion.pre_bronze import ApiClient, ApiError, fetch_with_retry


class TestApiClient:
    def test_fetch_returns_records(self, data_dir: Path) -> None:
        source = data_dir / "source"
        client = ApiClient(source)
        records = client.fetch("customers")
        assert len(records) > 0
        assert "customer_id" in records[0]

    def test_fetch_nonexistent_entity_raises(self, data_dir: Path) -> None:
        source = data_dir / "source"
        client = ApiClient(source)
        with pytest.raises(FileNotFoundError):
            client.fetch("nonexistent")

    def test_high_failure_rate_raises_api_error(self, data_dir: Path) -> None:
        source = data_dir / "source"
        client = ApiClient(source, failure_rate=1.0, seed=1)
        with pytest.raises(ApiError):
            client.fetch("customers")


class TestRetry:
    def test_succeeds_on_first_try_with_no_failures(self, data_dir: Path) -> None:
        source = data_dir / "source"
        client = ApiClient(source, failure_rate=0.0)
        records = fetch_with_retry(client, "customers", base_delay=0.001)
        assert len(records) > 0
        assert client.call_count == 1

    def test_retries_on_transient_failure(self, data_dir: Path) -> None:
        source = data_dir / "source"
        # 50% failure rate — with retries it should eventually succeed
        client = ApiClient(source, failure_rate=0.5, seed=99)
        records = fetch_with_retry(client, "customers", max_retries=5, base_delay=0.001)
        assert len(records) > 0

    def test_gives_up_after_max_retries(self, data_dir: Path) -> None:
        source = data_dir / "source"
        client = ApiClient(source, failure_rate=1.0, seed=1)
        with pytest.raises(RuntimeError, match="Failed to fetch"):
            fetch_with_retry(client, "customers", max_retries=2, base_delay=0.001)
