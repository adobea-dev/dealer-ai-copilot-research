"""Configuration for System C."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

# ADK / Gemini ---------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
THINKING_LEVEL = os.getenv(
    "GEMINI_THINKING_LEVEL",
    "medium",
).lower()

# Neo4j ----------------------------------------------------------------------
NEO4J_URI = os.getenv(
    "NEO4J_URI",
    "bolt://localhost:7687",
)
NEO4J_USERNAME = os.getenv(
    "NEO4J_USERNAME",
    "neo4j",
)
NEO4J_PASSWORD = os.getenv(
    "NEO4J_PASSWORD",
    "",
)
NEO4J_DATABASE = os.getenv(
    "NEO4J_DATABASE",
    "neo4j",
)

# Research budgets -----------------------------------------------------------
MAX_LLM_CALLS = int(
    os.getenv("SYSTEM_C_MAX_LLM_CALLS", "5")
)
MAX_TOOL_CALLS = int(
    os.getenv("SYSTEM_C_MAX_TOOL_CALLS", "5")
)
MAX_DB_CALLS = int(
    os.getenv("SYSTEM_C_MAX_DB_CALLS", "3")
)
MAX_KG_CALLS = int(
    os.getenv("SYSTEM_C_MAX_KG_CALLS", "2")
)
MAX_CALC_CALLS = int(
    os.getenv("SYSTEM_C_MAX_CALC_CALLS", "2")
)
MAX_VIZ_CALLS = int(
    os.getenv("SYSTEM_C_MAX_VIZ_CALLS", "1")
)

STATEMENT_TIMEOUT_MS = int(
    os.getenv("SYSTEM_C_SQL_TIMEOUT_MS", "10000")
)
MAX_QUERY_ROWS = int(
    os.getenv("SYSTEM_C_MAX_QUERY_ROWS", "1000")
)

RESULTS_DIR = Path("results/system_c")
ARTIFACTS_DIR = RESULTS_DIR / "artifacts"

APP_NAME = "dealer_ai_copilot_system_c"
USER_ID = "benchmark_user"

ALLOWED_TABLES = {
    "dealers",
    "leads",
    "applications",
    "sales",
}