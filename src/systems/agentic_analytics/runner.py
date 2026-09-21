"""Execution wrapper for System C.

Every benchmark task receives a fresh in-memory ADK session. There is no
cross-task persistent memory.

If the ADK tool loop successfully obtains a primary factual result but does not
emit a final natural-language response, System C performs one bounded,
tool-free grounded synthesis call using the same Gemini model.

That fallback:
- receives only the original question and already-grounded tool evidence;
- cannot query PostgreSQL, Neo4j, or any other tool;
- is counted as a model call;
- is used only when ADK ended normally without final text;
- never hides an actual agent runtime exception.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

from google import genai
from google.adk.agents.run_config import RunConfig
from google.adk.runners import InMemoryRunner
from google.genai import types

from .agent import build_agent
from .config import (
    APP_NAME,
    GEMINI_API_KEY,
    MAX_LLM_CALLS,
    MODEL,
    THINKING_LEVEL,
    USER_ID,
)
from .security import (
    PolicyViolation,
    json_safe,
    redact_pii_text,
    validate_user_question,
)


@dataclass
class SystemCResult:
    task_id: str | None
    question: str
    model: str
    thinking_level: str

    execution_success: bool

    # Preserve the complete evaluator-facing primary result as well as the
    # convenience columns/rows fields.
    primary_result: dict[str, Any]
    columns: list[str]
    rows: list[dict[str, Any]]

    explanation: str | None
    visualization: str | None

    # Makes final-response recovery explicit in research logs.
    synthesis_source: str | None
    synthesis_fallback_used: bool

    error_stage: str | None
    error_type: str | None
    error_message: str | None

    model_calls: int
    database_query_calls: int
    knowledge_graph_calls: int
    calculation_calls: int
    visualization_calls: int
    total_tool_calls: int

    sql_attempts: list[dict[str, Any]]
    trajectory: list[dict[str, Any]]
    token_usage: dict[str, int]
    pii_redactions: int

    total_latency_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return json_safe(asdict(self))


def _append_trajectory(
    state: dict[str, Any],
    item: dict[str, Any],
) -> None:
    """Append a JSON-safe diagnostic event to the saved trajectory."""
    trajectory = list(state.get("trajectory", []))
    trajectory.append(json_safe(item))
    state["trajectory"] = trajectory


def _add_usage_metadata(
    state: dict[str, Any],
    usage: Any,
) -> None:
    """Add direct Gemini-call usage to the normal System C token totals."""
    if usage is None:
        return

    totals = dict(state.get("token_usage", {}))

    fields = {
        "prompt_tokens": getattr(
            usage,
            "prompt_token_count",
            0,
        ) or 0,
        "output_tokens": getattr(
            usage,
            "candidates_token_count",
            0,
        ) or 0,
        "thoughts_tokens": getattr(
            usage,
            "thoughts_token_count",
            0,
        ) or 0,
        "total_tokens": getattr(
            usage,
            "total_token_count",
            0,
        ) or 0,
    }

    for key, value in fields.items():
        totals[key] = (
            int(totals.get(key, 0))
            + int(value)
        )

    state["token_usage"] = totals


def _extract_response_text(response: Any) -> str | None:
    """
    Extract visible model text without exposing thought parts.

    response.text is normally sufficient, but the explicit candidate traversal
    makes this robust to response-shape differences.
    """
    try:
        text = getattr(response, "text", None)
        if text and str(text).strip():
            return str(text).strip()
    except Exception:
        pass

    chunks: list[str] = []

    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)

        if content is None:
            continue

        for part in getattr(content, "parts", None) or []:
            if getattr(part, "thought", False):
                continue

            part_text = getattr(part, "text", None)

            if part_text:
                chunks.append(str(part_text))

    if not chunks:
        return None

    return "\n".join(chunks).strip() or None


def _thinking_level_value() -> Any:
    """Convert configured text level to the Gen AI SDK enum."""
    configured = str(THINKING_LEVEL).strip().upper()

    mapping = {
        "MINIMAL": types.ThinkingLevel.MINIMAL,
        "LOW": types.ThinkingLevel.LOW,
        "MEDIUM": types.ThinkingLevel.MEDIUM,
        "HIGH": types.ThinkingLevel.HIGH,
    }

    return mapping.get(
        configured,
        types.ThinkingLevel.MEDIUM,
    )


async def _grounded_synthesis_fallback(
    *,
    question: str,
    primary_result: dict[str, Any],
    calculation_results: list[Any],
    visualization_path: str | None,
    state: dict[str, Any],
) -> str | None:
    """
    Perform one final no-tools synthesis call.

    This function has no access to PostgreSQL, Neo4j, benchmark gold, or tools.
    It can only verbalize evidence that the agent has already produced.
    """

    evidence = {
        "primary_postgresql_result": json_safe(primary_result),
        "deterministic_calculation_results": json_safe(
            calculation_results
        ),
        "visualization_path": json_safe(visualization_path),
    }

    synthesis_prompt = f"""
You are the final grounded synthesis stage of Dealer AI Copilot 2.0.

The analytical/tool-execution stage has already finished.

You have NO tools in this stage.
Do NOT request a tool.
Do NOT invent or infer new database values.
Do NOT change the analytical scope.
Do NOT introduce facts absent from the evidence below.

USER QUESTION
=============
{question}

GROUNDED EVIDENCE
=================
{json.dumps(evidence, ensure_ascii=False, indent=2)}

FINAL-ANSWER REQUIREMENTS
=========================
- Answer the user's question directly.
- Include every explicitly requested component that is present in the evidence.
- Preserve numerical values exactly.
- Clearly distinguish counts, percentages, percentage points, currency,
  averages, medians, rankings, and dates where applicable.
- If a visualization path is present because the user requested a chart,
  mention the generated visualization.
- Do not claim causality from aggregate observational data.
- Do not invent explanations for patterns.
- Do not expose private chain-of-thought.
- Keep the answer concise and decision-ready.
- If the supplied evidence genuinely cannot support a requested component,
  state that limitation instead of fabricating an answer.

Return only the final natural-language answer.
""".strip()

    # This is a real model call and must be represented in research telemetry.
    current_calls = int(state.get("model_call_count", 0))

    if current_calls >= MAX_LLM_CALLS:
        _append_trajectory(
            state,
            {
                "event": "synthesis_fallback_blocked",
                "reason": "model_budget_exhausted",
                "model_calls": current_calls,
                "model_limit": MAX_LLM_CALLS,
            },
        )
        return None

    state["model_call_count"] = current_calls + 1

    _append_trajectory(
        state,
        {
            "event": "synthesis_fallback_call",
            "model": MODEL,
            "tool_access": False,
            "ordinal": current_calls + 1,
        },
    )

    client = genai.Client(api_key=GEMINI_API_KEY)

    try:
        response = await client.aio.models.generate_content(
            model=MODEL,
            contents=synthesis_prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                thinking_config=types.ThinkingConfig(
                    thinking_level=_thinking_level_value(),
                    include_thoughts=False,
                ),
            ),
        )

        _add_usage_metadata(
            state,
            getattr(response, "usage_metadata", None),
        )

        final_text = _extract_response_text(response)

        if final_text:
            _append_trajectory(
                state,
                {
                    "event": "synthesis_fallback_result",
                    "status": "success",
                    "text_length": len(final_text),
                },
            )
        else:
            _append_trajectory(
                state,
                {
                    "event": "synthesis_fallback_result",
                    "status": "missing_text",
                },
            )

        return final_text

    except Exception as exc:
        _append_trajectory(
            state,
            {
                "event": "synthesis_fallback_error",
                "error_type": type(exc).__name__,
                "message": str(exc)[:1000],
            },
        )
        return None

    finally:
        try:
            await client.aio.aclose()
        except Exception:
            pass

        try:
            client.close()
        except Exception:
            pass


class AgenticAnalyticsSystem:
    """System C: bounded ADK agent with MCP-connected semantic KG."""

    def __init__(self) -> None:
        self.model = MODEL
        self.thinking_level = THINKING_LEVEL

    async def run_async(
        self,
        question: str,
        *,
        task_id: str | None = None,
    ) -> SystemCResult:
        started = time.perf_counter()

        try:
            validate_user_question(question)
        except PolicyViolation as exc:
            return SystemCResult(
                task_id=task_id,
                question=question,
                model=self.model,
                thinking_level=self.thinking_level,
                execution_success=False,
                primary_result={},
                columns=[],
                rows=[],
                explanation=(
                    "I cannot perform that request because it crosses the "
                    "system's fixed data/safety boundary."
                ),
                visualization=None,
                synthesis_source=None,
                synthesis_fallback_used=False,
                error_stage="input_guardrail",
                error_type=type(exc).__name__,
                error_message=str(exc),
                model_calls=0,
                database_query_calls=0,
                knowledge_graph_calls=0,
                calculation_calls=0,
                visualization_calls=0,
                total_tool_calls=0,
                sql_attempts=[],
                trajectory=[],
                token_usage={},
                pii_redactions=0,
                total_latency_seconds=round(
                    time.perf_counter() - started,
                    6,
                ),
            )

        session_id = f"{task_id or 'task'}_{uuid4().hex[:12]}"

        initial_state: dict[str, Any] = {
            "task_id": task_id or "adhoc",
            "question": question,
            "trajectory": [],
            "sql_attempts": [],
            "calculation_results": [],
            "visualizations": [],
            "tool_call_count": 0,
            "db_call_count": 0,
            "kg_call_count": 0,
            "calc_call_count": 0,
            "viz_call_count": 0,
            "model_call_count": 0,
            "token_usage": {},
        }

        state: dict[str, Any] = dict(initial_state)

        final_text: str | None = None
        synthesis_source: str | None = None
        synthesis_fallback_used = False

        run_error: Exception | None = None

        runner: InMemoryRunner | None = None
        kg_toolset = None
        session = None

        try:
            _root_agent, app, kg_toolset = build_agent()
            runner = InMemoryRunner(app=app)

            await runner.session_service.create_session(
                app_name=APP_NAME,
                user_id=USER_ID,
                session_id=session_id,
                state=initial_state,
            )

            new_message = types.Content(
                role="user",
                parts=[
                    types.Part.from_text(
                        text=question,
                    )
                ],
            )

            run_config = RunConfig(
                max_llm_calls=MAX_LLM_CALLS,
                custom_metadata={
                    "task_id": task_id or "adhoc",
                    "system": "C",
                },
            )

            async for event in runner.run_async(
                user_id=USER_ID,
                session_id=session_id,
                new_message=new_message,
                run_config=run_config,
            ):
                # Only treat an ADK-designated final response as the normal
                # final answer. Tool/intermediate text is deliberately not
                # promoted to final output.
                if (
                    event.is_final_response()
                    and event.content
                    and event.content.parts
                ):
                    chunks: list[str] = []

                    for part in event.content.parts:
                        # Never surface or log private thought parts.
                        if getattr(part, "thought", False):
                            continue

                        part_text = getattr(part, "text", None)

                        if part_text:
                            chunks.append(str(part_text))

                    if chunks:
                        candidate = "\n".join(chunks).strip()

                        if candidate:
                            final_text = candidate
                            synthesis_source = "adk_final_response"

        except Exception as exc:
            run_error = exc

        finally:
            # Recover the complete ADK state BEFORE closing the runner.
            if runner is not None:
                try:
                    session = await runner.session_service.get_session(
                        app_name=APP_NAME,
                        user_id=USER_ID,
                        session_id=session_id,
                    )
                except Exception:
                    session = None

            if session is not None:
                try:
                    state = dict(session.state)
                except Exception:
                    state = dict(initial_state)

            # Explicitly close MCP stdio subprocess/toolset.
            if kg_toolset is not None:
                try:
                    await kg_toolset.close()
                except Exception:
                    pass

            if runner is not None:
                try:
                    await runner.close()
                except Exception:
                    pass

        primary = json_safe(
            state.get("primary_result") or {}
        )

        columns = list(
            primary.get("columns", [])
            if isinstance(primary, dict)
            else []
        )

        rows = list(
            primary.get("rows", [])
            if isinstance(primary, dict)
            else []
        )

        visualization = state.get("visualization_path")

        # ------------------------------------------------------------------
        # Bounded final-synthesis recovery.
        #
        # Only use this when:
        #   1. the normal ADK run did NOT crash;
        #   2. PostgreSQL evidence exists;
        #   3. ADK failed only to emit final natural-language text.
        #
        # It therefore fixes the observed MissingFinalResponse behavior
        # without hiding real agent/tool runtime failures.
        # ------------------------------------------------------------------

        if (
            run_error is None
            and final_text is None
            and bool(primary)
        ):
            final_text = await _grounded_synthesis_fallback(
                question=question,
                primary_result=primary,
                calculation_results=list(
                    state.get("calculation_results", [])
                ),
                visualization_path=visualization,
                state=state,
            )

            if final_text:
                synthesis_source = "grounded_no_tool_fallback"
                synthesis_fallback_used = True

        redactions = 0

        if final_text:
            final_text, redactions = redact_pii_text(
                final_text
            )

        # ------------------------------------------------------------------
        # Final execution classification.
        # ------------------------------------------------------------------

        if run_error is not None:
            error_stage = "agent_runtime"
            error_type = type(run_error).__name__
            error_message = str(run_error)

        elif not primary:
            error_stage = "evidence_selection"
            error_type = "MissingPrimaryResult"
            error_message = (
                "Agent finished without marking a primary "
                "PostgreSQL result."
            )

        elif final_text is None:
            error_stage = "final_synthesis"
            error_type = "MissingFinalResponse"

            if int(
                state.get("model_call_count", 0)
            ) >= MAX_LLM_CALLS:
                error_message = (
                    "Agent produced no final natural-language response "
                    "and the model-call budget was exhausted before the "
                    "bounded synthesis fallback could complete."
                )
            else:
                error_message = (
                    "Agent produced no final natural-language response "
                    "and the bounded synthesis fallback also returned "
                    "no usable text."
                )

        else:
            error_stage = None
            error_type = None
            error_message = None

        success = (
            run_error is None
            and bool(primary)
            and final_text is not None
        )

        return SystemCResult(
            task_id=task_id,
            question=question,
            model=self.model,
            thinking_level=self.thinking_level,
            execution_success=success,
            primary_result=primary,
            columns=columns,
            rows=rows,
            explanation=final_text,
            visualization=visualization,
            synthesis_source=synthesis_source,
            synthesis_fallback_used=synthesis_fallback_used,
            error_stage=error_stage,
            error_type=error_type,
            error_message=error_message,
            model_calls=int(
                state.get("model_call_count", 0)
            ),
            database_query_calls=int(
                state.get("db_call_count", 0)
            ),
            knowledge_graph_calls=int(
                state.get("kg_call_count", 0)
            ),
            calculation_calls=int(
                state.get("calc_call_count", 0)
            ),
            visualization_calls=int(
                state.get("viz_call_count", 0)
            ),
            total_tool_calls=int(
                state.get("tool_call_count", 0)
            ),
            sql_attempts=json_safe(
                state.get("sql_attempts", [])
            ),
            trajectory=json_safe(
                state.get("trajectory", [])
            ),
            token_usage=json_safe(
                state.get("token_usage", {})
            ),
            pii_redactions=redactions,
            total_latency_seconds=round(
                time.perf_counter() - started,
                6,
            ),
        )

    def run(
        self,
        question: str,
        *,
        task_id: str | None = None,
    ) -> SystemCResult:
        """Synchronous convenience wrapper for benchmark scripts."""
        import asyncio

        return asyncio.run(
            self.run_async(
                question,
                task_id=task_id,
            )
        )