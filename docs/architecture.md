# Request Architecture

## Current Flow

The application currently uses two LLM calls. Schema loading, SQL validation,
query execution, and response serialization are deterministic application code.

```mermaid
flowchart TD
    Question([User question])
    API[FastAPI POST /ask]
    Schema[(schemas/*.yaml)]
    SchemaLoader[Python: load and render schema]
    Extractor[LLM 1: data extraction and SQL generation]
    Validator[Python: parse and validate SQL]
    Executor[Python: apply row limit and submit SQL]
    Parquet[(Processed NFL Parquet files)]
    DuckDB[DuckDB query engine]
    Rows[Python: serialize columns and rows]
    Context[Python: build answer context]
    Answer[LLM 2: grounded answer generation]
    Response[Python: build AskResponse]
    Final([Final JSON response])

    Question -->|Question and provider| API
    API -->|Question| SchemaLoader
    Schema -->|Column contract| SchemaLoader
    SchemaLoader -->|Question and rendered schema guide| Extractor

    Extractor -->|Generated SQL when data is needed| Validator
    Validator -->|Approved SQL| Executor

    Executor -->|Bounded SQL query| DuckDB
    Parquet -->|nfl_plays and nfl_player_weekly views| DuckDB
    DuckDB -->|Columns and result rows| Rows

    API -->|Original question| Context
    Extractor -->|Extraction decision| Context
    Rows -->|Serialized analytics rows| Context
    Context -->|Question, decision, and optional rows| Answer
    Answer -->|Answer text| Response
    Validator -.->|Validation failure skips LLM 2| Response
    Response --> Final

    classDef python fill:#e8f1fb,stroke:#2563eb,color:#111827
    classDef llm fill:#f3e8ff,stroke:#7e22ce,color:#111827
    classDef data fill:#ecfdf5,stroke:#059669,color:#111827
    classDef external fill:#ffffff,stroke:#374151,color:#111827

    class API,SchemaLoader,Validator,Executor,Rows,Context,Response python
    class Extractor,Answer llm
    class Schema,Parquet,DuckDB data
    class Question,Final external
```

## Component Responsibilities

| Component | Type | Responsibility |
| --- | --- | --- |
| FastAPI `/ask` | Python | Orchestrates the request and returns a structured response. |
| Schema metadata loader | Python | Converts each dataset schema in `app/data_foundation/schemas/` into an LLM-readable schema guide. |
| Data extractor | LLM call 1 | Decides whether local data is useful and generates one SQL query when needed. |
| SQL validator | Python | Allows a single read-only query against approved analytics views and blocks direct file access. |
| SQL executor | Python | Applies the result limit and submits approved SQL to DuckDB. |
| DuckDB query engine | SQL engine | Creates `nfl_plays` over compatible season Parquet files and runs the bounded query. |
| Parquet files | Data storage | Store processed NFL play data by season. |
| Result serializer | Python | Converts DuckDB columns and rows into the bounded analytics payload. |
| Answer context builder | Python | Combines the question, extraction decision, and optional analytics rows. |
| Answer generator | LLM call 2 | Synthesizes the question, extraction decision, and returned rows into a grounded answer. |

## Data Boundaries

The extractor receives the user question and the YAML schema guide. It does not
query Parquet files directly. Generated SQL must pass the application
guardrails before DuckDB can execute it.

The answer generator does not have database access. It receives the original
question, the extractor decision, and the bounded analytics result. If no local
data is needed, it receives the question and no analytics rows.

Invalid SQL is returned as a structured validation failure without calling the
answer generator. Provider or analytics initialization failures are returned as
service errors.

## Planned Evolution

After multiple datasets are available, the extraction step can be separated
into dataset selection and dataset-specific SQL generation. LangGraph should be
introduced only if the workflow gains useful branching, retries, or persistent
state that becomes difficult to manage with direct Python orchestration. See
`docs/roadmap.md` for the staged plan.
