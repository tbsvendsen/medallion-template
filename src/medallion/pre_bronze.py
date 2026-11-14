"""Pre-bronze layer: ingest raw data from API with retry and rate limiting.

In a production pipeline this layer calls external APIs. Here we simulate
the API by reading from generated JSON files, applying the same retry and
rate-limiting patterns a real client would use.
"""

from __future__ import annotations

import json
import logging
import random
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("medallion.pre_bronze")

MAX_RETRIES = 3
BASE_DELAY_SECONDS = 0.1
JITTER_MAX = 0.05
TIMEOUT_SECONDS = 30.0


class ApiError(Exception):
    """Simulated transient API error."""


class ApiClient:
    """Simulated API client with retry, backoff and jitter."""

    def __init__(
        self,
        source_dir: Path,
        failure_rate: float = 0.0,
        seed: int = 42,
    ) -> None:
        self._source_dir = source_dir
        self._failure_rate = failure_rate
        self._rng = random.Random(seed)
        self._call_count = 0

    def fetch(self, entity: str) -> list[dict[str, Any]]:
        """Fetch an entity's records, simulating network conditions."""
        self._call_count += 1

        if self._rng.random() < self._failure_rate:
            raise ApiError(f"Transient error fetching {entity}")

        path = self._source_dir / f"{entity}.json"
        if not path.exists():
            raise FileNotFoundError(f"No source data for {entity}: {path}")

        return json.loads(path.read_text())  # type: ignore[no-any-return]

    @property
    def call_count(self) -> int:
        return self._call_count


def fetch_with_retry(
    client: ApiClient,
    entity: str,
    max_retries: int = MAX_RETRIES,
    base_delay: float = BASE_DELAY_SECONDS,
) -> list[dict[str, Any]]:
    """Fetch with exponential backoff and jitter."""
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return client.fetch(entity)
        except ApiError as exc:
            last_error = exc
            if attempt < max_retries:
                delay = base_delay * (2**attempt) + random.uniform(0, JITTER_MAX)
                logger.warning(
                    "Attempt %d/%d for %s failed: %s. Retrying in %.3fs",
                    attempt + 1,
                    max_retries + 1,
                    entity,
                    exc,
                    delay,
                )
                time.sleep(delay)

    raise RuntimeError(
        f"Failed to fetch {entity} after {max_retries + 1} attempts"
    ) from last_error


def ingest_to_raw(
    source_dir: Path,
    raw_dir: Path,
    entities: list[str],
    failure_rate: float = 0.0,
) -> dict[str, Path]:
    """Ingest entities from simulated API to raw JSON files.

    Idempotent: overwrites existing raw files with fresh data.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    client = ApiClient(source_dir, failure_rate=failure_rate)
    output_paths: dict[str, Path] = {}

    for entity in entities:
        logger.info("Ingesting %s from API", entity)
        records = fetch_with_retry(client, entity)
        output_path = raw_dir / f"{entity}.json"
        output_path.write_text(json.dumps(records, indent=2, default=str))
        output_paths[entity] = output_path
        logger.info("Wrote %d records to %s", len(records), output_path.name)

    return output_paths


