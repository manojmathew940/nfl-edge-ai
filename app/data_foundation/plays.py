"""Play-by-play derived fields. Columns are defined in schemas/nfl_plays.yaml."""

from __future__ import annotations

import pandas as pd


def add_derived_fields(play_by_play: pd.DataFrame) -> pd.DataFrame:
    play_by_play = play_by_play.sort_values(["game_id", "play_id"]).copy()

    play_by_play["turnover"] = (
        play_by_play[["interception", "fumble_lost"]].fillna(0).astype(int).sum(axis=1)
        > 0
    )
    play_by_play["third_down_attempt"] = play_by_play["down"] == 3
    play_by_play["red_zone_play"] = play_by_play["yardline_100"] <= 20
    play_by_play["explosive_play"] = (
        ((play_by_play["pass_attempt"] == 1) & (play_by_play["yards_gained"] >= 20))
        | ((play_by_play["rush_attempt"] == 1) & (play_by_play["yards_gained"] >= 10))
    )

    return play_by_play
