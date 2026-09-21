"""Run System C on benchmark tasks.

Held-out test tasks remain locked during development.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.systems.agentic_analytics import AgenticAnalyticsSystem


TASKS_PATH = Path("benchmark/tasks_v1.json")
RESULTS_DIR = Path("results/system_c")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run System C: MCP/KG-grounded agentic analytics."
        )
    )

    parser.add_argument(
        "--split",
        choices=["development", "test"],
        default="development",
    )

    parser.add_argument(
        "--task-id",
        default=None,
    )

    parser.add_argument(
        "--allow-test",
        action="store_true",
    )

    return parser.parse_args()


def load_tasks() -> list[dict[str, Any]]:
    with TASKS_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def main() -> None:
    args = parse_args()

    if (
        args.split == "test"
        and not args.allow_test
    ):
        raise SystemExit(
            "\nREFUSED: held-out test tasks are "
            "locked during development.\n"
        )

    tasks = [
        task
        for task in load_tasks()
        if task["split"] == args.split
    ]

    if args.task_id:
        tasks = [
            task
            for task in tasks
            if task["task_id"] == args.task_id
        ]

    if not tasks:
        raise SystemExit(
            "No matching benchmark tasks."
        )

    system = AgenticAnalyticsSystem()

    print("=" * 82)
    print(
        "SYSTEM C — MCP + KNOWLEDGE-GRAPH "
        "AGENTIC ANALYTICS"
    )
    print("=" * 82)
    print(f"Split:          {args.split}")
    print(f"Tasks selected: {len(tasks)}")
    print(f"Model:          {system.model}")
    print(
        f"Thinking level: {system.thinking_level}"
    )
    print("Session memory: per-task only")
    print("Neo4j MCP:      read-only")
    print("Agent loop:     bounded")
    print("Final synthesis: bounded grounded recovery")
    print("=" * 82)

    started = datetime.now(timezone.utc)
    results = []

    for index, task in enumerate(
        tasks,
        start=1,
    ):
        print()
        print(
            f"[{index}/{len(tasks)}] "
            f"{task['task_id']}"
        )
        print(
            f"Question: {task['prompt']}"
        )

        result = system.run(
            task["prompt"],
            task_id=task["task_id"],
        )

        record = result.to_dict()
        results.append(record)

        if result.execution_success:
            print("[AGENT PASS]")
        else:
            print("[AGENT FAIL]")
            print(
                f"Stage: {result.error_stage}"
            )
            print(
                "Error: "
                f"{result.error_type}: "
                f"{result.error_message}"
            )

        print(
            "Calls: "
            f"model={result.model_calls}, "
            f"tools={result.total_tool_calls}, "
            f"db={result.database_query_calls}, "
            f"kg={result.knowledge_graph_calls}, "
            f"calc={result.calculation_calls}, "
            f"viz={result.visualization_calls}"
        )

        print(
            "Synthesis: "
            f"{result.synthesis_source or 'none'}"
        )

        if result.synthesis_fallback_used:
            print(
                "[SYNTHESIS RECOVERY USED]"
            )

        if result.explanation:
            print("[FINAL ANSWER]")
            print(result.explanation)

        if result.visualization:
            print(
                "[VISUALIZATION] "
                f"{result.visualization}"
            )

    finished = datetime.now(timezone.utc)

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = started.strftime(
        "%Y%m%dT%H%M%SZ"
    )

    output_path = (
        RESULTS_DIR
        / f"{args.split}_{timestamp}.json"
    )

    success_count = sum(
        bool(result["execution_success"])
        for result in results
    )

    fallback_count = sum(
        bool(
            result.get(
                "synthesis_fallback_used",
                False,
            )
        )
        for result in results
    )

    output = {
        "system": "C",
        "system_name": (
            "mcp_kg_agentic_analytics"
        ),
        "split": args.split,
        "started_at_utc": started.isoformat(),
        "finished_at_utc": finished.isoformat(),
        "model": system.model,
        "thinking_level": system.thinking_level,
        "task_count": len(results),
        "execution_success_count": (
            success_count
        ),
        "synthesis_fallback_count": (
            fallback_count
        ),
        "design": {
            "architecture": (
                "single_root_adk_agent"
            ),
            "mcp": True,
            "knowledge_graph": (
                "neo4j_semantic_layer"
            ),
            "postgresql_authoritative_facts": (
                True
            ),
            "session_memory": "per_task_only",
            "persistent_cross_task_memory": (
                False
            ),
            "bounded_recovery": True,
            "bounded_final_synthesis_recovery": (
                True
            ),
            "final_synthesis_tools": False,
            "pii_redaction": True,
            "prompt_injection_policy": True,
        },
        "results": results,
    }

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            output,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print("=" * 82)
    print("SYSTEM C RUN COMPLETE")
    print("=" * 82)
    print(
        "Agent completion: "
        f"{success_count}/{len(results)}"
    )
    print(
        "Synthesis recoveries: "
        f"{fallback_count}/{len(results)}"
    )
    print(
        f"Saved results:    {output_path}"
    )
    print()
    print(
        "NOTE: agent completion is not benchmark "
        "correctness. Run the common evaluator afterward."
    )


if __name__ == "__main__":
    main()