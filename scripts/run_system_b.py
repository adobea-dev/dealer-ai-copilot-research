"""Run System B against benchmark development tasks.

Default behavior uses development tasks only. Held-out test execution remains
locked unless explicitly enabled after all systems are frozen.

Examples
--------

Run one development task:

    python -m scripts.run_system_b --task-id C4_DEV_01

Run all development tasks:

    python -m scripts.run_system_b

Held-out test run after system freeze:

    python -m scripts.run_system_b --split test --allow-test
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.systems.text_to_sql_explanation import (
    TextToSQLExplanationSystem,
)


TASKS_PATH = Path("benchmark/tasks_v1.json")
RESULTS_DIR = Path("results/system_b")


def load_tasks() -> list[dict[str, Any]]:
    with TASKS_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run System B: Text-to-SQL plus explanation."
    )

    parser.add_argument(
        "--split",
        choices=["development", "test"],
        default="development",
    )

    parser.add_argument(
        "--task-id",
        default=None,
        help="Optional single task ID.",
    )

    parser.add_argument(
        "--allow-test",
        action="store_true",
        help="Explicitly unlock held-out test execution.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.split == "test" and not args.allow_test:
        raise SystemExit(
            "\nREFUSED: held-out test tasks are locked during development.\n"
        )

    tasks = load_tasks()
    selected = [
        task
        for task in tasks
        if task["split"] == args.split
    ]

    if args.task_id:
        selected = [
            task
            for task in selected
            if task["task_id"] == args.task_id
        ]

        if not selected:
            raise SystemExit(
                f"No task {args.task_id!r} exists in split {args.split!r}."
            )

    system = TextToSQLExplanationSystem()

    print("=" * 78)
    print("SYSTEM B — TEXT-TO-SQL + GROUNDED EXPLANATION")
    print("=" * 78)
    print(f"Split:          {args.split}")
    print(f"Tasks selected: {len(selected)}")
    print(f"Model:          {system.model}")
    print(f"Thinking level: {system.thinking_level}")
    print("SQL retries:    0")
    print("Agent loop:     disabled")
    print("Explanation:    enabled (single grounded call)")
    print("Visualization:  disabled")
    print("=" * 78)

    run_started = datetime.now(timezone.utc)
    results = []

    for index, task in enumerate(selected, start=1):
        task_id = task["task_id"]
        question = task["prompt"]

        print()
        print(f"[{index}/{len(selected)}] {task_id}")
        print(f"Question: {question}")

        result = system.run(
            question,
            task_id=task_id,
        )
        results.append(result.to_dict())

        if result.execution_success:
            print("[SQL EXECUTION PASS]")
            print(f"SQL: {result.generated_sql}")
            print(f"Rows: {len(result.rows)}")
        else:
            print("[SQL EXECUTION FAIL]")

        if result.explanation:
            print("[EXPLANATION PASS]")
            print(result.explanation)
        elif result.error_stage == "explanation_generation":
            print("[EXPLANATION FAIL]")
            print(f"{result.error_type}: {result.error_message}")

        if result.error_stage in {
            "sql_generation",
            "database_execution",
        }:
            print(
                f"Failure stage: {result.error_stage}\n"
                f"Error type:    {result.error_type}\n"
                f"Error:         {result.error_message}"
            )

    run_finished = datetime.now(timezone.utc)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = run_started.strftime("%Y%m%dT%H%M%SZ")
    output_path = RESULTS_DIR / f"{args.split}_{timestamp}.json"

    sql_successes = sum(
        bool(r["execution_success"])
        for r in results
    )
    explanation_successes = sum(
        bool(r.get("explanation"))
        for r in results
    )

    run_record = {
        "system": "B",
        "system_name": "text_to_sql_plus_grounded_explanation",
        "split": args.split,
        "started_at_utc": run_started.isoformat(),
        "finished_at_utc": run_finished.isoformat(),
        "model": system.model,
        "thinking_level": system.thinking_level,
        "task_count": len(results),
        "sql_execution_success_count": sql_successes,
        "explanation_success_count": explanation_successes,
        "design": {
            "sql_model_calls_per_task": 1,
            "explanation_model_calls_per_successful_query": 1,
            "sql_candidates_per_task": 1,
            "retry_on_semantic_failure": False,
            "sql_self_correction": False,
            "agent_loop": False,
            "natural_language_explanation": True,
            "visualization": False,
        },
        "results": results,
    }

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(
            run_record,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print("=" * 78)
    print("SYSTEM B RUN COMPLETE")
    print("=" * 78)
    print(
        f"SQL execution success: {sql_successes}/{len(results)}"
    )
    print(
        f"Explanation success:   {explanation_successes}/{len(results)}"
    )
    print(f"Saved results:         {output_path}")


if __name__ == "__main__":
    main()
