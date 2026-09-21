"""Evaluate saved benchmark outputs against frozen gold results."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from src.evaluation import BenchmarkEvaluator


RESULTS_ROOT = Path("results")
EVALUATION_DIR = RESULTS_ROOT / "evaluations"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--system", default="system_a")
    parser.add_argument(
        "--split",
        choices=["development", "test"],
        default="development",
    )
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        help="Optional explicit result file. Can be repeated.",
    )
    parser.add_argument("--allow-test", action="store_true")
    return parser.parse_args()


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def collect_files(system: str, split: str, inputs: list[str]):
    if inputs:
        return [Path(p) for p in inputs]

    directory = RESULTS_ROOT / system
    if not directory.exists():
        raise FileNotFoundError(f"Missing results directory: {directory}")

    return sorted(
        directory.glob(f"{split}_*.json"),
        key=lambda p: p.stat().st_mtime,
    )


def newest_result_per_task(files: list[Path], split: str):
    latest = {}

    for path in files:
        payload = load_json(path)
        if payload.get("split") != split:
            continue

        timestamp = path.stat().st_mtime

        for result in payload.get("results", []):
            task_id = result.get("task_id")
            if not task_id:
                continue

            current = latest.get(task_id)
            if current is None or timestamp >= current[0]:
                record = dict(result)
                record["_source_file"] = str(path)
                record["_system_model"] = payload.get("model")
                record["_system_thinking_level"] = payload.get("thinking_level")
                latest[task_id] = (timestamp, record)

    return {task_id: value[1] for task_id, value in latest.items()}


def main():
    args = parse_args()

    if args.split == "test" and not args.allow_test:
        raise SystemExit(
            "\nREFUSED: held-out test evaluation is locked until all systems are frozen.\n"
        )

    files = collect_files(args.system, args.split, args.input)
    if not files:
        raise SystemExit("No matching result files found.")

    results = newest_result_per_task(files, args.split)
    if not results:
        raise SystemExit("No task results found in selected files.")

    evaluator = BenchmarkEvaluator()
    scores = []

    print("=" * 84)
    print("OBJECTIVE BENCHMARK EVALUATION")
    print("=" * 84)
    print(f"System:      {args.system}")
    print(f"Split:       {args.split}")
    print(f"Tasks found: {len(results)}")
    print("=" * 84)

    for task_id in sorted(results):
        result = results[task_id]
        score = evaluator.evaluate_result(result)
        scores.append(score.to_dict())

        print()
        print(task_id)
        print("-" * len(task_id))
        print(
            f"Execution success:    "
            f"{'PASS' if score.execution_success else 'FAIL'}"
        )
        print(
            f"Factual correctness:  "
            f"{'PASS' if score.factual_correctness else 'FAIL'}"
        )
        print(
            f"Component completion: "
            f"{score.correct_components}/{score.total_components} "
            f"({score.component_completion:.1%})"
        )
        print(
            f"Full task success:    "
            f"{'PASS' if score.full_task_success else 'FAIL'}"
        )

        model = result.get("_system_model")
        if model:
            print(f"Model:                {model}")

        for component in score.components:
            status = "PASS" if component.correct else "FAIL"
            print(
                f"  [{status}] {component.component}: {component.detail}"
            )

        for note in score.notes:
            print(f"  [NOTE] {note}")

    n = len(scores)
    exec_count = sum(s["execution_success"] for s in scores)
    factual_count = sum(s["factual_correctness"] for s in scores)
    full_count = sum(s["full_task_success"] for s in scores)
    mean_completion = sum(s["component_completion"] for s in scores) / n

    print()
    print("=" * 84)
    print("SUMMARY")
    print("=" * 84)
    print(f"Execution success:         {exec_count}/{n} ({exec_count/n:.1%})")
    print(f"Factual correctness:       {factual_count}/{n} ({factual_count/n:.1%})")
    print(f"Full task success:         {full_count}/{n} ({full_count/n:.1%})")
    print(f"Mean component completion: {mean_completion:.1%}")

    EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = (
        EVALUATION_DIR
        / f"{args.system}_{args.split}_{timestamp}.json"
    )

    output = {
        "system": args.system,
        "split": args.split,
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "task_count": n,
        "summary": {
            "execution_success_count": exec_count,
            "execution_success_rate": round(exec_count / n, 4),
            "factual_correct_count": factual_count,
            "factual_correct_rate": round(factual_count / n, 4),
            "full_task_success_count": full_count,
            "full_task_success_rate": round(full_count / n, 4),
            "mean_component_completion": round(mean_completion, 4),
        },
        "scores": scores,
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nSaved evaluation: {output_path}")


if __name__ == "__main__":
    main()
