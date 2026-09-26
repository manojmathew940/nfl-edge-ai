"""Registry of approved NFL datasets.

Each dataset keeps its natural grain and is described once here. Ingestion,
cleaning, DuckDB views, SQL validation, and LLM schema guides all read from
this registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Callable

import pandas as pd

from app.data_foundation import plays


RAW_DATA_DIR = Path("data/raw")
PROCESSED_DATA_DIR = Path("data/processed")
NFLVERSE_RELEASE_URL = "https://github.com/nflverse/nflverse-data/releases/download"


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    view_name: str
    source_url_template: str
    raw_filename_template: str
    processed_filename_template: str
    source_columns: tuple[str, ...]
    key_columns: tuple[str, ...]
    schema_path: Path
    min_season: int
    max_download_bytes: int
    derived_columns: tuple[str, ...] = ()
    derive: Callable[[pd.DataFrame], pd.DataFrame] | None = None

    def source_url(self, season: int) -> str:
        return self.source_url_template.format(season=season)

    def raw_path(self, season: int, raw_dir: Path = RAW_DATA_DIR) -> Path:
        return raw_dir / self.raw_filename_template.format(season=season)

    def processed_path(
        self, season: int, processed_dir: Path = PROCESSED_DATA_DIR
    ) -> Path:
        return processed_dir / self.processed_filename_template.format(season=season)

    def processed_file_pattern(self) -> re.Pattern[str]:
        prefix, suffix = self.processed_filename_template.split("{season}")
        return re.compile(rf"^{re.escape(prefix)}(\d{{4}}){re.escape(suffix)}$")


DATASETS: dict[str, DatasetSpec] = {
    "plays": DatasetSpec(
        name="plays",
        view_name="nfl_plays",
        source_url_template=f"{NFLVERSE_RELEASE_URL}/pbp/play_by_play_{{season}}.parquet",
        raw_filename_template="nfl_play_by_play_{season}_raw.parquet",
        processed_filename_template="nfl_plays_{season}.parquet",
        source_columns=tuple(plays.SOURCE_COLUMNS),
        key_columns=("game_id", "play_id"),
        schema_path=Path("docs/nfl_plays_schema.yaml"),
        min_season=1999,
        max_download_bytes=200 * 1024 * 1024,
        derived_columns=tuple(plays.DERIVED_COLUMNS),
        derive=plays.add_derived_fields,
    ),
}


def get_dataset(name: str) -> DatasetSpec:
    try:
        return DATASETS[name]
    except KeyError:
        raise ValueError(
            f"Unknown dataset: {name}. Choose one of: {', '.join(DATASETS)}."
        ) from None


def approved_view_names() -> frozenset[str]:
    return frozenset(spec.view_name for spec in DATASETS.values())


def validate_season(spec: DatasetSpec, season: int) -> None:
    current_year = datetime.now(timezone.utc).year
    if season < spec.min_season or season > current_year:
        raise ValueError(
            f"Season must be between {spec.min_season} and {current_year}; "
            f"got {season}."
        )
