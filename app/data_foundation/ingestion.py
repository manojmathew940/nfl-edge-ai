import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO
from urllib.request import urlopen

import pyarrow as pa
import pyarrow.parquet as pq

from app.data_foundation.datasets import (
    DATASETS,
    RAW_DATA_DIR,
    DatasetSpec,
    get_dataset,
    validate_season,
)
from app.data_foundation.file_io import staged_output, write_metadata


_DOWNLOAD_CHUNK_BYTES = 1024 * 1024


def _validate_content_length(content_length: str | None, max_bytes: int) -> int | None:
    if content_length is None:
        return None

    expected_bytes = int(content_length)
    if expected_bytes > max_bytes:
        raise ValueError(
            "Source file is larger than the configured limit: "
            f"{expected_bytes} bytes."
        )
    return expected_bytes


def _validate_required_columns(spec: DatasetSpec, column_names: list[str]) -> None:
    missing_columns = [
        column for column in spec.source_columns if column not in column_names
    ]
    if missing_columns:
        raise ValueError(
            "Source file is missing required columns: " + ", ".join(missing_columns)
        )


def _copy_limited(
    source: BinaryIO,
    destination: BinaryIO,
    *,
    max_bytes: int,
    expected_bytes: int | None,
) -> int:
    """Copy a download while enforcing the size limit on the bytes received."""
    bytes_written = 0
    while chunk := source.read(_DOWNLOAD_CHUNK_BYTES):
        bytes_written += len(chunk)
        if bytes_written > max_bytes:
            raise ValueError(
                f"Source file is larger than the configured limit: over {max_bytes} bytes."
            )
        destination.write(chunk)

    if expected_bytes is not None and bytes_written != expected_bytes:
        raise ValueError(
            f"Incomplete download: expected {expected_bytes} bytes, "
            f"received {bytes_written}."
        )
    return bytes_written


def save_raw(
    dataset_name: str, season: int, raw_dir: Path = RAW_DATA_DIR
) -> tuple[Path, int]:
    """Download one season of a dataset and save the source Parquet unchanged."""
    spec = get_dataset(dataset_name)
    validate_season(spec, season)

    source_url = spec.source_url(season)
    output_path = spec.raw_path(season, raw_dir)

    with staged_output(output_path) as temp_path:
        with urlopen(source_url, timeout=60) as response, temp_path.open("wb") as output:
            expected_bytes = _validate_content_length(
                response.headers.get("Content-Length"), spec.max_download_bytes
            )
            bytes_written = _copy_limited(
                response,
                output,
                max_bytes=spec.max_download_bytes,
                expected_bytes=expected_bytes,
            )

        parquet_file = pq.ParquetFile(temp_path)
        column_names = parquet_file.schema_arrow.names
        _validate_required_columns(spec, column_names)
        rows_written = parquet_file.metadata.num_rows

    write_metadata(
        output_path,
        {
            "source": "nflverse/nflverse-data GitHub release",
            "source_url": source_url,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "dataset": spec.name,
            "season": season,
            "scope": "all_nfl",
            "output_path": str(output_path),
            "bytes": bytes_written,
            "rows_written": rows_written,
            "source_column_count": len(column_names),
            "required_columns": sorted(spec.source_columns),
        },
    )

    return output_path, rows_written


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download raw nflverse data for one or more NFL seasons."
    )
    parser.add_argument("dataset", choices=DATASETS, help="Dataset to download")
    parser.add_argument(
        "seasons", nargs="+", type=int, help="NFL seasons to download, such as 2023"
    )
    args = parser.parse_args()

    spec = get_dataset(args.dataset)
    # save_raw validates each season too; checking all of them first keeps a bad
    # season at the end of the list from leaving a partially downloaded run.
    try:
        for season in args.seasons:
            validate_season(spec, season)
    except ValueError as error:
        parser.error(str(error))

    for season in args.seasons:
        try:
            output_path, rows_written = save_raw(args.dataset, season)
        except (ValueError, OSError, pa.ArrowException) as error:
            parser.exit(1, f"Failed to download {args.dataset} {season}: {error}\n")

        print(f"Saved {rows_written} raw {args.dataset} rows to {output_path}")


if __name__ == "__main__":
    main()
