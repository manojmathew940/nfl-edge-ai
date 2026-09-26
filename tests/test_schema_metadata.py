from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.analytics.schema_metadata import (
    SchemaMetadataError,
    _load_validated_schema_metadata,
    render_schema_guides,
    render_view_schema_guide,
)
from app.data_foundation.datasets import get_dataset


PLAYS = get_dataset("plays")


class SchemaMetadataTest(unittest.TestCase):
    def test_load_validated_schema_metadata_loads_columns(self) -> None:
        view = _load_validated_schema_metadata(PLAYS)

        self.assertEqual(view["view"], "nfl_plays")
        self.assertEqual(view["grain"], "One row per play from an NFL game.")
        self.assertIn("season", view["columns"])
        self.assertIn("explosive_play", view["columns"])

    def test_render_view_schema_guide_includes_columns(self) -> None:
        guide = render_view_schema_guide("plays")

        self.assertIn("Approved view: nfl_plays", guide)
        self.assertIn("- season (integer): NFL season.", guide)
        self.assertIn(
            "- posteam (string): Team in possession on the play.",
            guide,
        )
        self.assertNotIn("bills_on_offense", guide)
        self.assertIn(
            "- explosive_play (boolean): True for explosive plays",
            guide,
        )
        self.assertIn(
            "- lateral_receiver_player_name (string): Player name for the player credited with lateral receiving yards.",
            guide,
        )

    def test_render_schema_guides_matches_single_guide_for_one_dataset(self) -> None:
        self.assertEqual(
            render_schema_guides(["plays"]), render_view_schema_guide("plays")
        )

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

            with self.assertRaisesRegex(SchemaMetadataError, "must define view"):
                _load_validated_schema_metadata(PLAYS, path)

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

            with self.assertRaisesRegex(SchemaMetadataError, "nfl_plays.season"):
                _load_validated_schema_metadata(PLAYS, path)

    def test_missing_file_raises_clear_error(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "missing.yaml"

            with self.assertRaisesRegex(SchemaMetadataError, "Missing schema"):
                _load_validated_schema_metadata(PLAYS, path)


if __name__ == "__main__":
    unittest.main()
