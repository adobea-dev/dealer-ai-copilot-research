from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.db.connection import get_connection

TASKS_PATH = Path("benchmark/tasks_v1.json")
GOLD_QUERIES_PATH = Path("benchmark/gold/gold_queries_v1.json")
GOLD_RESULTS_PATH = Path("benchmark/gold/gold_results_v1.json")


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Unsupported JSON value: {type(value)}")


def main() -> None:
    tasks = load_json(TASKS_PATH)
    gold_queries = load_json(GOLD_QUERIES_PATH)

    task_ids = {task["task_id"] for task in tasks}
    if task_ids != set(gold_queries):
        raise ValueError("Task IDs and gold-query IDs do not match.")

    results = {}
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            for task in tasks:
                task_id = task["task_id"]
                definition = gold_queries[task_id]
                print(f"Executing {task_id}...")
                cursor.execute(definition["sql"])
                rows = cursor.fetchall()

                actual_columns = list(rows[0].keys()) if rows else []
                expected_columns = definition["expected_columns"]
                if actual_columns != expected_columns:
                    raise ValueError(
                        f"{task_id} column mismatch.\n"
                        f"Expected: {expected_columns}\n"
                        f"Actual:   {actual_columns}"
                    )

                results[task_id] = {
                    "columns": actual_columns,
                    "rows": rows,
                }
                print(f"[PASS] {task_id}: {len(rows)} row(s)")
    finally:
        connection.close()

    GOLD_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with GOLD_RESULTS_PATH.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=serialize)

    print("\n" + "=" * 70)
    print("GOLD RESULT GENERATION COMPLETE")
    print("=" * 70)
    print(f"Tasks executed: {len(results)}")
    print(f"Saved to:      {GOLD_RESULTS_PATH}")


if __name__ == "__main__":
    main()
