"""Run System A against benchmark development tasks.

By default this script REFUSES to run held-out test tasks. That prevents
accidental benchmark leakage while Systems A/B/C are still being developed.

Examples
--------

Run all 12 development tasks:

    python -m scripts.run_system_a

Run one development task:

    python -m scripts.run_system_a --task-id C1_DEV_01

Held-out evaluation should happen only after all systems are frozen. At that
point it must be explicitly unlocked:

    python -m scripts.run_system_a --split test --allow-test
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.systems.text_to_sql import TextToSQLBaseline


TASKS_PATH = Path("benchmark/tasks_v1.json")
RESULTS_DIR = Path("results/system_a")


def load_tasks() -> list[dict[str, Any]]:
    with TASKS_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run System A: single-shot Text-to-SQL baseline."
    )

    parser.add_argument(
        "--split",
        choices=["development", "test"],
        default="development",
        help="Benchmark split to run. Default: development.",
    )

    parser.add_argument(
        "--task-id",
        default=None,
        help="Optional single task ID.",
    )

    parser.add_argument(
        "--allow-test",
        action="store_true",
        help=(
            "Explicitly unlock held-out test execution. "
            "Do not use during system development."
        ),
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.split == "test" and not args.allow_test:
        raise SystemExit(
            "\nREFUSED: held-out test tasks are locked during development.\n"
            "Use only the development split until Systems A, B, and C are frozen.\n"
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

    system = TextToSQLBaseline()

    print("=" * 78)
    print("SYSTEM A — SINGLE-SHOT TEXT-TO-SQL BASELINE")
    print("=" * 78)
    print(f"Split:          {args.split}")
    print(f"Tasks selected: {len(selected)}")
    print(f"Model:          {system.model}")
    print(f"Thinking level: {system.thinking_level}")
    print("Retries:        0")
    print("Agent loop:     disabled")
    print("Explanation:    disabled")
    print("Visualization:  disabled")
    print("=" * 78)

    run_started = datetime.now(timezone.utc)
    results: list[dict[str, Any]] = []

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
        result_dict = result.to_dict()
        results.append(result_dict)

        if result.execution_success:
            print("[EXECUTION PASS]")
            print(f"SQL: {result.generated_sql}")
            print(f"Rows: {len(result.rows)}")
        else:
            print("[EXECUTION FAIL]")
            print(f"Error type: {result.error_type}")
            print(f"Error: {result.error_message}")
            if result.generated_sql:
                print(f"SQL: {result.generated_sql}")

    run_finished = datetime.now(timezone.utc)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = run_started.strftime("%Y%m%dT%H%M%SZ")
    output_path = RESULTS_DIR / f"{args.split}_{timestamp}.json"

    successful = sum(
        1
        for result in results
        if result["execution_success"]
    )

    run_record = {
        "system": "A",
        "system_name": "single_shot_text_to_sql",
        "split": args.split,
        "started_at_utc": run_started.isoformat(),
        "finished_at_utc": run_finished.isoformat(),
        "model": system.model,
        "thinking_level": system.thinking_level,
        "task_count": len(results),
        "execution_success_count": successful,
        "execution_failure_count": len(results) - successful,
        "design": {
            "model_calls_per_task": 1,
            "sql_candidates_per_task": 1,
            "retry_on_failure": False,
            "self_correction": False,
            "agent_loop": False,
            "natural_language_explanation": False,
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
    print("SYSTEM A RUN COMPLETE")
    print("=" * 78)
    print(f"Execution success: {successful}/{len(results)}")
    print(f"Saved results:     {output_path}")
    print()
    print(
        "NOTE: execution success only means the generated SQL ran. "
        "It does NOT mean the analytical answer was correct."
    )


if __name__ == "__main__":
    main()
