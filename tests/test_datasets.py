from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.analytics.sql_validation import APPROVED_ANALYTICS_VIEWS
from app.data_foundation.datasets import (
    DATASETS,
    SchemaError,
    approved_view_names,
    get_dataset,
)


PLAYS = get_dataset("plays")


class DatasetRegistryTest(unittest.TestCase):
    def test_columns_come_from_schema_yaml(self) -> None:
        self.assertEqual(PLAYS.schema["view"], "nfl_plays")
        self.assertIn("season", PLAYS.source_columns)
        self.assertNotIn("explosive_play", PLAYS.source_columns)
        self.assertIn("explosive_play", PLAYS.columns)
        self.assertIn("play_id", PLAYS.integer_columns)
        self.assertNotIn("epa", PLAYS.integer_columns)

    def test_key_columns_are_kept_in_processed_output(self) -> None:
        for spec in DATASETS.values():
            with self.subTest(dataset=spec.name):
                self.assertTrue(set(spec.key_columns) <= set(spec.source_columns))

    def test_view_and_file_names_are_unique(self) -> None:
        specs = list(DATASETS.values())

        self.assertEqual(len({spec.view_name for spec in specs}), len(specs))
        self.assertEqual(
            len({spec.processed_filename_template for spec in specs}), len(specs)
        )
        self.assertEqual(len({spec.raw_filename_template for spec in specs}), len(specs))

    def test_registry_key_matches_dataset_name(self) -> None:
        for name, spec in DATASETS.items():
            self.assertEqual(name, spec.name)

    def test_sql_validation_approves_every_registered_view(self) -> None:
        self.assertEqual(APPROVED_ANALYTICS_VIEWS, approved_view_names())

    def test_processed_file_pattern_matches_only_season_files(self) -> None:
        pattern = get_dataset("plays").processed_file_pattern()

        self.assertEqual(pattern.match("nfl_plays_2024.parquet").group(1), "2024")
        self.assertIsNone(pattern.match("nfl_plays_2024.metadata.json"))
        self.assertIsNone(pattern.match("nfl_plays_latest.parquet"))


    def test_wrong_view_raises_clear_error(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "schema.yaml"
            path.write_text(
                """
view: other_view
description: Test view.
grain: Test grain.
columns:
  season:
    type: integer
    description: NFL season.
""".strip()
            )

            with self.assertRaisesRegex(SchemaError, "must define view"):
                replace(PLAYS, schema_path=path).schema

    def test_invalid_column_metadata_raises_clear_error(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "schema.yaml"
            path.write_text(
                """
view: nfl_plays
description: Test view.
grain: Test grain.
columns:
  season: NFL season.
""".strip()
            )

            with self.assertRaisesRegex(SchemaError, "nfl_plays.season needs a type"):
                replace(PLAYS, schema_path=path).schema

    def test_missing_file_raises_clear_error(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "missing.yaml"

            with self.assertRaisesRegex(SchemaError, "Missing schema"):
                replace(PLAYS, schema_path=path).schema


if __name__ == "__main__":
    unittest.main()
