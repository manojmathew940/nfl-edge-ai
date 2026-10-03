from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import duckdb

from app.analytics.sql_views import AnalyticsViewError, create_analytics_connection
from app.analytics.sql_validation import validate_analytics_sql


DEFAULT_SQL_ROW_LIMIT = 100


@dataclass(frozen=True)
class AnalyticsSqlRows:
    columns: list[str]
    rows: list[dict[str, Any]]


@dataclass(frozen=True)
class AnalyticsSqlResult:
    is_valid: bool
    validation_reason: str
    columns: list[str]
    rows: list[dict[str, Any]]


def _execute_analytics_sql(
    sql: str,
    *,
    row_limit: int = DEFAULT_SQL_ROW_LIMIT,
) -> AnalyticsSqlRows:
    if row_limit < 1:
        raise AnalyticsViewError("row_limit must be at least 1.")

    connection = create_analytics_connection()
    limited_sql = apply_limit(sql, row_limit)
    cursor = connection.execute(limited_sql)
    columns = [column[0] for column in cursor.description]
    rows = cursor.fetchall()

    return AnalyticsSqlRows(
        columns=columns,
        rows=[dict(zip(columns, row)) for row in rows],
    )


def validate_and_execute_analytics_sql(
    sql: str,
    *,
    row_limit: int = DEFAULT_SQL_ROW_LIMIT,
) -> AnalyticsSqlResult:
    validation = validate_analytics_sql(sql)
    if not validation.is_valid:
        return AnalyticsSqlResult(
            is_valid=False,
            validation_reason=validation.reason,
            columns=[],
            rows=[],
        )

    try:
        result = _execute_analytics_sql(validation.sql, row_limit=row_limit)
    except duckdb.Error as error:
        # Validation checks statements and views, not columns or types, so
        # LLM SQL can still fail here (e.g. a column from the other view).
        return AnalyticsSqlResult(
            is_valid=False,
            validation_reason=f"SQL failed to run in DuckDB: {error}",
            columns=[],
            rows=[],
        )
    return AnalyticsSqlResult(
        is_valid=True,
        validation_reason=validation.reason,
        columns=result.columns,
        rows=result.rows,
    )


def apply_limit(sql: str, row_limit: int) -> str:
    stripped = sql.strip().rstrip(";")
    return f"SELECT * FROM ({stripped}) AS analytics_query LIMIT {int(row_limit)}"
