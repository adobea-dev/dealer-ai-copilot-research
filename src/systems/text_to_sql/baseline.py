"""Single-shot Text-to-SQL baseline for Dealer AI Copilot 2.0.

Scientific design:
- exactly one LLM call per task;
- exactly one generated SQL candidate;
- no self-correction;
- no retry after SQL failure;
- no agent loop;
- no visualization;
- no natural-language explanation.

This makes System A a conventional query-oriented baseline rather than an
agentic analytics system.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from google import genai
from google.genai import types
from dotenv import load_dotenv

from src.db.connection import get_connection
from src.systems.text_to_sql.prompt import (
    SQL_RESPONSE_SCHEMA,
    SYSTEM_A_INSTRUCTION,
)

load_dotenv()

class SQLSafetyError(ValueError):
    """Raised when generated SQL violates baseline safety constraints."""


@dataclass
class TokenUsage:
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    thoughts_tokens: int | None = None
    total_tokens: int | None = None


@dataclass
class SystemAResult:
    task_id: str | None
    question: str
    model: str
    model_version: str | None
    thinking_level: str

    generated_sql: str | None
    execution_success: bool
    columns: list[str]
    rows: list[dict[str, Any]]

    error_type: str | None
    error_message: str | None

    model_calls: int
    database_query_calls: int
    model_latency_seconds: float
    database_latency_seconds: float
    total_latency_seconds: float

    token_usage: TokenUsage

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return _json_safe(data)


def _json_safe(value: Any) -> Any:
    """Convert PostgreSQL/Python values into JSON-safe representations."""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def _strip_sql_wrapping(sql: str) -> str:
    """Remove common accidental Markdown fences without changing SQL meaning."""
    sql = sql.strip()

    fenced = re.fullmatch(
        r"```(?:sql)?\s*(.*?)\s*```",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if fenced:
        sql = fenced.group(1).strip()

    return sql


def validate_read_only_sql(sql: str) -> str:
    """Apply a conservative safety gate before PostgreSQL sees model SQL.

    PostgreSQL is ALSO placed into a read-only transaction. This function is
    therefore defense-in-depth, not the only protection.
    """
    sql = _strip_sql_wrapping(sql)

    if not sql:
        raise SQLSafetyError("The model returned empty SQL.")

    # Allow one optional trailing semicolon, but reject multiple statements.
    sql_without_trailing_semicolon = sql[:-1].rstrip() if sql.endswith(";") else sql

    if ";" in sql_without_trailing_semicolon:
        raise SQLSafetyError("Multiple SQL statements are not allowed.")

    if not re.match(r"^\s*(SELECT|WITH)\b", sql_without_trailing_semicolon, re.IGNORECASE):
        raise SQLSafetyError("Only SELECT or WITH queries are allowed.")

    forbidden = re.compile(
        r"\b("
        r"INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|TRUNCATE|CREATE|REPLACE|"
        r"GRANT|REVOKE|COPY|CALL|DO|VACUUM|ANALYZE|REFRESH|REINDEX|"
        r"CLUSTER|COMMENT|SECURITY|SET|RESET"
        r")\b",
        re.IGNORECASE,
    )

    if forbidden.search(sql_without_trailing_semicolon):
        raise SQLSafetyError("Generated SQL contains a forbidden operation.")

    # Keep the baseline inside the visible research schema.
    forbidden_sources = re.compile(
        r"\b("
        r"pg_catalog|information_schema|pg_read_file|pg_ls_dir|"
        r"dblink|postgres_fdw"
        r")\b",
        re.IGNORECASE,
    )
    if forbidden_sources.search(sql_without_trailing_semicolon):
        raise SQLSafetyError("Generated SQL attempts to access a forbidden source.")

    return sql_without_trailing_semicolon


def _extract_usage(response: Any) -> TokenUsage:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return TokenUsage()

    # Current Google Gen AI responses expose candidates_token_count.
    # Some SDK surfaces use response_token_count instead, so support both.
    output_tokens = getattr(usage, "candidates_token_count", None)
    if output_tokens is None:
        output_tokens = getattr(usage, "response_token_count", None)

    return TokenUsage(
        prompt_tokens=getattr(usage, "prompt_token_count", None),
        output_tokens=output_tokens,
        thoughts_tokens=getattr(usage, "thoughts_token_count", None),
        total_tokens=getattr(usage, "total_token_count", None),
    )


class TextToSQLBaseline:
    """System A: one model call -> one SQL query -> raw database result."""

    def __init__(
        self,
        *,
        model: str | None = None,
        thinking_level: str | None = None,
        statement_timeout_ms: int = 10_000,
        max_rows: int = 1_000,
    ) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY is not set. Set it in PowerShell before running System A."
            )

        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        self.thinking_level = (
            thinking_level
            or os.getenv("GEMINI_THINKING_LEVEL", "medium")
        ).lower()

        if self.thinking_level not in {"low", "medium", "high"}:
            raise ValueError(
                "GEMINI_THINKING_LEVEL must be one of: low, medium, high."
            )

        self.statement_timeout_ms = statement_timeout_ms
        self.max_rows = max_rows
        self.client = genai.Client(api_key=api_key)

    def generate_sql(self, question: str) -> tuple[str, Any, float]:
        """Generate exactly one SQL candidate."""
        started = time.perf_counter()

        response = self.client.models.generate_content(
            model=self.model,
            contents=question,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_A_INSTRUCTION,
                thinking_config=types.ThinkingConfig(
                    thinking_level=self.thinking_level,
                ),
                response_mime_type="application/json",
                response_schema=SQL_RESPONSE_SCHEMA,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True,
                ),
            ),
        )

        latency = time.perf_counter() - started

        if not response.text:
            raise ValueError("The model returned no text response.")

        payload = json.loads(response.text)
        sql = payload.get("sql")

        if not isinstance(sql, str):
            raise ValueError("Structured model response did not contain a SQL string.")

        return validate_read_only_sql(sql), response, latency

    def execute_sql(
        self,
        sql: str,
    ) -> tuple[list[str], list[dict[str, Any]], float]:
        """Execute one query in a read-only PostgreSQL transaction."""
        connection = get_connection()
        started = time.perf_counter()

        try:
            with connection.cursor() as cursor:
                # These are transaction controls, not analytical DB/tool calls.
                # The experimental metric database_query_calls still counts the
                # generated analytical SQL as one call.
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute(
                    f"SET LOCAL statement_timeout = '{int(self.statement_timeout_ms)}ms'"
                )

                cursor.execute(sql)

                if cursor.description is None:
                    raise RuntimeError("Generated SQL returned no result set.")

                columns = [column.name for column in cursor.description]

                fetched = cursor.fetchmany(self.max_rows + 1)
                if len(fetched) > self.max_rows:
                    raise RuntimeError(
                        f"Query exceeded the research row limit of {self.max_rows}."
                    )

                rows = [dict(row) for row in fetched]

            # Never persist anything from an evaluated query.
            connection.rollback()

            latency = time.perf_counter() - started
            return columns, rows, latency

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()

    def run(
        self,
        question: str,
        *,
        task_id: str | None = None,
    ) -> SystemAResult:
        """Run a single benchmark question with no retry or self-correction."""
        total_started = time.perf_counter()

        generated_sql: str | None = None
        model_version: str | None = None
        usage = TokenUsage()

        model_latency = 0.0
        database_latency = 0.0
        database_query_calls = 0

        try:
            generated_sql, response, model_latency = self.generate_sql(question)
            model_version = getattr(response, "model_version", None)
            usage = _extract_usage(response)

        except Exception as exc:
            return SystemAResult(
                task_id=task_id,
                question=question,
                model=self.model,
                model_version=model_version,
                thinking_level=self.thinking_level,
                generated_sql=generated_sql,
                execution_success=False,
                columns=[],
                rows=[],
                error_type=type(exc).__name__,
                error_message=str(exc),
                model_calls=1,
                database_query_calls=0,
                model_latency_seconds=round(model_latency, 6),
                database_latency_seconds=0.0,
                total_latency_seconds=round(
                    time.perf_counter() - total_started,
                    6,
                ),
                token_usage=usage,
            )

        try:
            database_query_calls = 1
            columns, rows, database_latency = self.execute_sql(generated_sql)

            return SystemAResult(
                task_id=task_id,
                question=question,
                model=self.model,
                model_version=model_version,
                thinking_level=self.thinking_level,
                generated_sql=generated_sql,
                execution_success=True,
                columns=columns,
                rows=rows,
                error_type=None,
                error_message=None,
                model_calls=1,
                database_query_calls=database_query_calls,
                model_latency_seconds=round(model_latency, 6),
                database_latency_seconds=round(database_latency, 6),
                total_latency_seconds=round(
                    time.perf_counter() - total_started,
                    6,
                ),
                token_usage=usage,
            )

        except Exception as exc:
            return SystemAResult(
                task_id=task_id,
                question=question,
                model=self.model,
                model_version=model_version,
                thinking_level=self.thinking_level,
                generated_sql=generated_sql,
                execution_success=False,
                columns=[],
                rows=[],
                error_type=type(exc).__name__,
                error_message=str(exc),
                model_calls=1,
                database_query_calls=database_query_calls,
                model_latency_seconds=round(model_latency, 6),
                database_latency_seconds=round(database_latency, 6),
                total_latency_seconds=round(
                    time.perf_counter() - total_started,
                    6,
                ),
                token_usage=usage,
            )
