# NFL Plays Dataset Schema

## Purpose

This document is the human-readable guide to the league-wide play-by-play
dataset used by the NFL AI Analyst. It explains the fields and football
semantics needed to write correct analytics queries.

The exhaustive machine-readable contract, including every column and data
type, is maintained in `docs/nfl_plays_schema.yaml`.

## Row Grain

One row represents one play from an NFL game. Rows can include ordinary
offensive plays, penalties, kickoffs, punts, field goals, extra points,
two-point attempts, and administrative events. Some fields are therefore null
when they do not apply to that row.

Unless stated otherwise, numeric flags use `1` for true and `0` for false.

## Game Context

- `season`: NFL season year.
- `season_type`: Season segment, such as `REG` or `POST`.
- `week`: NFL week number within the season.
- `game_id`: Unique nflverse game identifier.
- `game_date`: Date the game was played.
- `home_team`: Home team abbreviation.
- `away_team`: Away team abbreviation.
- `location`: Location classification supplied by nflverse, such as home or neutral.
- `result`: Final home-team score minus final away-team score. This is always from the home team's perspective.
- `home_score`: Final home-team score.
- `away_score`: Final away-team score.
- `div_game`: Whether the game was between division opponents.
- `roof`: Stadium roof classification.
- `surface`: Playing surface.
- `temp`: Game-time temperature when available.
- `wind`: Game-time wind speed when available.

## Play, Clock, And Field Position

- `play_id`: Play identifier within a game. Use it with `game_id` for a globally unique play key.
- `drive`: Drive number supplied by the source.
- `fixed_drive`: Normalized drive number.
- `fixed_drive_result`: Normalized final result of the drive.
- `qtr`: Quarter in which the play started.
- `time`: Display clock at the start of the play, such as `12:34`.
- `quarter_seconds_remaining`: Seconds remaining in the current quarter.
- `half_seconds_remaining`: Seconds remaining in the current half.
- `game_seconds_remaining`: Seconds remaining in regulation. This is usually easier than parsing `time` for time-range filters.
- `down`: Down number at the start of the play.
- `ydstogo`: Yards needed for a first down.
- `yardline_100`: Yards from the opponent's end zone from the possession team's perspective. A value of `20` means the opponent's 20-yard line; smaller values are closer to scoring.
- `yrdln`: Human-readable field position, including the team side and yard line.
- `side_of_field`: Team abbreviation for the side of the field where the ball is spotted.
- `goal_to_go`: Whether the offense is in a goal-to-go situation.
- `desc`: Original textual play description.
- `play_type`: Normalized nflverse play type.
- `play_type_nfl`: NFL source play type.

## Team Perspective

- `posteam`: Team in possession. Use this field to measure a team's offensive performance.
- `defteam`: Team defending the play. Use this field to measure performance allowed by a defense.
- `posteam_type`: Whether `posteam` is the home or away team.

Team analysis should use these neutral fields. For example, Buffalo offense is
`posteam = 'BUF'`, while Buffalo defense is `defteam = 'BUF'`.

## Score Context

- `posteam_score`: Possession-team score before the play.
- `defteam_score`: Defensive-team score before the play.
- `score_differential`: `posteam_score - defteam_score` before the play. A positive value means the possession team is leading.
- `posteam_score_post`: Possession-team score after the play.
- `defteam_score_post`: Defensive-team score after the play.
- `score_differential_post`: Possession-team score differential after the play.
- `total_home_score`: Home-team score after the play.
- `total_away_score`: Away-team score after the play.

Do not combine possession-perspective score fields with home-perspective fields
without checking which team has possession.

## Play Results

- `yards_gained`: Net yards gained on the play.
- `first_down`: Whether the play produced a first down.
- `touchdown`: Whether a touchdown occurred on the play.
- `td_team`: Team credited with the touchdown.
- `interception`: Whether the pass was intercepted.
- `fumble`: Whether a fumble occurred, including one recovered by the same team.
- `fumble_lost`: Whether the fumbling team lost possession.
- `sack`: Whether the quarterback was sacked.
- `qb_hit`: Whether the quarterback was hit.
- `safety`: Whether the play resulted in a safety.
- `tackled_for_loss`: Whether the ball carrier was tackled for a loss.
- `penalty`: Whether a penalty occurred.
- `penalty_team`: Team charged with the penalty.
- `penalty_type`: Type of penalty.
- `penalty_yards`: Penalty yards assessed.
- `third_down_converted`: Whether a third-down play converted.
- `third_down_failed`: Whether a third-down play failed.
- `fourth_down_converted`: Whether a fourth-down play converted.
- `fourth_down_failed`: Whether a fourth-down play failed.

## Pass And Rush Context

- `rush_attempt`: Whether the play counts as a rushing attempt.
- `pass_attempt`: Whether the play counts as a pass attempt.
- `qb_dropback`: Whether the quarterback dropped back to pass. This can include sacks and scrambles that are not ordinary pass attempts.
- `complete_pass`: Whether the pass was completed.
- `incomplete_pass`: Whether the pass was incomplete.
- `shotgun`: Whether the offense aligned in shotgun.
- `no_huddle`: Whether the offense operated without a huddle.
- `qb_scramble`: Whether the quarterback scrambled.
- `qb_kneel`: Whether the play was a quarterback kneel.
- `qb_spike`: Whether the play was a quarterback spike.
- `pass_length`: Pass depth bucket, such as short or deep.
- `pass_location`: Pass direction, such as left, middle, or right.
- `air_yards`: Distance the pass traveled beyond the line of scrimmage. Negative values represent targets behind the line.
- `yards_after_catch`: Yards gained by the receiver after the catch.
- `run_location`: Rush direction, such as left, middle, or right.
- `run_gap`: Rushing lane or gap when available.
- `passing_yards`: Passing yards credited on the play.
- `receiving_yards`: Receiving yards credited on the play.
- `rushing_yards`: Rushing yards credited on the play.

## Players

- `passer_player_id` and `passer_player_name`: Player credited as the passer.
- `receiver_player_id` and `receiver_player_name`: Targeted or credited receiver.
- `rusher_player_id` and `rusher_player_name`: Player credited as the rusher.
- `lateral_receiver_player_id`, `lateral_receiver_player_name`, and `lateral_receiving_yards`: Receiver and yards credited after a lateral.
- `lateral_rusher_player_id`, `lateral_rusher_player_name`, and `lateral_rushing_yards`: Rusher and yards credited after a lateral.

Player names are abbreviated by the source, for example `J.Allen`. Prefer
player IDs for identity and grouping because names are not guaranteed unique.

## Special Teams

- `special_teams_play`: Whether the row is a special-teams play.
- `kickoff_attempt`, `punt_attempt`, `field_goal_attempt`, `extra_point_attempt`, and `two_point_attempt`: Attempt-type flags.
- `field_goal_result`, `extra_point_result`, and `two_point_conv_result`: Outcome of the corresponding scoring attempt.
- `kick_distance`: Kick distance in yards.
- `return_team`: Team credited with the return.
- `return_yards`: Return yards gained.

## Drive Context

- `drive_play_count`: Number of plays in the drive.
- `drive_time_of_possession`: Drive possession time.
- `drive_first_downs`: First downs gained during the drive.
- `drive_inside20`: Whether the drive reached the opponent's 20-yard line.
- `drive_ended_with_score`: Whether the drive ended with a score.
- `drive_quarter_start` and `drive_quarter_end`: Starting and ending quarters.
- `drive_start_transition` and `drive_end_transition`: How possession began and ended.
- `drive_game_clock_start` and `drive_game_clock_end`: Clock at the beginning and end of the drive.
- `drive_start_yard_line` and `drive_end_yard_line`: Starting and ending field positions.

## Analytical Metrics

- `ep`: Expected points for the possession team before the play.
- `epa`: Expected points added by the play from the possession team's perspective. Positive EPA benefits the offense; negative EPA benefits the defense.
- `qb_epa`: EPA attributed to the quarterback on the play.
- `wp`: Possession-team win probability before the play, represented from `0` to `1`.
- `wpa`: Change in possession-team win probability caused by the play. Positive WPA benefits the possession team.
- `home_wp`: Home-team win probability.
- `away_wp`: Away-team win probability.
- `success`: Whether the play meets nflverse's EPA-based success definition.
- `cp`: Model-estimated completion probability for a pass.
- `cpoe`: Completion percentage over expected for a pass.
- `xpass`: Model-estimated probability that the offense would pass.
- `pass_oe`: Pass decision over expected, relative to `xpass`.

EPA and WPA are additive, so use `SUM(epa)` or `SUM(wpa)` to measure total
impact. Rates such as EPA per play, success rate, CP, and CPOE generally use
`AVG(...)` over the relevant plays.

## Derived Fields

These fields are added by this project's cleaning pipeline:

- `turnover`: `1` when the play contains an interception or lost fumble.
- `third_down_attempt`: `1` when the play started on third down.
- `red_zone_play`: `1` when the possession team started at or inside the opponent's 20-yard line.
- `explosive_play`: `1` for a pass gaining at least 20 yards or a rush gaining at least 10 yards.

## Storage And Access

- Raw: `data/raw/nfl_play_by_play_<season>_raw.parquet`
- Processed: `data/processed/nfl_plays_<season>.parquet`
- Approved DuckDB view: `nfl_plays`

Runtime-generated SQL can query only the approved processed view. Raw files are
recoverable ingestion inputs and are not exposed to generated SQL.

## Design Rules

- Keep source identifiers and team-neutral semantics intact.
- Keep processed column order and types compatible across seasons.
- Handle missing values explicitly; null often means a field did not apply to that play.
- Fail cleaning when required processed columns are missing.
- Store datasets with different grains, such as weekly player or team statistics, separately rather than widening this play-level table.
