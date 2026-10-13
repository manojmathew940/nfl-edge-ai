"""Run evals/questions.yaml through the /ask flow and check each result.

Usage: python scripts/run_question_eval.py [--provider openai|local] [--only ID ...]
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time

import yaml
from fastapi import HTTPException

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.data_foundation.datasets import DATASETS
from app.main import AskRequest, ask


QUESTIONS_PATH = ROOT_DIR / "evals" / "questions.yaml"
RESULTS_DIR = ROOT_DIR / "evals" / "results"
VIEW_NAMES = [spec.view_name for spec in DATASETS.values()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="openai", choices=["openai", "local"])
    parser.add_argument("--only", nargs="+", help="question ids to run")
    args = parser.parse_args()

    cases = yaml.safe_load(QUESTIONS_PATH.read_text())
    if args.only:
        cases = [case for case in cases if case["id"] in args.only]

    results = []
    for case in cases:
        print(f"{case['id']} ...", flush=True)
        result = run_case(case, args.provider)
        results.append(result)
        print(f"  {'PASS' if result['passed'] else 'FAIL'} {'; '.join(result['failures'])}")

    passed = sum(result["passed"] for result in results)
    print(f"\n{passed}/{len(results)} passed")

    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{args.provider}.json"
    path.write_text(json.dumps(results, indent=2, default=str))
    print(f"Results: {path.relative_to(ROOT_DIR)}")


def run_case(case: dict, provider: str) -> dict:
    started = time.monotonic()
    try:
        response = ask(AskRequest(question=case["question"], provider=provider))
        error = None
    except HTTPException as exception:
        response, error = {}, exception.detail
    seconds = round(time.monotonic() - started, 1)

    failures = [f"error: {error}"] if error else check_response(case, response)
    analytics = response.get("analytics", {})
    return {
        "id": case["id"],
        "passed": not failures,
        "failures": failures,
        "seconds": seconds,
        "question": case["question"],
        "sql": analytics.get("sql"),
        "row_count": len(analytics.get("rows", [])),
        "answer": response.get("answer"),
        "data_request": response.get("data_request"),
    }


def check_response(case: dict, response: dict) -> list[str]:
    failures = []
    expected_views = set(case["views"])
    needs_data = response["data_request"]["needs_data"]
    if needs_data != bool(expected_views):
        failures.append(f"needs_data={needs_data}, expected {bool(expected_views)}")

    analytics = response["analytics"]
    if expected_views and needs_data:
        sql = (analytics["sql"] or "").lower()
        used_views = {view for view in VIEW_NAMES if view in sql}
        if used_views != expected_views:
            failures.append(f"views {sorted(used_views)}, expected {sorted(expected_views)}")
        if not analytics["is_valid"]:
            failures.append(f"invalid SQL: {analytics['validation_reason']}")
        elif not analytics["rows"]:
            failures.append("SQL returned no rows")

    answer = _normalize(response["answer"])
    for expected in case["answer_includes"]:
        options = expected if isinstance(expected, list) else [expected]
        if not any(_normalize(option) in answer for option in options):
            failures.append(f"answer missing {' / '.join(options)}")
    return failures


def _normalize(text: str) -> str:
    return text.lower().replace(",", "").replace("’", "'")


if __name__ == "__main__":
    main()
