"""Build the in-memory DuckDB views (e.g. nfl_plays) over the processed Parquet files."""

from __future__ import annotations

from pathlib import Path
import re

import duckdb
import pyarrow.parquet as pq

from app.data_foundation import datasets
from app.data_foundation.datasets import DATASETS, DatasetSpec, get_dataset


_SEASON_FILE_PATTERN = re.compile(r"_(\d{4})\.parquet$")


class AnalyticsViewError(RuntimeError):
    """Raised when analytics views cannot be created from cleaned data."""


def _processed_paths(spec: DatasetSpec, data_dir: Path | None = None) -> list[Path]:
    # Read at call time (not as a default argument) so tests can patch it.
    data_dir = data_dir or datasets.PROCESSED_DATA_DIR
    pattern = spec.processed_file_pattern()
    paths = [
        path
        for path in data_dir.glob(spec.processed_filename_template.format(season="*"))
        if pattern.match(path.name)
    ]

    paths.sort(key=_season_from_path)
    if not paths:
        raise AnalyticsViewError(
            f"No cleaned {spec.view_name} files found in {data_dir}. Run: "
            f"python3 -m app.data_foundation.ingestion {spec.name} <seasons> && "
            f"python3 -m app.data_foundation.cleaning {spec.name} <seasons>"
        )

    return paths


def _season_from_path(path: Path) -> int:
    match = _SEASON_FILE_PATTERN.search(path.name)
    if not match:
        raise AnalyticsViewError(f"Unexpected cleaned data filename: {path}")

    return int(match.group(1))


def create_analytics_connection(
    paths_by_dataset: dict[str, list[Path]] | None = None,
) -> duckdb.DuckDBPyConnection:
    """Create approved views, from explicit paths or from every registered dataset."""
    if paths_by_dataset is None:
        paths_by_dataset = {
            name: _processed_paths(spec) for name, spec in DATASETS.items()
        }

    connection = duckdb.connect(database=":memory:")
    for name, paths in paths_by_dataset.items():
        _validate_compatible_schemas(paths)
        _create_view(connection, get_dataset(name), paths)
    return connection


def _create_view(
    connection: duckdb.DuckDBPyConnection,
    spec: DatasetSpec,
    paths: list[Path],
) -> None:
    path_list = ", ".join(_sql_string(str(path)) for path in paths)
    connection.execute(
        f"CREATE OR REPLACE VIEW {spec.view_name} AS "
        f"SELECT * FROM read_parquet([{path_list}], union_by_name=true)"
    )


def _validate_compatible_schemas(paths: list[Path]) -> None:
    if not paths:
        raise AnalyticsViewError("Cannot validate schemas without files.")

    base_path = paths[0]
    base_schema = pq.read_schema(base_path)
    base_fields = [field.name for field in base_schema]

    for path in paths[1:]:
        schema = pq.read_schema(path)
        fields = [field.name for field in schema]
        if fields != base_fields:
            raise AnalyticsViewError(
                "Cleaned schemas are not compatible: "
                f"{base_path} differs from {path}."
            )


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
