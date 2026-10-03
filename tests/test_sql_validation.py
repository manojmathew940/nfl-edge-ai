from __future__ import annotations

import unittest

from app.analytics.sql_validation import validate_analytics_sql


class SqlValidationTest(unittest.TestCase):
    def test_accepts_select_from_approved_view(self) -> None:
        result = validate_analytics_sql(
            "SELECT season, COUNT(*) FROM nfl_plays GROUP BY season"
        )

        self.assertTrue(result.is_valid)

    def test_accepts_with_select_from_approved_view(self) -> None:
        result = validate_analytics_sql(
            "WITH by_season AS ("
            "SELECT season, COUNT(*) AS rows FROM nfl_plays GROUP BY season"
            ") SELECT * FROM by_season"
        )

        self.assertTrue(result.is_valid)

    def test_accepts_join_of_player_weekly_and_plays(self) -> None:
        result = validate_analytics_sql(
            "SELECT w.player_display_name, SUM(w.passing_epa), COUNT(p.play_id) "
            "FROM nfl_player_weekly w "
            "JOIN nfl_plays p ON p.game_id = w.game_id AND p.posteam = w.team "
            "GROUP BY 1"
        )

        self.assertTrue(result.is_valid)

    def test_rejects_drop_statement(self) -> None:
        result = validate_analytics_sql("DROP TABLE nfl_plays")

        self.assertFalse(result.is_valid)
        self.assertIn("SELECT", result.reason)

    def test_rejects_delete_statement(self) -> None:
        result = validate_analytics_sql("DELETE FROM nfl_plays")

        self.assertFalse(result.is_valid)
        self.assertIn("SELECT", result.reason)

    def test_rejects_copy_statement(self) -> None:
        result = validate_analytics_sql("COPY nfl_plays TO 'file.csv'")

        self.assertFalse(result.is_valid)
        self.assertIn("SELECT", result.reason)

    def test_rejects_raw_file_function(self) -> None:
        result = validate_analytics_sql(
            "SELECT * FROM read_parquet('data/raw/nfl_player_weekly_2025_raw.parquet')"
        )

        self.assertFalse(result.is_valid)
        self.assertIn("blocked function", result.reason)

    def test_rejects_unknown_table(self) -> None:
        result = validate_analytics_sql("SELECT * FROM some_unknown_table")

        self.assertFalse(result.is_valid)
        self.assertIn("unapproved table", result.reason)

    def test_rejects_legacy_bills_view(self) -> None:
        result = validate_analytics_sql("SELECT * FROM bills_plays")

        self.assertFalse(result.is_valid)
        self.assertIn("unapproved table", result.reason)

    def test_rejects_multiple_statements(self) -> None:
        result = validate_analytics_sql("SELECT 1; SELECT 2")

        self.assertFalse(result.is_valid)
        self.assertIn("exactly one statement", result.reason)

    def test_rejects_empty_sql(self) -> None:
        result = validate_analytics_sql(" ")

        self.assertFalse(result.is_valid)
        self.assertIn("empty", result.reason)


if __name__ == "__main__":
    unittest.main()
