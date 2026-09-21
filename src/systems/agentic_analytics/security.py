"""Security and policy helpers for System C.

These checks are deliberately deterministic. They supplement, rather than
replace, model instructions and database permissions.
"""

from __future__ import annotations

import re
from typing import Any

from .config import ALLOWED_TABLES


class PolicyViolation(ValueError):
    """Raised when a request violates System C's fixed research policy."""


class SQLSafetyError(ValueError):
    """Raised when generated SQL violates the read-only database boundary."""


# Explicitly malicious/unsupported user intents used by the robustness layer.
_SECRET_TERMS = re.compile(
    r"\b(api[_ -]?key|password|secret|token|credential|pgpassword|"
    r"gemini_api_key|neo4j_password)\b",
    re.IGNORECASE,
)
_DESTRUCTIVE = re.compile(
    r"\b(delete|drop|truncate|alter|update|insert|create|grant|revoke)\b",
    re.IGNORECASE,
)
_OVERRIDE = re.compile(
    r"\b(ignore|bypass|override|disregard)\b.{0,60}"
    r"\b(instruction|policy|guardrail|system prompt|previous)\b",
    re.IGNORECASE | re.DOTALL,
)
_GOLD_ACCESS = re.compile(
    r"\b(benchmark[/\\ ]gold|gold[_ -]results|gold[_ -]queries|"
    r"research[_ -]truth|latent[_ -]quality)\b",
    re.IGNORECASE,
)


def validate_user_question(question: str) -> None:
    """Reject requests that cross the fixed experimental safety boundary."""
    text = question.strip()

    if not text:
        raise PolicyViolation("Empty request.")

    if _GOLD_ACCESS.search(text):
        raise PolicyViolation(
            "Access to benchmark gold data or hidden research-truth data is prohibited."
        )

    if _SECRET_TERMS.search(text) and re.search(
        r"\b(show|reveal|print|read|give|tell|expose|return|list)\b",
        text,
        re.IGNORECASE,
    ):
        raise PolicyViolation("Secret or credential disclosure is prohibited.")

    if _DESTRUCTIVE.search(text) and re.search(
        r"\b(database|table|row|record|dealer|lead|application|sale)\b",
        text,
        re.IGNORECASE,
    ):
        raise PolicyViolation("Database modification requests are prohibited.")

    if _OVERRIDE.search(text):
        raise PolicyViolation(
            "Requests to override or bypass system/tool policies are prohibited."
        )


def validate_read_only_sql(sql: str) -> str:
    """Validate one read-only query and restrict physical table access."""
    text = sql.strip()

    # Strip an accidental Markdown code fence.
    fenced = re.fullmatch(
        r"```(?:sql)?\s*(.*?)\s*```",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if fenced:
        text = fenced.group(1).strip()

    if not text:
        raise SQLSafetyError("SQL is empty.")

    # Permit a single optional trailing semicolon.
    text = text[:-1].rstrip() if text.endswith(";") else text

    if ";" in text:
        raise SQLSafetyError("Multiple SQL statements are not allowed.")

    if not re.match(r"^\s*(SELECT|WITH)\b", text, re.IGNORECASE):
        raise SQLSafetyError("Only SELECT or WITH statements are allowed.")

    forbidden = re.compile(
        r"\b("
        r"INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|TRUNCATE|CREATE|REPLACE|"
        r"GRANT|REVOKE|COPY|CALL|DO|VACUUM|ANALYZE|REFRESH|REINDEX|"
        r"CLUSTER|COMMENT|SECURITY|SET|RESET|EXECUTE"
        r")\b",
        re.IGNORECASE,
    )
    if forbidden.search(text):
        raise SQLSafetyError("SQL contains a forbidden operation.")

    forbidden_sources = re.compile(
        r"\b("
        r"pg_catalog|information_schema|pg_read_file|pg_ls_dir|"
        r"dblink|postgres_fdw|lo_import|lo_export"
        r")\b",
        re.IGNORECASE,
    )
    if forbidden_sources.search(text):
        raise SQLSafetyError("SQL attempts to access a forbidden source.")

    # Extract CTE names so FROM/JOIN references to them are not mistaken for
    # physical tables.
    cte_names = {
        match.lower()
        for match in re.findall(
            r"(?:WITH|,)\s*([A-Za-z_][A-Za-z0-9_]*)\s+AS\s*\(",
            text,
            flags=re.IGNORECASE,
        )
    }

    table_refs = {
        match.lower().split(".")[-1]
        for match in re.findall(
            r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_\.]*)",
            text,
            flags=re.IGNORECASE,
        )
    }

    unknown = sorted(
        ref
        for ref in table_refs
        if ref not in ALLOWED_TABLES and ref not in cte_names
    )
    if unknown:
        raise SQLSafetyError(
            "SQL references non-allowlisted relations: " + ", ".join(unknown)
        )

    return text


# Lightweight output redaction. The research database contains no real PII;
# this is defense-in-depth for future extensions.
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_CARD = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")


def redact_pii_text(text: str) -> tuple[str, int]:
    """Redact common direct identifiers from final free-text output."""
    count = 0

    def sub(pattern: re.Pattern[str], replacement: str, value: str) -> str:
        nonlocal count
        matches = list(pattern.finditer(value))
        count += len(matches)
        return pattern.sub(replacement, value)

    text = sub(_EMAIL, "[REDACTED_EMAIL]", text)
    text = sub(_CARD, "[REDACTED_NUMBER]", text)
    # Phone redaction comes last because numeric business metrics should not
    # normally match unless they resemble a long phone-like sequence.
    text = sub(_PHONE, "[REDACTED_PHONE]", text)

    return text, count


def json_safe(value: Any) -> Any:
    """Recursively keep only JSON-friendly values for logs/state."""
    from datetime import date, datetime
    from decimal import Decimal
    from uuid import UUID

    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value
