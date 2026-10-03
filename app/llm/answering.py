from __future__ import annotations

import json
import os
from typing import Any, TYPE_CHECKING

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

from app.analytics.sql_execution import AnalyticsSqlResult

if TYPE_CHECKING:
    from app.llm.data_extraction import DataExtractionDecision


DEFAULT_MODEL = "gpt-5.5"
DEFAULT_API_KEY = "ollama"
DEFAULT_LOCAL_BASE_URL = "http://127.0.0.1:11434/v1"
DEFAULT_LOCAL_MODEL = "qwen2.5:7b-instruct"
MAX_ANSWER_OUTPUT_TOKENS = 2000
LLM_REASONING = {"effort": "low"}

ANSWER_QUESTION_INSTRUCTIONS = """
You are an NFL football analyst.

Answer the user's question using only the supplied local analytics data when it
is present. If no local analytics data was requested, answer directly only when
the question can be answered without local data or current outside context.

If the supplied data is empty or insufficient, say what is missing. Do not
invent current news, injuries, quotes, roster moves, reporting, play details, or
other context that was not provided.

When the analytics result contains multiple rows with comparable columns,
present the result as a Markdown table. Preserve the returned row ordering. Do
not convert ranked or grouped result sets into prose lists.

Be clear about direct evidence from the data versus interpretation. Keep the
answer concise and specific.
""".strip()


class LLMConfigurationError(RuntimeError):
    """Raised when the LLM client is not configured."""


class LLMServiceError(RuntimeError):
    """Raised when the LLM provider call fails."""


def get_llm_model(provider: str | None = None) -> str:
    if provider == "local":
        return os.getenv("LOCAL_LLM_MODEL") or os.getenv("LLM_MODEL") or DEFAULT_LOCAL_MODEL

    if provider == "openai":
        return os.getenv("OPENAI_LLM_MODEL") or DEFAULT_MODEL

    return os.getenv("LLM_MODEL", DEFAULT_MODEL)


def get_llm_base_url(provider: str | None = None) -> str | None:
    if provider == "local":
        return os.getenv("LOCAL_LLM_BASE_URL") or os.getenv("LLM_BASE_URL") or DEFAULT_LOCAL_BASE_URL

    if provider == "openai":
        return None

    return os.getenv("LLM_BASE_URL") or None


def get_llm_api_key(provider: str | None = None) -> str | None:
    if provider == "local":
        return os.getenv("LOCAL_LLM_API_KEY") or os.getenv("LLM_API_KEY") or DEFAULT_API_KEY

    if provider == "openai":
        return os.getenv("OPENAI_API_KEY")

    if get_llm_base_url():
        return os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or DEFAULT_API_KEY

    return os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")


def reasoning_options(provider: str | None = None) -> dict[str, Any]:
    """Reasoning settings for a Responses API call.

    Only OpenAI gets them. Local servers such as Ollama reject the setting for
    models that do not support thinking.
    """
    if get_llm_base_url(provider):
        return {}
    return {"reasoning": LLM_REASONING}


def raise_if_response_incomplete(response: Any, step: str) -> None:
    """Raise when the model stopped early, e.g. after spending its token budget."""
    incomplete_details = getattr(response, "incomplete_details", None)
    if incomplete_details is None:
        return

    reason = getattr(incomplete_details, "reason", None)
    if reason is None and isinstance(incomplete_details, dict):
        reason = incomplete_details.get("reason")

    if isinstance(reason, str) and reason:
        raise LLMServiceError(
            f"The LLM {step} returned an incomplete response. Reason: {reason}."
        )


def build_llm_client(provider: str | None = None) -> OpenAI:
    api_key = get_llm_api_key(provider)
    base_url = get_llm_base_url(provider)

    if not api_key:
        raise LLMConfigurationError(
            "LLM answering is not configured. Set OPENAI_API_KEY for OpenAI, "
            "or set LLM_BASE_URL and LLM_MODEL for a local provider such as Ollama."
        )

    client_options = {"api_key": api_key}
    if base_url:
        client_options["base_url"] = base_url

    return OpenAI(**client_options)


def answer_question(
    question: str,
    extraction_decision: DataExtractionDecision,
    analytics_result: AnalyticsSqlResult | None,
    *,
    provider: str | None = None,
) -> str:
    load_dotenv()

    _validate_answer_question_inputs(extraction_decision, analytics_result)

    client = build_llm_client(provider)
    prompt = _render_answer_question_prompt(
        question,
        extraction_decision,
        analytics_result,
    )
    model = get_llm_model(provider)

    try:
        response = client.responses.create(
            model=model,
            instructions=ANSWER_QUESTION_INSTRUCTIONS,
            input=prompt,
            max_output_tokens=MAX_ANSWER_OUTPUT_TOKENS,
            **reasoning_options(provider),
        )
    except OpenAIError as error:
        raise LLMServiceError("The LLM service failed to answer the question.") from error

    raise_if_response_incomplete(response, "answer")
    if not response.output_text.strip():
        raise LLMServiceError("The LLM returned an empty answer.")

    return response.output_text


def _render_answer_question_prompt(
    question: str,
    extraction_decision: DataExtractionDecision,
    analytics_result: AnalyticsSqlResult | None,
) -> str:
    _validate_answer_question_inputs(extraction_decision, analytics_result)

    analytics_context_json = json.dumps(
        _renderable_analytics_context(extraction_decision, analytics_result),
        indent=2,
        sort_keys=True,
    )

    return (
        f"Question:\n{question}\n\n"
        "Local analytics context JSON:\n"
        f"{analytics_context_json}"
    )


def build_answer_debug_payload(
    question: str,
    extraction_decision: DataExtractionDecision,
    analytics_result: AnalyticsSqlResult | None,
    *,
    provider: str | None = None,
) -> dict[str, Any]:
    load_dotenv()

    return {
        "provider": provider or ("local" if get_llm_base_url() else "openai"),
        "model": get_llm_model(provider),
        "base_url": get_llm_base_url(provider),
        "instructions": ANSWER_QUESTION_INSTRUCTIONS,
        "input": _render_answer_question_prompt(
            question,
            extraction_decision,
            analytics_result,
        ),
        "max_output_tokens": MAX_ANSWER_OUTPUT_TOKENS,
        **reasoning_options(provider),
    }


def _validate_answer_question_inputs(
    extraction_decision: DataExtractionDecision,
    analytics_result: AnalyticsSqlResult | None,
) -> None:
    if analytics_result is None:
        if extraction_decision.needs_data:
            raise ValueError(
                "analytics_result is required when extraction_decision.needs_data is true."
            )
        return

    if not analytics_result.is_valid:
        raise ValueError("Invalid SQL results must be handled before answer generation.")


def _renderable_analytics_context(
    extraction_decision: DataExtractionDecision,
    analytics_result: AnalyticsSqlResult | None,
) -> dict[str, Any]:
    if analytics_result is None:
        return {
            "status": "no_local_analytics_data_requested",
            "reason": extraction_decision.data_not_needed_reason
            or extraction_decision.reason,
            "result": None,
        }

    return {
        "status": "local_analytics_data_available",
        "result": {
            "columns": analytics_result.columns,
            "rows": analytics_result.rows,
            "row_count": len(analytics_result.rows),
        },
    }
