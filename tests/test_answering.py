from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from openai import OpenAIError

from app.analytics.sql_execution import AnalyticsSqlResult
from app.llm.answering import (
    ANSWER_QUESTION_INSTRUCTIONS,
    LLM_REASONING,
    LLMServiceError,
    _render_answer_question_prompt,
    answer_question,
    build_answer_debug_payload,
)
from app.llm.data_extraction import DataExtractionDecision


NO_DATA_DECISION = DataExtractionDecision(
    needs_data=False,
    sql=None,
    reason="No local data needed.",
    confidence=0.6,
    data_not_needed_reason="The question is general.",
)


def mock_client(response: Mock) -> Mock:
    client = Mock()
    client.responses.create.return_value = response
    return client


class AnsweringTest(unittest.TestCase):
    def test_render_prompt_includes_valid_sql_result(self) -> None:
        decision = DataExtractionDecision(
            needs_data=True,
            sql="SELECT season, AVG(epa) AS avg_epa FROM nfl_plays GROUP BY season",
            reason="The question asks for an EPA trend.",
            confidence=0.8,
            data_not_needed_reason=None,
        )
        result = AnalyticsSqlResult(
            is_valid=True,
            validation_reason="SQL is valid.",
            columns=["season", "avg_epa"],
            rows=[{"season": 2023, "avg_epa": 0.12}],
        )

        prompt = _render_answer_question_prompt(
            "How did the Bills offense perform?",
            decision,
            result,
        )

        self.assertIn("Question:\nHow did the Bills offense perform?", prompt)
        self.assertIn("Local analytics context JSON:", prompt)
        self.assertIn('"status": "local_analytics_data_available"', prompt)
        self.assertIn('"columns": [', prompt)
        self.assertIn('"row_count": 1', prompt)
        self.assertIn('"avg_epa": 0.12', prompt)
        self.assertNotIn("Data extraction decision JSON:", prompt)
        self.assertNotIn("SELECT season", prompt)
        self.assertNotIn("validation_reason", prompt)

    def test_instructions_prefer_tables_for_multi_row_results(self) -> None:
        self.assertIn("NFL football analyst", ANSWER_QUESTION_INSTRUCTIONS)
        self.assertIn("Markdown table", ANSWER_QUESTION_INSTRUCTIONS)
        self.assertIn("Preserve the returned row ordering", ANSWER_QUESTION_INSTRUCTIONS)
        self.assertIn("ranked or grouped result sets", ANSWER_QUESTION_INSTRUCTIONS)

    def test_render_prompt_includes_no_data_state(self) -> None:
        decision = DataExtractionDecision(
            needs_data=False,
            sql=None,
            reason="The question asks about current injuries.",
            confidence=0.9,
            data_not_needed_reason="Local play data does not include injuries.",
        )

        prompt = _render_answer_question_prompt(
            "Is the quarterback injured?",
            decision,
            None,
        )

        self.assertIn('"status": "no_local_analytics_data_requested"', prompt)
        self.assertIn('"reason": "Local play data does not include injuries."', prompt)
        self.assertIn('"result": null', prompt)
        self.assertNotIn("Data extraction decision JSON:", prompt)

    def test_invalid_sql_result_raises_before_llm_call(self) -> None:
        decision = DataExtractionDecision(
            needs_data=True,
            sql="SELECT * FROM unapproved_table",
            reason="The question asks for local data.",
            confidence=0.7,
            data_not_needed_reason=None,
        )
        result = AnalyticsSqlResult(
            is_valid=False,
            validation_reason="SQL references unapproved table or view: unapproved_table.",
            columns=[],
            rows=[],
        )

        with patch("app.llm.answering.build_llm_client") as build_client:
            with self.assertRaisesRegex(ValueError, "Invalid SQL results"):
                answer_question("How did they do?", decision, result, provider="local")

        build_client.assert_not_called()

    def test_missing_result_when_data_needed_raises_before_llm_call(self) -> None:
        decision = DataExtractionDecision(
            needs_data=True,
            sql="SELECT COUNT(*) AS plays FROM nfl_plays",
            reason="The question asks for local data.",
            confidence=0.7,
            data_not_needed_reason=None,
        )

        with patch("app.llm.answering.build_llm_client") as build_client:
            with self.assertRaisesRegex(ValueError, "analytics_result is required"):
                answer_question("How many plays?", decision, None, provider="local")

        build_client.assert_not_called()

    @patch("app.llm.answering.get_llm_model", return_value="test-model")
    @patch("app.llm.answering.build_llm_client")
    def test_answer_question_calls_llm(
        self,
        build_client: Mock,
        get_model: Mock,
    ) -> None:
        decision = DataExtractionDecision(
            needs_data=False,
            sql=None,
            reason="No local data needed.",
            confidence=0.6,
            data_not_needed_reason="The question is general.",
        )
        response = Mock(output_text="A concise answer.")
        client = Mock()
        client.responses.create.return_value = response
        build_client.return_value = client

        answer = answer_question("Who are the Bills?", decision, None, provider="local")

        self.assertEqual(answer, "A concise answer.")
        build_client.assert_called_once_with("local")
        get_model.assert_called_once_with("local")
        client.responses.create.assert_called_once()
        call_kwargs = client.responses.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "test-model")
        self.assertEqual(call_kwargs["instructions"], ANSWER_QUESTION_INSTRUCTIONS)
        self.assertIn("Question:\nWho are the Bills?", call_kwargs["input"])
        self.assertNotIn("reasoning", call_kwargs)

    @patch("app.llm.answering.get_llm_model", return_value="test-model")
    @patch("app.llm.answering.build_llm_client")
    def test_answer_question_sends_low_reasoning_to_openai(
        self, build_client: Mock, get_model: Mock
    ) -> None:
        client = mock_client(Mock(incomplete_details=None, output_text="Answer."))
        build_client.return_value = client

        answer_question("Who are the Bills?", NO_DATA_DECISION, None, provider="openai")

        call_kwargs = client.responses.create.call_args.kwargs
        self.assertEqual(call_kwargs["reasoning"], LLM_REASONING)
        self.assertEqual(call_kwargs["max_output_tokens"], 2000)

    @patch("app.llm.answering.get_llm_model", return_value="test-model")
    @patch("app.llm.answering.build_llm_client")
    def test_answer_question_raises_when_token_budget_runs_out(
        self, build_client: Mock, get_model: Mock
    ) -> None:
        build_client.return_value = mock_client(
            Mock(incomplete_details={"reason": "max_output_tokens"}, output_text="")
        )

        with self.assertRaisesRegex(LLMServiceError, "answer.*max_output_tokens"):
            answer_question("Who are the Bills?", NO_DATA_DECISION, None, provider="openai")

    @patch("app.llm.answering.get_llm_model", return_value="test-model")
    @patch("app.llm.answering.build_llm_client")
    def test_answer_question_raises_on_empty_answer(
        self, build_client: Mock, get_model: Mock
    ) -> None:
        build_client.return_value = mock_client(
            Mock(incomplete_details=None, output_text="  ")
        )

        with self.assertRaisesRegex(LLMServiceError, "empty answer"):
            answer_question("Who are the Bills?", NO_DATA_DECISION, None, provider="local")

    @patch("app.llm.answering.get_llm_model", return_value="test-model")
    @patch("app.llm.answering.build_llm_client")
    def test_answer_question_wraps_provider_errors(
        self,
        build_client: Mock,
        get_model: Mock,
    ) -> None:
        decision = DataExtractionDecision(
            needs_data=False,
            sql=None,
            reason="No local data needed.",
            confidence=0.6,
            data_not_needed_reason="The question is general.",
        )
        client = Mock()
        client.responses.create.side_effect = OpenAIError("boom")
        build_client.return_value = client

        with self.assertRaisesRegex(LLMServiceError, "failed to answer"):
            answer_question("Who are the Bills?", decision, None, provider="local")

        get_model.assert_called_once_with("local")

    @patch("app.llm.answering.get_llm_base_url", return_value="http://test")
    @patch("app.llm.answering.get_llm_model", return_value="test-model")
    def test_build_answer_debug_payload(self, get_model: Mock, get_base_url: Mock) -> None:
        decision = DataExtractionDecision(
            needs_data=False,
            sql=None,
            reason="No local data needed.",
            confidence=0.6,
            data_not_needed_reason="The question is general.",
        )

        payload = build_answer_debug_payload(
            "Who are the Bills?",
            decision,
            None,
            provider="local",
        )

        self.assertEqual(payload["provider"], "local")
        self.assertEqual(payload["model"], "test-model")
        self.assertEqual(payload["base_url"], "http://test")
        self.assertEqual(payload["instructions"], ANSWER_QUESTION_INSTRUCTIONS)
        self.assertIn("Question:\nWho are the Bills?", payload["input"])
        self.assertEqual(payload["max_output_tokens"], 2000)
        self.assertNotIn("reasoning", payload)
        get_model.assert_called_once_with("local")
        get_base_url.assert_called_with("local")


if __name__ == "__main__":
    unittest.main()
