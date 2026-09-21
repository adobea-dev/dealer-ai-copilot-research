"""ADK plugin implementing budgets, telemetry, and tool guardrails."""

from __future__ import annotations

from typing import Any

from google.adk.plugins.base_plugin import BasePlugin

from .config import (
    MAX_CALC_CALLS,
    MAX_DB_CALLS,
    MAX_KG_CALLS,
    MAX_TOOL_CALLS,
    MAX_VIZ_CALLS,
)
from .security import json_safe


def _append_state(state, key: str, item: Any) -> None:
    """Append a JSON-safe item to a list stored in ADK session state."""
    values = list(state.get(key, []))
    values.append(json_safe(item))
    state[key] = values


def _compact(value: Any, max_chars: int = 2500) -> Any:
    """Keep trajectory logging bounded."""
    safe = json_safe(value)
    text = repr(safe)

    if len(text) <= max_chars:
        return safe

    return {
        "truncated_for_trace": True,
        "preview": text[:max_chars],
    }


class ResearchGuardPlugin(BasePlugin):
    """
    Cross-cutting resource budgets and observable trajectory logging.

    Important telemetry convention:
    - *_call_count = calls actually permitted to execute;
    - *_attempt_count = all requests made by the agent, including blocked ones.

    This prevents a blocked over-budget request from being reported as an
    executed tool call in the research results.
    """

    def __init__(self) -> None:
        super().__init__(name="system_c_research_guard")

    async def before_model_callback(
        self,
        *,
        callback_context,
        llm_request,
    ):
        state = callback_context.state

        state["model_call_count"] = (
            int(state.get("model_call_count", 0)) + 1
        )

        return None

    async def after_model_callback(
        self,
        *,
        callback_context,
        llm_response,
    ):
        state = callback_context.state

        usage = getattr(llm_response, "usage_metadata", None)

        if usage is not None:
            totals = dict(state.get("token_usage", {}))

            fields = {
                "prompt_tokens": (
                    getattr(usage, "prompt_token_count", 0) or 0
                ),
                "output_tokens": (
                    getattr(usage, "candidates_token_count", 0) or 0
                ),
                "thoughts_tokens": (
                    getattr(usage, "thoughts_token_count", 0) or 0
                ),
                "total_tokens": (
                    getattr(usage, "total_token_count", 0) or 0
                ),
            }

            for key, value in fields.items():
                totals[key] = (
                    int(totals.get(key, 0)) + int(value)
                )

            state["token_usage"] = totals

        return None

    async def before_tool_callback(
        self,
        *,
        tool,
        tool_args,
        tool_context,
    ):
        state = tool_context.state
        name = tool.name

        # ------------------------------------------------------------------
        # Determine category and configured category limit.
        # ------------------------------------------------------------------

        if name == "query_database":
            category = "database"
            call_key = "db_call_count"
            attempt_key = "db_attempt_count"
            category_limit = MAX_DB_CALLS

        elif name == "calculate":
            category = "calculation"
            call_key = "calc_call_count"
            attempt_key = "calc_attempt_count"
            category_limit = MAX_CALC_CALLS

        elif name == "create_visualization":
            category = "visualization"
            call_key = "viz_call_count"
            attempt_key = "viz_attempt_count"
            category_limit = MAX_VIZ_CALLS

        elif name.startswith("kg_"):
            category = "knowledge_graph"
            call_key = "kg_call_count"
            attempt_key = "kg_attempt_count"
            category_limit = MAX_KG_CALLS

        else:
            category = "other"
            call_key = "other_call_count"
            attempt_key = "other_attempt_count"
            category_limit = MAX_TOOL_CALLS

        # ------------------------------------------------------------------
        # Record the attempt first.
        #
        # Attempts include both permitted and blocked requests.
        # They are diagnostic and are NOT used as executed-call counts.
        # ------------------------------------------------------------------

        tool_attempt = int(state.get("tool_attempt_count", 0)) + 1
        category_attempt = int(state.get(attempt_key, 0)) + 1

        state["tool_attempt_count"] = tool_attempt
        state[attempt_key] = category_attempt

        current_total_calls = int(
            state.get("tool_call_count", 0)
        )
        current_category_calls = int(
            state.get(call_key, 0)
        )

        # ------------------------------------------------------------------
        # Enforce total tool budget BEFORE incrementing executed-call counts.
        # ------------------------------------------------------------------

        if current_total_calls >= MAX_TOOL_CALLS:
            _append_state(
                state,
                "trajectory",
                {
                    "event": "tool_blocked",
                    "tool": name,
                    "category": category,
                    "arguments": _compact(tool_args),
                    "attempt_ordinal": tool_attempt,
                    "reason": "total_tool_budget_exceeded",
                    "limit": MAX_TOOL_CALLS,
                },
            )

            return {
                "status": "blocked",
                "error_type": "total_tool_budget_exceeded",
                "message": (
                    f"Total tool-call budget of "
                    f"{MAX_TOOL_CALLS} has been reached. "
                    "Do not request another tool. "
                    "Synthesize the best grounded answer from "
                    "existing evidence."
                ),
                "retryable": False,
            }

        # ------------------------------------------------------------------
        # Enforce category-specific budget BEFORE incrementing the executed
        # category counter.
        # ------------------------------------------------------------------

        if current_category_calls >= category_limit:
            _append_state(
                state,
                "trajectory",
                {
                    "event": "tool_blocked",
                    "tool": name,
                    "category": category,
                    "arguments": _compact(tool_args),
                    "attempt_ordinal": tool_attempt,
                    "reason": f"{category}_budget_exceeded",
                    "limit": category_limit,
                },
            )

            return {
                "status": "blocked",
                "error_type": f"{category}_budget_exceeded",
                "message": (
                    f"{category} tool budget of "
                    f"{category_limit} has been reached. "
                    "Do not request this tool category again. "
                    "Use existing evidence or finish with an "
                    "explicit limitation."
                ),
                "retryable": False,
            }

        # ------------------------------------------------------------------
        # The call is permitted. Only now increment executed-call counters.
        # ------------------------------------------------------------------

        executed_total = current_total_calls + 1
        executed_category = current_category_calls + 1

        state["tool_call_count"] = executed_total
        state[call_key] = executed_category

        _append_state(
            state,
            "trajectory",
            {
                "event": "tool_call",
                "tool": name,
                "category": category,
                "arguments": _compact(tool_args),
                "ordinal": executed_total,
                "attempt_ordinal": tool_attempt,
            },
        )

        return None

    async def after_tool_callback(
        self,
        *,
        tool,
        tool_args,
        tool_context,
        result,
    ):
        _append_state(
            tool_context.state,
            "trajectory",
            {
                "event": "tool_result",
                "tool": tool.name,
                "result": _compact(result),
            },
        )

        return None

    async def on_tool_error_callback(
        self,
        *,
        tool,
        tool_args,
        tool_context,
        error,
    ):
        _append_state(
            tool_context.state,
            "trajectory",
            {
                "event": "tool_error",
                "tool": tool.name,
                "error_type": type(error).__name__,
                "message": str(error)[:1000],
            },
        )

        # Convert tool crashes into structured observations so the agent can
        # recover within its fixed budget.
        return {
            "status": "error",
            "error_type": type(error).__name__,
            "message": str(error)[:1000],
            "retryable": True,
        }