"""Deterministic native tools for System C."""

from __future__ import annotations

import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

from google.adk.tools import ToolContext

from src.db.connection import get_connection

from .config import (
    ARTIFACTS_DIR,
    MAX_QUERY_ROWS,
    STATEMENT_TIMEOUT_MS,
)
from .security import json_safe, validate_read_only_sql


def _append_state_list(tool_context: ToolContext, key: str, item: Any) -> None:
    values = list(tool_context.state.get(key, []))
    values.append(json_safe(item))
    tool_context.state[key] = values


def query_database(
    sql: str,
    primary: bool = True,
    tool_context: ToolContext = None,
) -> dict[str, Any]:
    """Execute one safe read-only PostgreSQL query.

    Use this tool for factual dealer analytics. Set `primary=true` when this
    query's rows most directly represent the final answer table. Supporting or
    exploratory queries should use `primary=false`.

    Returns a structured success/error object. SQL errors are returned to the
    agent so it can make a bounded corrected attempt.
    """
    started = time.perf_counter()

    try:
        safe_sql = validate_read_only_sql(sql)
    except Exception as exc:
        result = {
            "status": "error",
            "error_type": "sql_policy_error",
            "message": str(exc),
            "retryable": False,
        }
        if tool_context is not None:
            _append_state_list(
                tool_context,
                "sql_attempts",
                {"sql": sql, **result},
            )
        return result

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(
                f"SET LOCAL statement_timeout = '{int(STATEMENT_TIMEOUT_MS)}ms'"
            )
            cursor.execute(safe_sql)

            if cursor.description is None:
                raise RuntimeError("Query returned no result set.")

            columns = [column.name for column in cursor.description]
            fetched = cursor.fetchmany(MAX_QUERY_ROWS + 1)

            if len(fetched) > MAX_QUERY_ROWS:
                raise RuntimeError(
                    f"Query exceeded the row limit of {MAX_QUERY_ROWS}."
                )

            rows = [json_safe(dict(row)) for row in fetched]

        connection.rollback()

        result = {
            "status": "success",
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": False,
            "latency_seconds": round(time.perf_counter() - started, 6),
        }

        if tool_context is not None:
            attempt = {
                "sql": safe_sql,
                "primary": bool(primary),
                "status": "success",
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "latency_seconds": result["latency_seconds"],
            }
            _append_state_list(tool_context, "sql_attempts", attempt)

            if primary:
                tool_context.state["primary_result"] = {
                    "sql": safe_sql,
                    "columns": columns,
                    "rows": rows,
                }

        return result

    except Exception as exc:
        connection.rollback()

        message = str(exc)
        lower = message.lower()

        retryable = any(
            marker in lower
            for marker in (
                "does not exist",
                "undefined",
                "syntax error",
                "column",
                "operator does not exist",
                "invalid input syntax",
            )
        )

        result = {
            "status": "error",
            "error_type": type(exc).__name__,
            "message": message[:1000],
            "retryable": retryable,
            "latency_seconds": round(time.perf_counter() - started, 6),
        }

        if tool_context is not None:
            _append_state_list(
                tool_context,
                "sql_attempts",
                {"sql": safe_sql, "primary": bool(primary), **result},
            )

        return result

    finally:
        connection.close()


def calculate(
    operation: str,
    values: list[float],
    tool_context: ToolContext = None,
) -> dict[str, Any]:
    """Perform deterministic arithmetic.

    Supported operations:
    - ratio_pct: values=[numerator, denominator]
    - percentage_change: values=[old_value, new_value]
    - difference: values=[first_value, second_value] -> first - second
    - sum
    - mean
    - median
    - min
    - max
    """
    operation = operation.strip().lower()

    try:
        numbers = [float(value) for value in values]
    except (TypeError, ValueError):
        return {
            "status": "error",
            "error_type": "invalid_numeric_input",
            "message": "All values must be numeric.",
            "retryable": True,
        }

    try:
        if operation == "ratio_pct":
            if len(numbers) != 2:
                raise ValueError("ratio_pct requires [numerator, denominator].")
            numerator, denominator = numbers
            if denominator == 0:
                raise ZeroDivisionError("Denominator is zero.")
            answer = (numerator / denominator) * 100.0

        elif operation == "percentage_change":
            if len(numbers) != 2:
                raise ValueError(
                    "percentage_change requires [old_value, new_value]."
                )
            old_value, new_value = numbers
            if old_value == 0:
                raise ZeroDivisionError("Old value is zero.")
            answer = ((new_value - old_value) / old_value) * 100.0

        elif operation == "difference":
            if len(numbers) != 2:
                raise ValueError("difference requires exactly two values.")
            answer = numbers[0] - numbers[1]

        elif operation == "sum":
            answer = sum(numbers)

        elif operation == "mean":
            answer = statistics.mean(numbers)

        elif operation == "median":
            answer = statistics.median(numbers)

        elif operation == "min":
            answer = min(numbers)

        elif operation == "max":
            answer = max(numbers)

        else:
            raise ValueError(f"Unsupported operation: {operation}")

        result = {
            "status": "success",
            "operation": operation,
            "result": round(float(answer), 6),
        }

        if tool_context is not None:
            _append_state_list(
                tool_context,
                "calculation_results",
                {
                    "operation": operation,
                    "values": numbers,
                    **result,
                },
            )

        return result

    except Exception as exc:
        return {
            "status": "error",
            "error_type": type(exc).__name__,
            "message": str(exc),
            "retryable": True,
        }


def create_visualization(
    chart_type: str,
    title: str,
    x_key: str,
    y_keys: list[str],
    data_json: str,
    tool_context: ToolContext = None,
) -> dict[str, Any]:
    """Create one deterministic PNG visualization from exact analytical rows.

    `data_json` must be a JSON array of row objects. Supported chart types:
    line and bar. Use this tool only when the user's prompt explicitly asks
    for a visualization.
    """
    chart_type = chart_type.strip().lower()

    if chart_type not in {"line", "bar"}:
        return {
            "status": "error",
            "error_type": "unsupported_chart_type",
            "message": "Supported chart types are line and bar.",
            "retryable": True,
        }

    try:
        rows = json.loads(data_json)
    except json.JSONDecodeError as exc:
        return {
            "status": "error",
            "error_type": "invalid_json",
            "message": str(exc),
            "retryable": True,
        }

    if not isinstance(rows, list) or not rows:
        return {
            "status": "error",
            "error_type": "empty_chart_data",
            "message": "Visualization data must be a non-empty JSON array.",
            "retryable": True,
        }

    if not y_keys:
        return {
            "status": "error",
            "error_type": "missing_series",
            "message": "At least one y_key is required.",
            "retryable": True,
        }

    try:
        x_values = [row[x_key] for row in rows]
        series = {
            key: [float(row[key]) for row in rows]
            for key in y_keys
        }
    except (KeyError, TypeError, ValueError) as exc:
        return {
            "status": "error",
            "error_type": "invalid_chart_data",
            "message": str(exc),
            "retryable": True,
        }

    task_id = "task"
    if tool_context is not None:
        task_id = str(tool_context.state.get("task_id", "task"))

    output_dir = ARTIFACTS_DIR / task_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "visualization.png"

    fig, ax = plt.subplots(figsize=(10, 6))

    if chart_type == "line":
        for key, values in series.items():
            ax.plot(x_values, values, marker="o", label=key)
    else:
        # Grouped bars without explicitly choosing colors.
        count = len(y_keys)
        positions = list(range(len(x_values)))
        width = 0.8 / count
        for index, (key, values) in enumerate(series.items()):
            offsets = [
                position - 0.4 + width / 2 + index * width
                for position in positions
            ]
            ax.bar(offsets, values, width=width, label=key)
        ax.set_xticks(positions)
        ax.set_xticklabels(x_values, rotation=45, ha="right")

    ax.set_title(title)
    ax.set_xlabel(x_key)
    ax.set_ylabel("Value")

    if len(y_keys) > 1:
        ax.legend()

    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)

    result = {
        "status": "success",
        "chart_type": chart_type,
        "path": str(output_path),
        "series": y_keys,
        "row_count": len(rows),
    }

    if tool_context is not None:
        tool_context.state["visualization_path"] = str(output_path)
        _append_state_list(tool_context, "visualizations", result)

    return result
