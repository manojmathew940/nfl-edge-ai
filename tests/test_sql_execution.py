from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq

from app.analytics.sql_execution import validate_and_execute_analytics_sql
from app.analytics.sql_views import (
    AnalyticsViewError,
    _season_from_path,
)


def expected_rows_by_season(paths: list[Path]) -> list[tuple[int, int]]:
    return [
        (_season_from_path(path), pq.ParquetFile(path).metadata.num_rows)
        for path in paths
    ]


class SqlExecutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = TemporaryDirectory()
        self.paths = []
        for season in (2023, 2024):
            path = Path(self.temp_directory.name) / f"nfl_plays_{season}.parquet"
            pq.write_table(
                pa.table(
                    {
                        "season": [season, season],
                        "play_id": [1, 2],
                        "posteam": ["BUF", "ARI"],
                        "epa": [0.1, -0.1],
                    }
                ),
                path,
            )
            self.paths.append(path)
        pq.write_table(
            pa.table({"season": [2024], "player_id": ["00-0034857"]}),
            Path(self.temp_directory.name) / "nfl_player_weekly_2024.parquet",
        )
        self.paths_patch = patch(
            "app.data_foundation.datasets.PROCESSED_DATA_DIR",
            Path(self.temp_directory.name),
        )
        self.paths_patch.start()

    def tearDown(self) -> None:
        self.paths_patch.stop()
        self.temp_directory.cleanup()

    def test_validate_and_execute_analytics_sql_returns_json_safe_rows(self) -> None:
        result = validate_and_execute_analytics_sql(
            "SELECT season, COUNT(*) AS rows "
            "FROM nfl_plays "
            "GROUP BY season "
            "ORDER BY season"
        )
        expected_rows = [
            {"season": season, "rows": rows}
            for season, rows in expected_rows_by_season(self.paths)
        ]

        self.assertTrue(result.is_valid)
        self.assertEqual(result.validation_reason, "SQL is valid.")
        self.assertEqual(result.columns, ["season", "rows"])
        self.assertEqual(result.rows, expected_rows)

    def test_validate_and_execute_analytics_sql_applies_row_limit(self) -> None:
        result = validate_and_execute_analytics_sql(
            "SELECT play_id FROM nfl_plays ORDER BY season, play_id",
            row_limit=3,
        )

        self.assertEqual(len(result.rows), 3)

    def test_validate_and_execute_analytics_sql_rejects_invalid_row_limit(self) -> None:
        with self.assertRaisesRegex(AnalyticsViewError, "row_limit"):
            validate_and_execute_analytics_sql("SELECT 1", row_limit=0)

    def test_validate_and_execute_analytics_sql_rejects_invalid_sql(self) -> None:
        result = validate_and_execute_analytics_sql("DROP TABLE nfl_plays")

        self.assertFalse(result.is_valid)
        self.assertIn("SELECT", result.validation_reason)
        self.assertEqual(result.columns, [])
        self.assertEqual(result.rows, [])

    def test_validate_and_execute_analytics_sql_reports_query_errors(self) -> None:
        result = validate_and_execute_analytics_sql(
            "SELECT receiver_player_name FROM nfl_player_weekly"
        )

        self.assertFalse(result.is_valid)
        self.assertIn("SQL failed to run in DuckDB", result.validation_reason)
        self.assertIn("receiver_player_name", result.validation_reason)
        self.assertEqual(result.rows, [])


if __name__ == "__main__":
    unittest.main()
