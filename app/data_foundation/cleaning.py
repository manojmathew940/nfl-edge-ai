# Clean the data by normalizing the data and validating the keys.
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from app.data_foundation.datasets import (
    DATASETS,
    PROCESSED_DATA_DIR,
    RAW_DATA_DIR,
    DatasetSpec,
    get_dataset,
)
from app.data_foundation.file_io import staged_output


def _load_raw(spec: DatasetSpec, season: int, raw_dir: Path = RAW_DATA_DIR) -> pd.DataFrame:
    raw_path = spec.raw_path(season, raw_dir)
    if not raw_path.exists():
        raise FileNotFoundError(
            f"Missing raw data file: {raw_path}. Run: "
            f"python3 -m app.data_foundation.ingestion {spec.name} {season}"
        )

    return pd.read_parquet(raw_path)


def _select_source_columns(spec: DatasetSpec, raw: pd.DataFrame) -> pd.DataFrame:
    missing_columns = [
        column for column in spec.source_columns if column not in raw.columns
    ]
    if missing_columns:
        raise ValueError(
            f"Raw {spec.name} data is missing required processed columns: "
            + ", ".join(missing_columns)
        )

    return raw.loc[:, list(spec.source_columns)].copy()


def _normalize_source_values(spec: DatasetSpec, processed: pd.DataFrame) -> pd.DataFrame:
    """Store blank strings as nulls and whole-number columns as integers.

    nflverse Parquet stores some whole-number fields as doubles. Integer columns
    come from the dataset's schema YAML so the processed file matches its docs;
    a fractional value in one of them fails loudly instead of being truncated.
    """
    for column in processed.columns:
        if pd.api.types.is_string_dtype(processed[column]):
            processed[column] = processed[column].mask(processed[column] == "")

    for column in spec.integer_columns:
        try:
            processed[column] = processed[column].astype("Int64")
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{spec.name}.{column} is documented as integer but has "
                f"non-integer values: {error}"
            ) from error

    return processed


def _validate_keys(spec: DatasetSpec, processed: pd.DataFrame) -> None:
    key_columns = list(spec.key_columns)
    null_keys = processed[key_columns].isna().any(axis=1)
    if null_keys.any():
        raise ValueError(
            f"{spec.name} has {int(null_keys.sum())} rows with null key columns: "
            + ", ".join(key_columns)
        )

    duplicate_keys = processed.duplicated(key_columns)
    if duplicate_keys.any():
        raise ValueError(
            f"{spec.name} has {int(duplicate_keys.sum())} duplicate rows for key: "
            + ", ".join(key_columns)
        )


def _clean_dataset(
    spec: DatasetSpec, season: int, raw_dir: Path = RAW_DATA_DIR
) -> pd.DataFrame:
    processed = _select_source_columns(spec, _load_raw(spec, season, raw_dir))
    processed = _normalize_source_values(spec, processed)
    if spec.derive is not None:
        processed = spec.derive(processed)
    _validate_keys(spec, processed)
    return processed


def save_processed(
    dataset_name: str,
    season: int,
    raw_dir: Path = RAW_DATA_DIR,
    processed_dir: Path = PROCESSED_DATA_DIR,
) -> tuple[Path, int, int]:
    spec = get_dataset(dataset_name)
    processed = _clean_dataset(spec, season, raw_dir)

    output_path = spec.processed_path(season, processed_dir)
    with staged_output(output_path) as temp_path:
        processed.to_parquet(temp_path, index=False)

    row_count, column_count = processed.shape
    return output_path, row_count, column_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create processed analytics data for one or more NFL seasons."
    )
    parser.add_argument("dataset", choices=DATASETS, help="Dataset to process")
    parser.add_argument(
        "seasons", nargs="+", type=int, help="NFL seasons to process, such as 2024"
    )
    args = parser.parse_args()

    for season in args.seasons:
        try:
            output_path, row_count, column_count = save_processed(args.dataset, season)
        except (FileNotFoundError, ValueError) as error:
            parser.exit(1, f"Failed to process {args.dataset} {season}: {error}\n")

        print(f"Saved {row_count} rows and {column_count} columns to {output_path}")


if __name__ == "__main__":
    main()
