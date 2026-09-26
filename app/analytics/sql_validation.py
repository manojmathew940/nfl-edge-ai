from __future__ import annotations

from dataclasses import dataclass

from sqlglot import exp, parse
from sqlglot.errors import ParseError

from app.data_foundation.datasets import approved_view_names


APPROVED_ANALYTICS_VIEWS = approved_view_names()
BLOCKED_EXPRESSIONS = (
    exp.Alter,
    exp.Attach,
    exp.Command,
    exp.Copy,
    exp.Create,
    exp.Delete,
    exp.Drop,
    exp.Insert,
    exp.LoadData,
    exp.Merge,
    exp.Update,
)
BLOCKED_FUNCTIONS = {"readparquet", "readcsv", "readjson", "readtext"}


@dataclass(frozen=True)
class SqlValidationResult:
    is_valid: bool
    sql: str
    reason: str


def validate_analytics_sql(sql: str) -> SqlValidationResult:
    normalized_sql = sql.strip()
    if not normalized_sql:
        return invalid(sql, "SQL is empty.")

    try:
        statements = parse(normalized_sql, read="duckdb")
    except ParseError as error:
        return invalid(sql, f"SQL could not be parsed: {error}.")

    statements = [statement for statement in statements if statement is not None]
    if len(statements) != 1:
        return invalid(sql, "SQL must contain exactly one statement.")

    statement = statements[0]
    if not is_select_query(statement):
        return invalid(sql, "SQL must be a SELECT query.")

    blocked_expression = first_blocked_expression(statement)
    if blocked_expression is not None:
        return invalid(sql, f"SQL contains blocked expression: {blocked_expression.key}.")

    blocked_function = first_blocked_function(statement)
    if blocked_function is not None:
        return invalid(sql, f"SQL contains blocked function: {blocked_function}.")

    unknown_tables = sorted(
        table
        for table in table_names(statement)
        if table not in APPROVED_ANALYTICS_VIEWS and table not in cte_names(statement)
    )
    if unknown_tables:
        return invalid(sql, "SQL references unapproved table or view: " + ", ".join(unknown_tables) + ".")

    return SqlValidationResult(is_valid=True, sql=normalized_sql, reason="SQL is valid.")


def is_select_query(statement: exp.Expression) -> bool:
    return isinstance(statement, exp.Select) or (
        isinstance(statement, exp.With) and isinstance(statement.this, exp.Select)
    )


def first_blocked_expression(statement: exp.Expression) -> exp.Expression | None:
    for expression in statement.walk():
        if isinstance(expression, BLOCKED_EXPRESSIONS):
            return expression
    return None


def first_blocked_function(statement: exp.Expression) -> str | None:
    for expression in statement.find_all(exp.Func):
        function_name = expression.__class__.__name__.lower()
        if function_name in BLOCKED_FUNCTIONS:
            return function_name
    return None


def table_names(statement: exp.Expression) -> set[str]:
    return {table.name for table in statement.find_all(exp.Table) if table.name}


def cte_names(statement: exp.Expression) -> set[str]:
    names = set()
    for cte in statement.find_all(exp.CTE):
        alias = cte.alias
        if alias:
            names.add(alias)
    return names


def invalid(sql: str, reason: str) -> SqlValidationResult:
    return SqlValidationResult(is_valid=False, sql=sql.strip(), reason=reason)
