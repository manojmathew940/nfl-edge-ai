from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from openai import OpenAIError

from app.llm.answering import LLM_REASONING, LLMServiceError
from app.llm.data_extraction import (
    _DATA_EXTRACTION_RESPONSE_FORMAT,
    _EXTRACT_DATA_INSTRUCTIONS,
    _print_data_extraction_response_debug,
    _parse_data_extraction_decision,
    _render_data_extraction_prompt,
    run_data_extraction_llm,
)


class DataExtractionTest(unittest.TestCase):
    def test_render_prompt_includes_schema_metadata(self) -> None:
        prompt = _render_data_extraction_prompt("How did the Bills offense perform?")

        self.assertIn(
            "Use the schema below to choose the exact view and column names",
            prompt,
        )
        self.assertIn(
            "Do not reference columns that are not listed in the schema.",
            prompt,
        )
        self.assertIn("Approved view: nfl_plays", prompt)
        self.assertIn("Approved view: nfl_player_weekly", prompt)
        self.assertIn("- passing_cpoe (float):", prompt)
        self.assertIn("- season (integer): NFL season.", prompt)
        self.assertIn(
            "- passer_player_name (string): Player name for the passer.",
            prompt,
        )
        self.assertIn("Question:\nHow did the Bills offense perform?", prompt)
        self.assertNotIn("Example JSON when data is useful", prompt)

    def test_instructions_include_extraction_examples(self) -> None:
        self.assertIn("NFL analytics app", _EXTRACT_DATA_INSTRUCTIONS)
        self.assertIn("posteam = 'BUF'", _EXTRACT_DATA_INSTRUCTIONS)
        self.assertNotIn("bills_on_offense", _EXTRACT_DATA_INSTRUCTIONS)
        self.assertIn("Example JSON when data is useful", _EXTRACT_DATA_INSTRUCTIONS)
        self.assertIn(
            "Example JSON when local data is not useful",
            _EXTRACT_DATA_INSTRUCTIONS,
        )
        self.assertIn("lateral_receiving_yards", _EXTRACT_DATA_INSTRUCTIONS)
        self.assertIn("lateral_receiver_player_name", _EXTRACT_DATA_INSTRUCTIONS)
        self.assertIn("lateral_rushing_yards", _EXTRACT_DATA_INSTRUCTIONS)
        self.assertIn("lateral_rusher_player_name", _EXTRACT_DATA_INSTRUCTIONS)

    @patch("app.llm.data_extraction.get_llm_model", return_value="test-model")
    @patch("app.llm.data_extraction.build_llm_client")
    def test_run_data_extraction_requests_json_schema(
        self,
        build_llm_client: Mock,
        get_llm_model: Mock,
    ) -> None:
        response = Mock(
            output_text=(
                '{"needs_data": false, "sql": null, "reason": "No data needed.", '
                '"confidence": 0.7, "data_not_needed_reason": "No local data needed."}'
            )
        )
        client = Mock()
        client.responses.create.return_value = response
        build_llm_client.return_value = client

        decision = run_data_extraction_llm("Who are the Bills?", provider="local")

        self.assertFalse(decision.needs_data)
        build_llm_client.assert_called_once_with("local")
        get_llm_model.assert_called_once_with("local")
        call_kwargs = client.responses.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "test-model")
        self.assertEqual(call_kwargs["instructions"], _EXTRACT_DATA_INSTRUCTIONS)
        self.assertEqual(call_kwargs["max_output_tokens"], 2000)
        self.assertNotIn("reasoning", call_kwargs)
        self.assertEqual(call_kwargs["text"], {"format": _DATA_EXTRACTION_RESPONSE_FORMAT})

    @patch("app.llm.data_extraction.get_llm_model", return_value="test-model")
    @patch("app.llm.data_extraction.build_llm_client")
    def test_run_data_extraction_sends_reasoning_only_to_openai(
        self,
        build_llm_client: Mock,
        get_llm_model: Mock,
    ) -> None:
        client = Mock()
        client.responses.create.return_value = Mock(
            incomplete_details=None,
            output_text='{"needs_data": false, "sql": null, "reason": "r", '
            '"confidence": 0.5, "data_not_needed_reason": "n"}',
        )
        build_llm_client.return_value = client

        run_data_extraction_llm("Who are the Bills?", provider="openai")

        call_kwargs = client.responses.create.call_args.kwargs
        self.assertEqual(call_kwargs["reasoning"], LLM_REASONING)

    @patch("app.llm.data_extraction.get_llm_model", return_value="test-model")
    @patch("app.llm.data_extraction.build_llm_client")
    def test_run_data_extraction_raises_on_incomplete_response(
        self,
        build_llm_client: Mock,
        get_llm_model: Mock,
    ) -> None:
        client = Mock()
        client.responses.create.return_value = Mock(
            incomplete_details={"reason": "max_output_tokens"}, output_text=""
        )
        build_llm_client.return_value = client

        with self.assertRaisesRegex(LLMServiceError, "data extractor.*max_output_tokens"):
            run_data_extraction_llm("Who are the Bills?", provider="openai")

    @patch("app.llm.data_extraction.get_llm_model", return_value="test-model")
    @patch("app.llm.data_extraction.build_llm_client")
    def test_run_data_extraction_includes_provider_error(
        self,
        build_llm_client: Mock,
        get_llm_model: Mock,
    ) -> None:
        client = Mock()
        client.responses.create.side_effect = OpenAIError("unsupported response format")
        build_llm_client.return_value = client

        with self.assertRaisesRegex(LLMServiceError, "unsupported response format"):
            run_data_extraction_llm("Who are the Bills?", provider="local")

    @patch.dict("os.environ", {}, clear=True)
    @patch("builtins.print")
    def test_response_debug_print_is_disabled_by_default(self, print_mock: Mock) -> None:
        _print_data_extraction_response_debug(Mock(output_text="{}"))

        print_mock.assert_not_called()

    def test_parses_valid_data_request(self) -> None:
        decision = _parse_data_extraction_decision(
            """
            {
              "needs_data": true,
              "sql": "SELECT season, COUNT(*) AS plays FROM nfl_plays GROUP BY season ORDER BY season",
              "reason": "The question asks for play counts by season.",
              "confidence": 0.8,
              "data_not_needed_reason": null
            }
            """
        )

        self.assertTrue(decision.needs_data)
        self.assertEqual(
            decision.sql,
            "SELECT season, COUNT(*) AS plays FROM nfl_plays GROUP BY season ORDER BY season",
        )
        self.assertEqual(decision.reason, "The question asks for play counts by season.")
        self.assertEqual(decision.confidence, 0.8)
        self.assertIsNone(decision.data_not_needed_reason)

    def test_parses_valid_no_data_decision(self) -> None:
        decision = _parse_data_extraction_decision(
            """
            {
              "needs_data": false,
              "sql": null,
              "reason": "The question asks about current injuries.",
              "confidence": 0.9,
              "data_not_needed_reason": "Local play data does not include injuries."
            }
            """
        )

        self.assertFalse(decision.needs_data)
        self.assertIsNone(decision.sql)
        self.assertEqual(decision.reason, "The question asks about current injuries.")
        self.assertEqual(decision.confidence, 0.9)
        self.assertEqual(
            decision.data_not_needed_reason,
            "Local play data does not include injuries.",
        )

    def test_strips_fenced_json(self) -> None:
        decision = _parse_data_extraction_decision(
            """```json
            {
              "needs_data": true,
              "sql": "SELECT 1 FROM nfl_plays",
              "reason": "Test query.",
              "confidence": 1,
              "data_not_needed_reason": null
            }
            ```"""
        )

        self.assertTrue(decision.needs_data)
        self.assertEqual(decision.sql, "SELECT 1 FROM nfl_plays")

    def test_clamps_confidence(self) -> None:
        high = _parse_data_extraction_decision(
            """
            {
              "needs_data": false,
              "sql": null,
              "reason": "Too high.",
              "confidence": 10,
              "data_not_needed_reason": null
            }
            """
        )
        low = _parse_data_extraction_decision(
            """
            {
              "needs_data": false,
              "sql": null,
              "reason": "Too low.",
              "confidence": -5,
              "data_not_needed_reason": null
            }
            """
        )

        self.assertEqual(high.confidence, 1.0)
        self.assertEqual(low.confidence, 0.0)

    def test_invalid_confidence_defaults_to_zero(self) -> None:
        decision = _parse_data_extraction_decision(
            """
            {
              "needs_data": false,
              "sql": null,
              "reason": "Bad confidence.",
              "confidence": "high",
              "data_not_needed_reason": null
            }
            """
        )

        self.assertEqual(decision.confidence, 0.0)

    def test_ignores_sql_when_data_not_needed(self) -> None:
        decision = _parse_data_extraction_decision(
            """
            {
              "needs_data": false,
              "sql": "SELECT * FROM nfl_plays",
              "reason": "No data needed.",
              "confidence": 0.5,
              "data_not_needed_reason": "The question can be answered directly."
            }
            """
        )

        self.assertFalse(decision.needs_data)
        self.assertIsNone(decision.sql)

    def test_string_false_does_not_request_data(self) -> None:
        decision = _parse_data_extraction_decision(
            """
            {
              "needs_data": "false",
              "sql": "SELECT * FROM nfl_plays",
              "reason": "String boolean.",
              "confidence": 0.5,
              "data_not_needed_reason": "No local data needed."
            }
            """
        )

        self.assertFalse(decision.needs_data)
        self.assertIsNone(decision.sql)

    def test_blank_sql_when_data_needed_becomes_no_data_decision(self) -> None:
        decision = _parse_data_extraction_decision(
            """
            {
              "needs_data": true,
              "sql": " ",
              "reason": "",
              "confidence": 0.5,
              "data_not_needed_reason": null
            }
            """
        )

        self.assertFalse(decision.needs_data)
        self.assertIsNone(decision.sql)
        self.assertIn("did not provide usable SQL", decision.reason)
        self.assertIn("did not provide usable SQL", decision.data_not_needed_reason)

    def test_missing_reason_uses_fallback(self) -> None:
        decision = _parse_data_extraction_decision(
            """
            {
              "needs_data": false,
              "sql": null,
              "confidence": 0.2,
              "data_not_needed_reason": null
            }
            """
        )

        self.assertEqual(decision.reason, "Extractor did not provide a reason.")

    def test_malformed_json_raises_service_error(self) -> None:
        with self.assertRaisesRegex(LLMServiceError, "invalid JSON"):
            _parse_data_extraction_decision("{not valid json")

    def test_missing_json_object_raises_service_error(self) -> None:
        with self.assertRaisesRegex(LLMServiceError, "invalid JSON"):
            _parse_data_extraction_decision("no JSON here")


if __name__ == "__main__":
    unittest.main()
