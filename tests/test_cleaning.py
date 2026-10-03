from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from app.data_foundation.cleaning import (
    _normalize_source_values,
    save_processed,
    _select_source_columns,
)
from app.data_foundation.datasets import get_dataset
from app.data_foundation.plays import add_derived_fields


PLAYS = get_dataset("plays")


def source_frame(rows: int, **columns: list) -> pd.DataFrame:
    """A raw-shaped frame with every source column, null unless given."""
    frame = {column: [None] * rows for column in PLAYS.source_columns}
    frame.update(columns)
    return pd.DataFrame(frame)


class CleaningTest(unittest.TestCase):
    def test_paths_use_nfl_wide_names(self) -> None:
        self.assertEqual(
            PLAYS.raw_path(2024, Path("raw")),
            Path("raw/nfl_play_by_play_2024_raw.parquet"),
        )
        self.assertEqual(
            PLAYS.processed_path(2024, Path("processed")),
            Path("processed/nfl_plays_2024.parquet"),
        )

    def test_adds_neutral_derived_fields_for_multiple_teams(self) -> None:
        plays = pd.DataFrame(
            [
                {
                    "game_id": "2024_01_ARI_BUF",
                    "play_id": 2,
                    "down": 3,
                    "yardline_100": 19,
                    "interception": 0,
                    "fumble_lost": 0,
                    "pass_attempt": 1,
                    "rush_attempt": 0,
                    "yards_gained": 21,
                },
                {
                    "game_id": "2024_01_SF_NYJ",
                    "play_id": 1,
                    "down": 1,
                    "yardline_100": 60,
                    "interception": 1,
                    "fumble_lost": 0,
                    "pass_attempt": 1,
                    "rush_attempt": 0,
                    "yards_gained": 0,
                },
            ]
        )

        result = add_derived_fields(plays)

        self.assertEqual(result["game_id"].tolist(), [
            "2024_01_ARI_BUF",
            "2024_01_SF_NYJ",
        ])
        self.assertEqual(result["third_down_attempt"].tolist(), [True, False])
        self.assertEqual(result["red_zone_play"].tolist(), [True, False])
        self.assertEqual(result["explosive_play"].tolist(), [True, False])
        self.assertEqual(result["turnover"].tolist(), [False, True])
        self.assertNotIn("bills_on_offense", result.columns)
        self.assertNotIn("opponent", result.columns)

    def test_select_source_columns_rejects_incomplete_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing required processed columns"):
            _select_source_columns(PLAYS, pd.DataFrame({"season": [2024]}))

    def test_saves_complete_source_as_processed_parquet(self) -> None:
        row = {column: None for column in PLAYS.source_columns}
        row.update(
            {
                "season": 2024,
                "week": 1,
                "game_id": "2024_01_ARI_BUF",
                "play_id": 1,
                "home_team": "BUF",
                "away_team": "ARI",
                "posteam": "ARI",
                "defteam": "BUF",
                "down": 3,
                "yardline_100": 15,
                "interception": 0,
                "fumble_lost": 0,
                "pass_attempt": 1,
                "rush_attempt": 0,
                "yards_gained": 20,
            }
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            raw_dir = root / "raw"
            processed_dir = root / "processed"
            raw_dir.mkdir()
            pd.DataFrame([row]).to_parquet(PLAYS.raw_path(2024, raw_dir), index=False)

            output_path, row_count, column_count = save_processed(
                "plays", 2024, raw_dir, processed_dir
            )
            processed = pd.read_parquet(output_path)

            self.assertEqual(row_count, 1)
            self.assertEqual(column_count, len(processed.columns))
            self.assertEqual(list(processed.columns), list(PLAYS.columns))
            self.assertEqual(processed["posteam"].tolist(), ["ARI"])
            self.assertEqual(processed["turnover"].tolist(), [False])
            self.assertEqual(processed["third_down_attempt"].tolist(), [True])
            self.assertEqual(processed["red_zone_play"].tolist(), [True])
            self.assertEqual(processed["explosive_play"].tolist(), [True])

    def test_saves_processed_file_without_replacing_on_failure(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            raw_dir = root / "raw"
            processed_dir = root / "processed"
            raw_dir.mkdir()
            processed_dir.mkdir()
            output_path = PLAYS.processed_path(2024, processed_dir)
            output_path.write_bytes(b"existing-data")
            incomplete = pd.DataFrame({"season": [2024]})
            incomplete.to_parquet(PLAYS.raw_path(2024, raw_dir), index=False)

            with self.assertRaisesRegex(ValueError, "missing required processed columns"):
                save_processed("plays", 2024, raw_dir, processed_dir)

            self.assertEqual(output_path.read_bytes(), b"existing-data")

    def test_normalizes_blank_strings_and_documented_integer_columns(self) -> None:
        plays = source_frame(
            3,
            play_id=[1.0, 2.0, None],
            surface=["grass", "", None],
            epa=[0.5, 1.0, None],
        )

        result = _normalize_source_values(PLAYS, plays)

        self.assertEqual(str(result["play_id"].dtype), "Int64")
        self.assertEqual(result["play_id"].tolist()[:2], [1, 2])
        self.assertTrue(pd.isna(result["play_id"].iloc[2]))
        self.assertEqual(result["surface"].iloc[0], "grass")
        self.assertTrue(result["surface"].iloc[1:].isna().all())
        self.assertEqual(str(result["epa"].dtype), "float64")

    def test_fractional_value_in_integer_column_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "plays.qtr is documented as integer"):
            _normalize_source_values(PLAYS, source_frame(2, qtr=[1.0, 2.5]))

    def test_rejects_duplicate_keys(self) -> None:
        rows = []
        for _ in range(2):
            row = {column: None for column in PLAYS.source_columns}
            row.update({"game_id": "2024_01_ARI_BUF", "play_id": 1})
            rows.append(row)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "raw").mkdir()
            pd.DataFrame(rows).to_parquet(PLAYS.raw_path(2024, root / "raw"), index=False)

            with self.assertRaisesRegex(ValueError, "1 duplicate rows for key"):
                save_processed("plays", 2024, root / "raw", root / "processed")

            self.assertFalse(PLAYS.processed_path(2024, root / "processed").exists())

    def test_missing_raw_file_names_ingestion_command(self) -> None:
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                FileNotFoundError, "ingestion plays 2024"
            ):
                save_processed("plays", 2024, Path(directory), Path(directory))


if __name__ == "__main__":
    unittest.main()
