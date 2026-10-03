from __future__ import annotations

import unittest

from app.analytics.schema_metadata import render_schema_guides, render_view_schema_guide


class SchemaMetadataTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
