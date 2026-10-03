# NFL Data Analyst Expansion Plan

## Goal

Evolve the project from a Buffalo Bills analyst into an NFL-wide analytics
assistant. Every analytical answer must be grounded in data returned from an
approved NFL dataset. If the available data cannot answer a question, the app
must state that limitation instead of producing an unsupported answer.

Keep one DuckDB analytics layer over separate Parquet datasets and approved SQL
views. Each dataset should retain its natural grain rather than being merged
into one oversized table.

## Phase 1: Replace `bills_plays` With `nfl_plays`

Make league-wide play-by-play the primary analytics source.

1. Update ingestion to retain every NFL game instead of filtering for `BUF`.
2. Save raw and processed files with generic names:
   - `nfl_play_by_play_<season>_raw.parquet`
   - `nfl_plays_<season>.parquet`
3. Replace Bills-perspective fields with neutral football fields based on the
   possession team, defensive team, home team, and away team.
4. Preserve useful derived fields such as turnovers, third-down attempts, red
   zone plays, and explosive plays when they are team-neutral.
5. Create an approved DuckDB view named `nfl_plays`.
6. Update SQL validation, schema metadata, prompts, tests, documentation, and
   UI language to use `nfl_plays`.
7. Remove Bills-only assumptions such as `bills_on_offense`, `opponent`, and
   `bills_score_before`. Do not retain a `bills_plays` compatibility view.

Questions unlocked:

- What was Kansas City's EPA on third-and-long in the fourth quarter?
- Which teams were most successful in the red zone?
- How did offenses perform against Buffalo compared with the league average?

## Phase 2: Add `nfl_player_weekly`

Status: complete. Both schemas are in the current extraction prompt until
Phase 3 adds dataset selection.

Add league-wide weekly player statistics as a separate approved view.

1. Download the current nflverse `stats_player` weekly Parquet files.
2. Store one processed file per season with one row per player and game/week.
3. Preserve stable identifiers such as `player_id`, `game_id`, `season`,
   `week`, `team`, and `opponent_team`.
4. Include documented passing, rushing, receiving, kicking, and defensive
   statistics.
5. Add schema metadata describing metric definitions and valid comparisons.
6. Create and approve the `nfl_player_weekly` DuckDB view.
7. Add ingestion, schema compatibility, SQL validation, and query tests.

Questions unlocked:

- How did Josh Allen compare with other quarterbacks in passing EPA and CPOE?
- Which receivers generated the most yards per target?
- Which defenders recorded the most sacks, QB hits, or tackles over a selected
  span?

## Phase 3: Introduce The Three-LLM Query Architecture

Replace the single-schema extraction workflow with dataset selection, focused
SQL generation, and grounded answer generation.

### Normal Request Flow

1. **Python:** Validate the API request with Pydantic.
2. **LLM call 1 - Dataset selector:** Choose one or more relevant approved
   datasets from a compact catalog and explain the selection.
3. **Python:** Validate the selected dataset names and load only their detailed
   schemas and documented join rules.
4. **LLM call 2 - SQL generator:** Generate one SQL query using only the
   selected schemas.
5. **Python:** Validate the SQL with `sqlglot`.
6. **Python:** Execute valid read-only SQL in DuckDB with row and execution
   limits.
7. **Python:** Build an evidence packet containing the question, selected
   datasets, SQL, validation result, columns, and rows.
8. **LLM call 3 - Answer generator:** Explain only what the evidence packet
   supports.
9. **Python:** Validate and serialize the API response, including visible
   grounding information.

### Dataset Selector Output

```json
{
  "tables": ["nfl_plays"],
  "reason": "The question requires down, distance, and quarter-level data."
}
```

### Guardrails

- Permit only approved views and documented joins.
- Reject writes, multiple statements, unknown tables, blocked functions, and
  accidental cross joins.
- Require result row limits and execution limits.
- Do not allow the answer LLM to replace missing evidence with general
  knowledge.
- If no approved dataset can answer the question, return a clear data
  limitation response.
- If SQL returns no rows, report that no matching data was found.
- Add at most one bounded SQL repair call later, after the basic flow is stable.

## Phase 4: Add `nfl_team_weekly`

Add standardized weekly team statistics for efficient rankings and trends.

1. Download the current nflverse `stats_team` weekly Parquet files.
2. Store one row per team and game/week.
3. Preserve `game_id`, `season`, `week`, `team`, `opponent_team`, and
   `season_type` as core keys.
4. Create and approve the `nfl_team_weekly` DuckDB view.
5. Document where team metrics differ from aggregations over `nfl_plays`.
6. Define joins to `nfl_plays` through `game_id` and team identifiers.
7. Add dataset-selection, SQL generation, and cross-view query tests.

Questions unlocked:

- Which teams improved the most after Week 8?
- Where did Buffalo rank in offensive EPA per game?
- Which offenses were strongest against top-ranked defenses?

## Phase 5: Add Further Datasets Based On Question Gaps

Do not add every available nflverse dataset automatically. Record questions
that the approved views cannot answer, group them by missing evidence, and add
the dataset that closes the largest useful gap.

Likely candidates:

1. `nfl_snap_counts` for playing time, workload, and production-per-snap.
2. `nfl_games` for schedules, results, rest, location, and opponent context.
3. `nfl_players` for canonical player identity, position, experience, and ID
   mapping across sources.
4. `nfl_rosters_weekly` for weekly team membership and roster status.
5. Next Gen Stats for expected rushing, separation, and passing metrics.
6. Participation or FTN charting for personnel, formations, motion, pressure,
   and coverage.

Every new dataset must include:

- a documented row grain and source;
- stable keys and explicit join rules;
- processed Parquet output and source metadata;
- an approved DuckDB view and schema guide;
- SQL validation coverage;
- representative questions and tests;
- any required attribution or availability limitations.

## Conditional Phase 6: Adopt LangGraph When Orchestration Requires It

Do not use LangGraph for the initial three-LLM workflow. Implement that workflow
as explicit Python functions first so its inputs, outputs, failures, latency,
and tests are understood before adding an orchestration framework.

Consider adopting LangGraph only when at least one of these requirements is
real and scheduled for implementation:

- a bounded SQL validation and repair loop;
- parallel queries against multiple datasets followed by result synthesis;
- request checkpointing and resumption after a failed step;
- human review or approval before continuing a workflow;
- persistent conversation state across related analytical questions;
- streaming step-level progress to the UI;
- branching that has become difficult to understand and test in normal Python.

Do not adopt LangGraph solely because the request contains three LLM calls or
to replace straightforward sequential function calls.

### Migration Approach

1. Keep dataset selection, schema loading, SQL generation, SQL validation,
   DuckDB execution, evidence construction, and answer generation as separate,
   tested Python functions.
2. Define a typed graph state containing the question, selected datasets,
   schemas, generated SQL, validation result, repair count, query result,
   evidence packet, and answer.
3. Wrap the existing Python functions as graph nodes without moving domain
   logic into the graph definition.
4. Add conditional edges only for behavior that requires branching, such as
   valid SQL versus one bounded repair attempt.
5. Keep SQL validation and execution deterministic. LangGraph may coordinate
   these steps but must not weaken the approved-view or read-only boundaries.
6. Compare the graph implementation with the plain-Python baseline for
   readability, testability, latency, observability, and failure recovery.
7. Retain LangGraph only if it provides a measurable improvement in at least
   one of those areas.

The first suitable LangGraph learning milestone is the bounded SQL repair
workflow:

```text
generate SQL
     |
     v
validate SQL ---- valid ----> execute SQL ----> build evidence ----> answer
     |
   invalid
     |
     v
repair SQL ---- retry limit not reached ----> validate SQL
     |
 retry limit reached
     |
     v
return validation failure
```

LangGraph should orchestrate the workflow only. Pydantic models, `sqlglot`
validation, DuckDB execution, approved dataset metadata, and FastAPI response
models remain owned by the application.

## API Response Requirements

Every data-backed response should expose:

- answer text;
- selected datasets and selection reason;
- generated SQL;
- SQL validation status and reason;
- returned columns and rows;
- row limit;
- grounding status;
- optional debug payload when enabled.

Suggested grounding states:

- `Data-backed answer`
- `No matching data`
- `Available data cannot answer this question`
- `Data query failed validation`
- `Data source unavailable`

## Verification Strategy

For each phase:

1. Test ingestion validation, source metadata, and file naming.
2. Test schema compatibility across seasons.
3. Test DuckDB view creation and representative queries.
4. Test selection of the correct dataset or dataset combination.
5. Test approved and rejected SQL, including invalid joins.
6. Test that answer prompts contain the executed evidence.
7. Test that insufficient-data paths do not produce unsupported answers.
8. Run the full test suite before moving to the next dataset.
