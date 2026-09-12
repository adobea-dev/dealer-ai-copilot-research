from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

TASKS_PATH = Path("benchmark/tasks_v1.json")
GOLD_PATH = Path("benchmark/gold/gold_queries_v1.json")

VALID_SPLITS = {"development", "test"}
VALID_COMPLEXITIES = {"C1", "C2", "C3", "C4", "C5", "C6"}
VALID_TIME_SEMANTICS = {"event_period", "cohort", "all_time"}
REQUIRED_FIELDS = {
    "task_id", "split", "complexity", "prompt", "answer_type",
    "required_components", "visualization_required",
    "explanation_required", "time_semantics",
}


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    tasks = load_json(TASKS_PATH)
    gold = load_json(GOLD_PATH)

    if len(tasks) != 48:
        raise ValueError(f"Expected 48 tasks, found {len(tasks)}")

    ids = [task["task_id"] for task in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate task IDs found.")

    for task in tasks:
        missing = REQUIRED_FIELDS - set(task)
        if missing:
            raise ValueError(f"{task.get('task_id')} missing fields: {sorted(missing)}")
        if task["split"] not in VALID_SPLITS:
            raise ValueError(f"{task['task_id']} has invalid split.")
        if task["complexity"] not in VALID_COMPLEXITIES:
            raise ValueError(f"{task['task_id']} has invalid complexity.")
        if task["time_semantics"] not in VALID_TIME_SEMANTICS:
            raise ValueError(f"{task['task_id']} has invalid time semantics.")
        if not isinstance(task["required_components"], list) or not task["required_components"]:
            raise ValueError(f"{task['task_id']} must have required components.")
        if not isinstance(task["visualization_required"], bool):
            raise ValueError(f"{task['task_id']} visualization_required must be boolean.")
        if not isinstance(task["explanation_required"], bool):
            raise ValueError(f"{task['task_id']} explanation_required must be boolean.")

    if set(ids) != set(gold):
        raise ValueError(
            f"Task/gold mismatch. Missing gold={sorted(set(ids)-set(gold))}, "
            f"extra gold={sorted(set(gold)-set(ids))}"
        )

    for task_id, item in gold.items():
        if not item.get("sql", "").strip():
            raise ValueError(f"{task_id} has empty gold SQL.")
        if not item.get("expected_columns"):
            raise ValueError(f"{task_id} has no expected columns.")

    complexity_counts = Counter(task["complexity"] for task in tasks)
    split_counts = Counter(task["split"] for task in tasks)

    for complexity in sorted(VALID_COMPLEXITIES):
        level = [t for t in tasks if t["complexity"] == complexity]
        dev = sum(t["split"] == "development" for t in level)
        test = sum(t["split"] == "test" for t in level)
        if len(level) != 8 or dev != 2 or test != 6:
            raise ValueError(
                f"{complexity}: expected 8 tasks (2 dev, 6 test); "
                f"found {len(level)} ({dev} dev, {test} test)."
            )

    if split_counts["development"] != 12 or split_counts["test"] != 36:
        raise ValueError(f"Expected 12 dev / 36 test, found {dict(split_counts)}")

    print("=" * 70)
    print("BENCHMARK DEFINITION VALIDATION")
    print("=" * 70)
    print(f"Tasks:       {len(tasks)}")
    print(f"Development: {split_counts['development']}")
    print(f"Held-out:    {split_counts['test']}")
    for complexity in sorted(complexity_counts):
        print(f"{complexity}:          {complexity_counts[complexity]}")
    print("\n[PASS] Benchmark definition is structurally valid.")


if __name__ == "__main__":
    main()
