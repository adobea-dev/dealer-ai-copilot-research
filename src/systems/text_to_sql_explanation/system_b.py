"""System B: single-shot Text-to-SQL plus grounded explanation.

Architecture
------------
User question
    -> one Text-to-SQL model call
    -> one PostgreSQL query
    -> one explanation model call using only the returned rows
    -> final natural-language answer

Scientific constraints
----------------------
- SQL generation is inherited from System A so the query-generation stage is
  held constant.
- no SQL repair;
- no retry after semantic/SQL failure;
- no planning loop;
- no autonomous tool selection;
- no visualization;
- explanation cannot issue another database query.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Any

from google import genai
from google.genai import types

from src.systems.text_to_sql.baseline import (
    TextToSQLBaseline,
    TokenUsage,
    _extract_usage,
    _json_safe,
)
from src.systems.text_to_sql_explanation.prompt import (
    EXPLANATION_INSTRUCTION,
)


@dataclass
class StageUsage:
    sql_generation: TokenUsage
    explanation: TokenUsage


@dataclass
class SystemBResult:
    task_id: str | None
    question: str

    model: str
    model_version_sql: str | None
    model_version_explanation: str | None
    thinking_level: str

    generated_sql: str | None
    execution_success: bool
    columns: list[str]
    rows: list[dict[str, Any]]

    explanation: str | None

    error_stage: str | None
    error_type: str | None
    error_message: str | None

    model_calls: int
    database_query_calls: int

    sql_generation_latency_seconds: float
    database_latency_seconds: float
    explanation_latency_seconds: float
    total_latency_seconds: float

    token_usage: StageUsage

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


def _empty_usage() -> TokenUsage:
    return TokenUsage()


class TextToSQLExplanationSystem:
    """System B implementation."""

    def __init__(
        self,
        *,
        model: str | None = None,
        thinking_level: str | None = None,
        statement_timeout_ms: int = 10_000,
        max_rows: int = 1_000,
    ) -> None:
        # Reuse System A directly for SQL generation and PostgreSQL execution.
        # This keeps the query-oriented portion of A and B as comparable as
        # possible.
        self.sql_baseline = TextToSQLBaseline(
            model=model,
            thinking_level=thinking_level,
            statement_timeout_ms=statement_timeout_ms,
            max_rows=max_rows,
        )

        self.model = self.sql_baseline.model
        self.thinking_level = self.sql_baseline.thinking_level
        self.client = self.sql_baseline.client

    def explain(
        self,
        *,
        question: str,
        sql: str,
        columns: list[str],
        rows: list[dict[str, Any]],
    ) -> tuple[str, Any, float]:
        """Generate exactly one grounded explanation."""
        payload = {
            "question": question,
            "executed_sql": sql,
            "result": {
                "columns": columns,
                "rows": _json_safe(rows),
            },
        }

        started = time.perf_counter()

        response = self.client.models.generate_content(
            model=self.model,
            contents=json.dumps(
                payload,
                ensure_ascii=False,
            ),
            config=types.GenerateContentConfig(
                system_instruction=EXPLANATION_INSTRUCTION,
                thinking_config=types.ThinkingConfig(
                    thinking_level=self.thinking_level,
                ),
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True,
                ),
            ),
        )

        latency = time.perf_counter() - started

        if not response.text:
            raise ValueError("The explanation model returned no text.")

        return response.text.strip(), response, latency

    def run(
        self,
        question: str,
        *,
        task_id: str | None = None,
    ) -> SystemBResult:
        """Run one benchmark question with no repair/self-correction loop."""
        total_started = time.perf_counter()

        generated_sql: str | None = None
        explanation: str | None = None

        sql_model_version: str | None = None
        explanation_model_version: str | None = None

        sql_usage = _empty_usage()
        explanation_usage = _empty_usage()

        sql_latency = 0.0
        database_latency = 0.0
        explanation_latency = 0.0

        database_query_calls = 0
        model_calls = 0

        columns: list[str] = []
        rows: list[dict[str, Any]] = []

        # -------------------------------------------------------------
        # Stage 1: SQL generation
        # -------------------------------------------------------------
        try:
            model_calls += 1
            generated_sql, response, sql_latency = (
                self.sql_baseline.generate_sql(question)
            )
            sql_model_version = getattr(
                response,
                "model_version",
                None,
            )
            sql_usage = _extract_usage(response)

        except Exception as exc:
            return SystemBResult(
                task_id=task_id,
                question=question,
                model=self.model,
                model_version_sql=sql_model_version,
                model_version_explanation=None,
                thinking_level=self.thinking_level,
                generated_sql=generated_sql,
                execution_success=False,
                columns=[],
                rows=[],
                explanation=None,
                error_stage="sql_generation",
                error_type=type(exc).__name__,
                error_message=str(exc),
                model_calls=model_calls,
                database_query_calls=0,
                sql_generation_latency_seconds=round(sql_latency, 6),
                database_latency_seconds=0.0,
                explanation_latency_seconds=0.0,
                total_latency_seconds=round(
                    time.perf_counter() - total_started,
                    6,
                ),
                token_usage=StageUsage(
                    sql_generation=sql_usage,
                    explanation=explanation_usage,
                ),
            )

        # -------------------------------------------------------------
        # Stage 2: database execution
        # -------------------------------------------------------------
        try:
            database_query_calls = 1
            columns, rows, database_latency = (
                self.sql_baseline.execute_sql(generated_sql)
            )

        except Exception as exc:
            return SystemBResult(
                task_id=task_id,
                question=question,
                model=self.model,
                model_version_sql=sql_model_version,
                model_version_explanation=None,
                thinking_level=self.thinking_level,
                generated_sql=generated_sql,
                execution_success=False,
                columns=[],
                rows=[],
                explanation=None,
                error_stage="database_execution",
                error_type=type(exc).__name__,
                error_message=str(exc),
                model_calls=model_calls,
                database_query_calls=database_query_calls,
                sql_generation_latency_seconds=round(sql_latency, 6),
                database_latency_seconds=round(database_latency, 6),
                explanation_latency_seconds=0.0,
                total_latency_seconds=round(
                    time.perf_counter() - total_started,
                    6,
                ),
                token_usage=StageUsage(
                    sql_generation=sql_usage,
                    explanation=explanation_usage,
                ),
            )

        # -------------------------------------------------------------
        # Stage 3: grounded explanation
        # -------------------------------------------------------------
        try:
            model_calls += 1
            explanation, response, explanation_latency = self.explain(
                question=question,
                sql=generated_sql,
                columns=columns,
                rows=rows,
            )
            explanation_model_version = getattr(
                response,
                "model_version",
                None,
            )
            explanation_usage = _extract_usage(response)

        except Exception as exc:
            # The query itself succeeded, but System B did not complete its
            # defining explanation stage.
            return SystemBResult(
                task_id=task_id,
                question=question,
                model=self.model,
                model_version_sql=sql_model_version,
                model_version_explanation=explanation_model_version,
                thinking_level=self.thinking_level,
                generated_sql=generated_sql,
                execution_success=True,
                columns=columns,
                rows=rows,
                explanation=None,
                error_stage="explanation_generation",
                error_type=type(exc).__name__,
                error_message=str(exc),
                model_calls=model_calls,
                database_query_calls=database_query_calls,
                sql_generation_latency_seconds=round(sql_latency, 6),
                database_latency_seconds=round(database_latency, 6),
                explanation_latency_seconds=round(
                    explanation_latency,
                    6,
                ),
                total_latency_seconds=round(
                    time.perf_counter() - total_started,
                    6,
                ),
                token_usage=StageUsage(
                    sql_generation=sql_usage,
                    explanation=explanation_usage,
                ),
            )

        return SystemBResult(
            task_id=task_id,
            question=question,
            model=self.model,
            model_version_sql=sql_model_version,
            model_version_explanation=explanation_model_version,
            thinking_level=self.thinking_level,
            generated_sql=generated_sql,
            execution_success=True,
            columns=columns,
            rows=rows,
            explanation=explanation,
            error_stage=None,
            error_type=None,
            error_message=None,
            model_calls=model_calls,
            database_query_calls=database_query_calls,
            sql_generation_latency_seconds=round(sql_latency, 6),
            database_latency_seconds=round(database_latency, 6),
            explanation_latency_seconds=round(
                explanation_latency,
                6,
            ),
            total_latency_seconds=round(
                time.perf_counter() - total_started,
                6,
            ),
            token_usage=StageUsage(
                sql_generation=sql_usage,
                explanation=explanation_usage,
            ),
        )
