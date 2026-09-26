from __future__ import annotations

import unittest

import yaml

from app.analytics.sql_validation import APPROVED_ANALYTICS_VIEWS
from app.data_foundation.datasets import DATASETS, approved_view_names, get_dataset


class DatasetRegistryTest(unittest.TestCase):
    def test_schema_yaml_documents_exactly_the_processed_columns(self) -> None:
        for spec in DATASETS.values():
            with self.subTest(dataset=spec.name):
                schema = yaml.safe_load(spec.schema_path.read_text())

                self.assertEqual(schema["view"], spec.view_name)
                self.assertEqual(
                    tuple(schema["columns"]),
                    spec.source_columns + spec.derived_columns,
                )

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


if __name__ == "__main__":
    unittest.main()
