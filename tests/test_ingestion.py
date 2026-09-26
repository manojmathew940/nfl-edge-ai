from __future__ import annotations

from dataclasses import replace
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq

from app.data_foundation.datasets import DATASETS, get_dataset, validate_season
from app.data_foundation.ingestion import save_raw


PLAYS = get_dataset("plays")


class StubResponse(io.BytesIO):
    def __init__(
        self, payload: bytes, content_length: int | None = None, *, send_length=True
    ):
        super().__init__(payload)
        length = len(payload) if content_length is None else content_length
        self.headers = {"Content-Length": str(length)} if send_length else {}


def parquet_bytes(columns: dict[str, list]) -> bytes:
    buffer = io.BytesIO()
    pq.write_table(pa.table(columns), buffer)
    return buffer.getvalue()


def complete_plays(rows: int = 2) -> dict[str, list]:
    columns = {column: [None] * rows for column in PLAYS.source_columns}
    columns["game_id"] = ["2024_01_ARI_BUF", "2024_01_SF_NYJ"][:rows]
    columns["play_id"] = list(range(1, rows + 1))
    columns["posteam"] = ["ARI", "SF"][:rows]
    columns["extra_source_column"] = ["kept"] * rows
    return columns


class IngestionTest(unittest.TestCase):
    def test_saves_source_parquet_unchanged_with_metadata(self) -> None:
        payload = parquet_bytes(complete_plays())

        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            with patch(
                "app.data_foundation.ingestion.urlopen",
                return_value=StubResponse(payload),
            ) as urlopen:
                output_path, rows_written = save_raw("plays", 2024, output_dir)

            self.assertEqual(output_path.name, "nfl_play_by_play_2024_raw.parquet")
            self.assertEqual(rows_written, 2)
            self.assertEqual(output_path.read_bytes(), payload)

            metadata = json.loads(
                (output_dir / "nfl_play_by_play_2024_raw.metadata.json").read_text()
            )
            self.assertEqual(metadata["dataset"], "plays")
            self.assertEqual(metadata["scope"], "all_nfl")
            self.assertEqual(metadata["rows_written"], 2)
            self.assertEqual(metadata["bytes"], len(payload))
            self.assertEqual(
                metadata["source_column_count"], len(PLAYS.source_columns) + 1
            )
            self.assertEqual(metadata["output_path"], str(output_path))

            urlopen.assert_called_once_with(PLAYS.source_url(2024), timeout=60)

    def test_missing_required_columns_does_not_replace_existing_output(self) -> None:
        payload = parquet_bytes({"game_id": ["2024_01_ARI_BUF"], "play_id": [1]})

        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            output_path = PLAYS.raw_path(2024, output_dir)
            output_path.write_bytes(b"existing-data")

            with patch(
                "app.data_foundation.ingestion.urlopen",
                return_value=StubResponse(payload),
            ):
                with self.assertRaisesRegex(ValueError, "missing required columns"):
                    save_raw("plays", 2024, output_dir)

            self.assertEqual(output_path.read_bytes(), b"existing-data")
            self.assertEqual(list(output_dir.glob(".nfl_play_by_play_2024_raw*")), [])

    def test_content_length_mismatch_does_not_replace_existing_output(self) -> None:
        payload = parquet_bytes(complete_plays())

        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            output_path = PLAYS.raw_path(2024, output_dir)
            output_path.write_bytes(b"existing-data")

            with patch(
                "app.data_foundation.ingestion.urlopen",
                return_value=StubResponse(payload[:-8], content_length=len(payload)),
            ):
                with self.assertRaisesRegex(ValueError, "Incomplete download"):
                    save_raw("plays", 2024, output_dir)

            self.assertEqual(output_path.read_bytes(), b"existing-data")
            self.assertEqual(list(output_dir.glob(".nfl_play_by_play_2024_raw*")), [])

    def test_corrupt_parquet_does_not_replace_existing_output(self) -> None:
        payload = parquet_bytes(complete_plays())[:-8]

        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            output_path = PLAYS.raw_path(2024, output_dir)
            output_path.write_bytes(b"existing-data")

            with patch(
                "app.data_foundation.ingestion.urlopen",
                return_value=StubResponse(payload),
            ):
                with self.assertRaises(pa.ArrowInvalid):
                    save_raw("plays", 2024, output_dir)

            self.assertEqual(output_path.read_bytes(), b"existing-data")

    def test_rejects_declared_size_over_limit(self) -> None:
        response = StubResponse(b"", content_length=PLAYS.max_download_bytes + 1)

        with TemporaryDirectory() as directory:
            with patch("app.data_foundation.ingestion.urlopen", return_value=response):
                with self.assertRaisesRegex(ValueError, "larger than the configured limit"):
                    save_raw("plays", 2024, Path(directory))

    def test_rejects_received_bytes_over_limit(self) -> None:
        payload = parquet_bytes(complete_plays())

        with TemporaryDirectory() as directory:
            with patch(
                "app.data_foundation.ingestion.urlopen",
                return_value=StubResponse(payload, send_length=False),
            ), patch.dict(
                DATASETS,
                {"plays": replace(PLAYS, max_download_bytes=len(payload) - 1)},
            ):
                with self.assertRaisesRegex(ValueError, "larger than the configured limit"):
                    save_raw("plays", 2024, Path(directory))

    def test_rejects_season_outside_supported_range(self) -> None:
        with self.assertRaisesRegex(ValueError, "Season must be between"):
            validate_season(PLAYS, 1998)

    def test_rejects_unknown_dataset(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown dataset"):
            save_raw("injuries", 2024)


if __name__ == "__main__":
    unittest.main()
