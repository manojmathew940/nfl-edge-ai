"""Registry of approved NFL datasets.

Each dataset keeps its natural grain and is described once here. Its schema
YAML (in schemas/) is the single source for its columns, types, and the
descriptions the SQL LLM sees. Ingestion, cleaning, DuckDB views, SQL
validation, and LLM schema guides all read from this registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Callable

import pandas as pd
import yaml

from app.data_foundation import plays


RAW_DATA_DIR = Path("data/raw")
PROCESSED_DATA_DIR = Path("data/processed")
NFLVERSE_RELEASE_URL = "https://github.com/nflverse/nflverse-data/releases/download"
SCHEMA_DIR = Path(__file__).parent / "schemas"


class SchemaError(ValueError):
    """Raised when a dataset's schema YAML is missing or malformed."""


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    view_name: str
    source_url_template: str
    raw_filename_template: str
    processed_filename_template: str
    key_columns: tuple[str, ...]
    schema_path: Path
    min_season: int
    max_download_bytes: int
    derive: Callable[[pd.DataFrame], pd.DataFrame] | None = None

    def source_url(self, season: int) -> str:
        return self.source_url_template.format(season=season)

    def raw_path(self, season: int, raw_dir: Path = RAW_DATA_DIR) -> Path:
        return raw_dir / self.raw_filename_template.format(season=season)

    def processed_path(
        self, season: int, processed_dir: Path = PROCESSED_DATA_DIR
    ) -> Path:
        return processed_dir / self.processed_filename_template.format(season=season)

    @cached_property
    def schema(self) -> dict[str, Any]:
        return _load_schema(self.schema_path, self.view_name)

    @property
    def columns(self) -> dict[str, dict[str, Any]]:
        """Every processed column, in order, with its YAML metadata."""
        return self.schema["columns"]

    @property
    def source_columns(self) -> tuple[str, ...]:
        """Columns copied from the raw file; derived ones are added by cleaning."""
        return tuple(
            column for column, metadata in self.columns.items()
            if not metadata.get("derived")
        )

    @property
    def integer_columns(self) -> tuple[str, ...]:
        return tuple(
            column for column in self.source_columns
            if self.columns[column]["type"] == "integer"
        )

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
        key_columns=("game_id", "play_id"),
        schema_path=SCHEMA_DIR / "nfl_plays.yaml",
        min_season=1999,
        max_download_bytes=200 * 1024 * 1024,
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


def _load_schema(path: Path, view_name: str) -> dict[str, Any]:
    if not path.exists():
        raise SchemaError(f"Missing schema file: {path}")

    schema = yaml.safe_load(path.read_text())
    if not isinstance(schema, dict):
        raise SchemaError(f"Schema file is invalid: {path}")
    if schema.get("view") != view_name:
        raise SchemaError(f"Schema file {path} must define view: {view_name}")

    columns = schema.get("columns")
    if not isinstance(columns, dict) or not columns:
        raise SchemaError(f"Schema for {view_name} has no columns.")
    for column, metadata in columns.items():
        if not isinstance(metadata, dict) or "type" not in metadata:
            raise SchemaError(f"Schema for {view_name}.{column} needs a type.")

    return schema
