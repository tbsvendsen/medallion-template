"""Pipeline configuration and shared utilities."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("medallion")

ENTITIES = ["customers", "products", "orders", "order_lines", "deliveries"]


@dataclass(frozen=True)
class PipelineConfig:
    """Paths for each layer of the medallion architecture."""

    base_dir: Path
    raw_dir: Path = field(init=False)
    bronze_dir: Path = field(init=False)
    silver_dir: Path = field(init=False)
    gold_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw_dir", self.base_dir / "raw")
        object.__setattr__(self, "bronze_dir", self.base_dir / "bronze")
        object.__setattr__(self, "silver_dir", self.base_dir / "silver")
        object.__setattr__(self, "gold_dir", self.base_dir / "gold")

    def ensure_dirs(self) -> None:
        for d in (self.raw_dir, self.bronze_dir, self.silver_dir, self.gold_dir):
            d.mkdir(parents=True, exist_ok=True)


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
