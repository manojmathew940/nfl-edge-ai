import os
from typing import Any

from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.analytics.sql_execution import (
    DEFAULT_SQL_ROW_LIMIT,
    AnalyticsSqlResult,
    validate_and_execute_analytics_sql,
)
from app.analytics.sql_views import AnalyticsViewError
from app.llm.answering import (
    LLMConfigurationError,
    LLMServiceError,
    answer_question,
    build_answer_debug_payload,
)
from app.llm.data_extraction import (
    DataExtractionDecision,
    build_data_extraction_debug_payload,
    run_data_extraction_llm,
)


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    provider: str = Field(default="openai", pattern="^(openai|local)$")


class AskResponse(BaseModel):
    answer: str
    provider: str
    data_request: dict[str, Any]
    analytics: dict[str, Any]
    debug_payload: dict[str, Any] | None = None


def is_llm_debug_enabled() -> bool:
    enabled_values = {"1", "true", "yes", "on"}
    return (
        os.getenv("NFL_AI_DEBUG_PAYLOAD", "").lower() in enabled_values
        or os.getenv("NFL_AI_DEBUG_PROMPT", "").lower() in enabled_values
    )

#TODO: Think if this is required or if the AskResponse already covers this info
def build_request_extraction_debug_payload(request: AskRequest) -> dict | None:
    if not is_llm_debug_enabled():
        return None

    return {
        "data_extraction": build_data_extraction_debug_payload(
            request.question,
            provider=request.provider,
        )
    }

#TODO: Think if this is required or if the AskResponse already covers this info
def build_request_answer_debug_payload(
    request: AskRequest,
    extraction_decision: DataExtractionDecision,
    analytics_result: AnalyticsSqlResult | None,
) -> dict | None:
    if not is_llm_debug_enabled():
        return None

    return {
        "data_extraction": build_data_extraction_debug_payload(
            request.question,
            provider=request.provider,
        ),
        "answer": build_answer_debug_payload(
            request.question,
            extraction_decision,
            analytics_result,
            provider=request.provider,
        ),
    }


def raise_llm_http_error(error: Exception, debug_payload: dict | None) -> None:
    detail = {"error": str(error), "debug_payload": debug_payload} if debug_payload else str(error)
    raise HTTPException(status_code=503, detail=detail) from error


def build_analytics_payload(
    sql: str | None,
    analytics_result: AnalyticsSqlResult | None,
    *,
    row_limit: int = DEFAULT_SQL_ROW_LIMIT,
) -> dict:
    if analytics_result is None:
        return {
            "sql": sql,
            "is_valid": None,
            "validation_reason": None,
            "columns": [],
            "rows": [],
            "row_limit": row_limit,
        }

    return {
        "sql": sql,
        "is_valid": analytics_result.is_valid,
        "validation_reason": analytics_result.validation_reason,
        "columns": analytics_result.columns,
        "rows": analytics_result.rows,
        "row_limit": row_limit,
    }


def build_invalid_sql_answer(validation_reason: str) -> str:
    return (
        "I could not query the local analytics data because the generated SQL "
        f"failed validation: {validation_reason}"
    )


app = FastAPI(title="NFL AI Analyst")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
def root():
    return FileResponse("app/static/index.html")


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    try:
        extraction_decision = run_data_extraction_llm(
            request.question,
            provider=request.provider,
        )
    except LLMConfigurationError as error:
        raise_llm_http_error(error, build_request_extraction_debug_payload(request))
    except LLMServiceError as error:
        raise_llm_http_error(error, build_request_extraction_debug_payload(request))

    analytics_result = None
    if extraction_decision.needs_data:
        sql = extraction_decision.sql
        if not sql:
            response = {
                "answer": build_invalid_sql_answer("SQL is empty."),
                "provider": request.provider,
                "data_request": extraction_decision.to_dict(),
                "analytics": build_analytics_payload(
                    sql,
                    AnalyticsSqlResult(
                        is_valid=False,
                        validation_reason="SQL is empty.",
                        columns=[],
                        rows=[],
                    ),
                ),
            }
            debug_payload = build_request_extraction_debug_payload(request)
            if debug_payload:
                response["debug_payload"] = debug_payload
            return response

        try:
            analytics_result = validate_and_execute_analytics_sql(
                sql,
                row_limit=DEFAULT_SQL_ROW_LIMIT,
            )
        except AnalyticsViewError as error:
            raise_llm_http_error(error, build_request_extraction_debug_payload(request))

        if not analytics_result.is_valid:
            response = {
                "answer": build_invalid_sql_answer(analytics_result.validation_reason),
                "provider": request.provider,
                "data_request": extraction_decision.to_dict(),
                "analytics": build_analytics_payload(sql, analytics_result),
            }
            debug_payload = build_request_extraction_debug_payload(request)
            if debug_payload:
                response["debug_payload"] = debug_payload
            return response

    debug_payload = build_request_answer_debug_payload(
        request,
        extraction_decision,
        analytics_result,
    )

    try:
        answer = answer_question(
            request.question,
            extraction_decision,
            analytics_result,
            provider=request.provider,
        )
    except LLMConfigurationError as error:
        raise_llm_http_error(error, debug_payload)
    except LLMServiceError as error:
        raise_llm_http_error(error, debug_payload)

    response = {
        "answer": answer,
        "provider": request.provider,
        "data_request": extraction_decision.to_dict(),
        "analytics": build_analytics_payload(
            extraction_decision.sql,
            analytics_result,
        ),
    }

    if debug_payload:
        response["debug_payload"] = debug_payload

    return response
