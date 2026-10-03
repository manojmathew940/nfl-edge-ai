# NFL AI Analyst Roadmap

## Purpose

Build an NFL-wide analytics application that answers questions from approved,
inspectable NFL datasets. LLMs may select data, generate SQL, and explain
results, but Python code validates and executes every query.

When available data cannot answer a question, the application should describe
the missing evidence instead of inventing an answer.

## Target Architecture

1. Validate the user's question.
2. Select the relevant approved dataset or datasets.
3. Generate SQL from documented schemas and join rules.
4. Validate the SQL as one read-only query.
5. Execute it in DuckDB with limits.
6. Build an evidence packet from the executed query and rows.
7. Generate a concise answer grounded in that evidence.
8. Return the answer with the selected data, SQL, validation status, and rows.

The current application combines data extraction and SQL generation in one LLM
call. Dataset selection becomes a separate call once the approved schemas no
longer fit comfortably in one prompt (see Phase 4).

## Phase 1: League-Wide Play Data (complete)

- Ingest complete nflverse play-by-play seasons.
- Clean them into `nfl_plays_<season>.parquet`.
- Preserve neutral possession, defense, home, away, and score semantics.
- Expose only the approved `nfl_plays` DuckDB view.
- Document the schema and keep SQL validation read-only.

Questions include situational EPA, success rate, play calling, drive outcomes,
turnovers, explosive plays, and team comparisons.

## Phase 2: Weekly Player Data (complete)

- Add nflverse weekly player statistics as `nfl_player_weekly`.
- Preserve player, game, team, opponent, season, and week identifiers.
- Cover documented passing, rushing, receiving, kicking, and defensive stats.
- Define joins and metric semantics explicitly.

This phase enables reliable player rankings and comparisons that cannot be
answered completely from credited play participants alone.

## Phase 3: Weekly Team Data

- Add nflverse weekly team statistics as `nfl_team_weekly`.
- Support standardized team rankings and trends without reconstructing every
  summary from play rows.
- Define joins through game and team identifiers.

## Phase 4: Dataset Selection (when triggered)

The current two-call flow stays while every approved schema fits comfortably
in one prompt: the data extraction call sees all schema guides and writes SQL,
and the answering call explains the evidence. A separate selection call adds
latency and a failure mode the SQL call cannot recover from, so add it only
when one of these triggers occurs:

- The combined schema guides exceed about half the configured LLM context.
- Debug logs show wrong-dataset or wrong-column SQL errors.

Then split the flow into three calls:

- LLM call 1 selects one or more approved datasets from a compact catalog.
- Python validates the selection and loads only the selected schemas.
- LLM call 2 generates one SQL query.
- Python validates and executes the query and builds the evidence packet.
- LLM call 3 explains only what the evidence supports.

SQL repair is deferred until the basic three-call flow is stable.

## Later Data Expansion

Add datasets in response to logged question gaps rather than loading every
available source:

1. Snap counts for workload and production per snap.
2. Games and schedules for results, rest, location, and future matchups.
3. Canonical players for identity and cross-provider ID mapping.
4. Weekly rosters for membership and status.
5. Next Gen Stats for expected and tracking-derived metrics.
6. Participation or FTN charting for personnel, formations, motion, pressure,
   and coverage.

Each addition requires a documented grain, source, stable keys, join rules,
Parquet output, approved view, schema guide, and tests.

## LangGraph Adoption

Keep the first three-LLM workflow in ordinary Python. Consider LangGraph only
when real orchestration requirements appear, such as a bounded SQL repair loop,
parallel dataset queries, checkpointing, human approval, persistent
conversation state, or step-level streaming.

LangGraph may coordinate existing tested functions; it must not replace
Pydantic validation, SQL guardrails, DuckDB execution, or approved dataset
metadata.

## Data Policy

- Runtime analytics query processed, approved views only.
- Raw source files remain recoverable ingestion inputs.
- Every data-backed response exposes its query and evidence.
- Different grains remain in separate datasets.
- Source attribution and availability limitations are documented per dataset.
