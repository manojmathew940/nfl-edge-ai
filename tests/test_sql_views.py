from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq

from app.analytics.sql_views import (
    AnalyticsViewError,
    create_analytics_connection,
    _processed_paths,
    _season_from_path,
)
from app.data_foundation.datasets import get_dataset


def expected_rows_by_season(paths: list[Path]) -> list[tuple[int, int]]:
    return [
        (_season_from_path(path), pq.ParquetFile(path).metadata.num_rows)
        for path in paths
    ]


class SqlViewsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = TemporaryDirectory()
        self.data_dir = Path(self.temp_directory.name)
        self.paths = []
        for season in (2023, 2024):
            path = self.data_dir / f"nfl_plays_{season}.parquet"
            pq.write_table(
                pa.table(
                    {
                        "season": [season],
                        "week": [1],
                        "game_id": [f"{season}_01_ARI_BUF"],
                        "play_id": [1],
                        "qtr": [1],
                        "posteam": ["BUF"],
                        "defteam": ["ARI"],
                        "rushing_yards": [5.0],
                        "lateral_receiver_player_name": [None],
                        "lateral_receiving_yards": [None],
                        "lateral_rusher_player_name": [None],
                        "lateral_rushing_yards": [None],
                        "epa": [0.1],
                    }
                ),
                path,
            )
            self.paths.append(path)

        self.player_path = self.data_dir / "nfl_player_weekly_2024.parquet"
        pq.write_table(
            pa.table(
                {
                    "season": [2024],
                    "game_id": ["2024_01_ARI_BUF"],
                    "player_id": ["00-0034857"],
                    "team": ["BUF"],
                    "passing_yards": [232],
                }
            ),
            self.player_path,
        )

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def test_nfl_plays_view_counts_rows_by_season(self) -> None:
        connection = create_analytics_connection({"plays": self.paths})

        rows = connection.execute(
            "SELECT season, COUNT(*) AS rows "
            "FROM nfl_plays "
            "GROUP BY season "
            "ORDER BY season"
        ).fetchall()

        self.assertEqual(rows, expected_rows_by_season(self.paths))

    def test_processed_paths_ignore_other_files_and_sort_by_season(self) -> None:
        (self.data_dir / "nfl_plays_2024.metadata.json").write_text("{}")
        (self.data_dir / "nfl_plays_latest.parquet").write_bytes(b"")

        paths = _processed_paths(get_dataset("plays"), self.data_dir)

        self.assertEqual(paths, sorted(self.paths, key=_season_from_path))

    def test_default_connection_reads_processed_data_dir(self) -> None:
        with patch("app.data_foundation.datasets.PROCESSED_DATA_DIR", self.data_dir):
            connection = create_analytics_connection()

        seasons = connection.execute(
            "SELECT DISTINCT season FROM nfl_plays ORDER BY season"
        ).fetchall()

        self.assertEqual(seasons, [(2023,), (2024,)])

    def test_player_weekly_joins_to_plays_on_game_and_team(self) -> None:
        connection = create_analytics_connection(
            {"plays": self.paths, "player_weekly": [self.player_path]}
        )

        rows = connection.execute(
            "SELECT w.player_id, COUNT(p.play_id) AS offensive_plays "
            "FROM nfl_player_weekly w "
            "JOIN nfl_plays p ON p.game_id = w.game_id AND p.posteam = w.team "
            "GROUP BY ALL"
        ).fetchall()

        self.assertEqual(rows, [("00-0034857", 1)])

    def test_no_processed_files_raises_clear_error(self) -> None:
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                AnalyticsViewError, "No cleaned nfl_plays files.*ingestion plays"
            ):
                _processed_paths(get_dataset("plays"), Path(directory))

    def test_incompatible_schema_raises_clear_error(self) -> None:
        with TemporaryDirectory() as directory:
            temp_dir = Path(directory)
            first = temp_dir / "nfl_plays_2098.parquet"
            second = temp_dir / "nfl_plays_2099.parquet"

            pq.write_table(pa.table({"season": [2098], "week": [1]}), first)
            pq.write_table(pa.table({"season": [2099], "posteam": ["NYJ"]}), second)

            with self.assertRaisesRegex(
                AnalyticsViewError, "schemas are not compatible"
            ):
                create_analytics_connection({"plays": [first, second]})


if __name__ == "__main__":
    unittest.main()
