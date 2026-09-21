"""Deterministic common evaluator for Dealer AI Copilot 2.0.

This evaluator is shared by Systems A, B, and C.

Important principles
--------------------
1. Execution success is not benchmark correctness.
2. SQL string equality is never used.
3. Required components are scored semantically.
4. Column names may differ when their meaning is unambiguous.
5. Counts must match exactly.
6. USD values use +/- 0.01 tolerance.
7. Percentages use +/- 0.01 percentage-point tolerance.
8. Other decimal values use +/- 0.0001 tolerance.
9. Rankings allow arbitrary ordering inside tied metric groups.
10. Explanation and visualization are scored only when required.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


# ---------------------------------------------------------------------
# DEFAULT BENCHMARK LOCATIONS
# ---------------------------------------------------------------------

TASKS_PATH = Path("benchmark/tasks_v1.json")
GOLD_RESULTS_PATH = Path("benchmark/gold/gold_results_v1.json")

# Backwards-compatible alias in case another script imports GOLD_PATH.
GOLD_PATH = GOLD_RESULTS_PATH


# ---------------------------------------------------------------------
# COMPONENT CATEGORIES
# ---------------------------------------------------------------------

PRESENTATION_COMPONENTS = {
    "explanation",
    "visualization",
}

RANKING_COMPONENTS = {
    "descending_ranking",
    "ascending_ranking",
    "descending_lead_volume",
}

META_COMPONENTS = {
    "highest_sales_month",
    "highest_revenue_quarter",
    "highest_percentage_month",
    "largest_gap_month",
    "highest_revenue_month",
    "highest_lead_to_sale_country",
    "highest_lead_to_sale_quarter",
    "same_country_leads_both",
}


# Identity columns used to align semantic rows.
IDENTITY_PRIORITY = (
    "dealer_name",
    "financing_bank",
    "country",
    "quarter",
    "month",
)


# ---------------------------------------------------------------------
# SEMANTIC COLUMN ALIASES
# ---------------------------------------------------------------------
#
# IMPORTANT:
#
# These are tuples, not sets.
#
# Order matters. If an agent returns more than one semantically similar
# column, the evaluator chooses the first valid alias deterministically.
#
# This avoids the non-deterministic behaviour of iterating Python sets.
# ---------------------------------------------------------------------

ALIASES: dict[str, tuple[str, ...]] = {

    # -------------------------------------------------------------
    # Dealer / identity fields
    # -------------------------------------------------------------

    "dealer_count": (
        "dealer_count",
        "total_dealers",
        "dealers",
        "count_dealers",
        "count",
    ),

    "dealer_name": (
        "dealer_name",
        "dealer",
        "dealership_name",
        "dealership",
    ),

    "country": (
        "country",
        "country_code",
    ),

    "month": (
        "month",
        "month_name",
        "calendar_month",
    ),

    "quarter": (
        "quarter",
        "calendar_quarter",
    ),

    "financing_bank": (
        "financing_bank",
        "bank",
        "bank_name",
        "financier",
    ),

    # -------------------------------------------------------------
    # Leads
    # -------------------------------------------------------------

    "lead_count": (
        "lead_count",
        "total_leads",
        "leads",
        "distinct_lead_count",
        "lead_total",
    ),

    "leads": (
        "leads",
        "lead_count",
        "total_leads",
        "distinct_lead_count",
        "lead_total",
    ),

    "referral_lead_count": (
        "referral_lead_count",
        "referral_leads",
        "referral_count",
        "total_referral_leads",
    ),

    # -------------------------------------------------------------
    # Applications
    # -------------------------------------------------------------

    "application_count": (
        "application_count",
        "applications",
        "total_applications",

        # Prefer a distinct entity count over a joined raw count when
        # both are available.
        "distinct_application_count",

        # System C observed variants.
        "total_application_count",
        "application_record_count",
        "application_total",
    ),

    "applications": (
        "applications",
        "application_count",
        "total_applications",
        "distinct_application_count",
        "total_application_count",
        "application_record_count",
        "application_total",
    ),

    "approved_application_count": (
        "approved_application_count",
        "approved_applications",
        "approved_count",
        "total_approved_applications",
        "approved_application_total",
    ),

    "approved_applications": (
        "approved_applications",
        "approved_application_count",
        "approved_count",
        "total_approved_applications",
        "approved_application_total",
    ),

    "rejected_application_count": (
        "rejected_application_count",
        "rejected_applications",
        "rejected_count",
        "total_rejected_applications",
        "rejected_application_total",
    ),

    # -------------------------------------------------------------
    # Sales / revenue
    # -------------------------------------------------------------

    "sales_count": (
        "sales_count",
        "sales",
        "sale_count",
        "total_sales",
        "distinct_sales_count",
        "distinct_sale_count",
        "sales_total",
    ),

    "sales": (
        "sales",
        "sales_count",
        "sale_count",
        "total_sales",
        "distinct_sales_count",
        "distinct_sale_count",
        "sales_total",
    ),

    "revenue_usd": (
        "revenue_usd",
        "revenue",
        "total_revenue",
        "total_revenue_usd",
        "total_sales_revenue",
        "total_sales_revenue_usd",
        "sales_revenue",
        "sales_revenue_usd",
    ),

    "average_sale_value_usd": (
        "average_sale_value_usd",
        "avg_sale_value_usd",
        "average_sale_amount_usd",
        "avg_sale_amount_usd",
        "average_sale_value",
        "avg_sale_value",
    ),

    "revenue_per_sale_usd": (
        "revenue_per_sale_usd",
        "average_revenue_per_sale_usd",
        "avg_revenue_per_sale_usd",
        "revenue_per_sale",
        "average_revenue_per_sale",
    ),

    # -------------------------------------------------------------
    # Generic C4 conversion
    # -------------------------------------------------------------
    #
    # conversion_pct is intentionally generic in the benchmark.
    # The task wording determines which funnel transition it means.
    # -------------------------------------------------------------

    "conversion_pct": (
        "conversion_pct",
        "conversion_percentage",
        "conversion_rate",
        "percentage",

        # Lead -> application
        "lead_to_application_pct",
        "lead_to_application_percentage",
        "lead_to_application_rate",
        "percentage_leads_with_application",
        "percentage_of_leads_with_application",

        # Lead -> sale
        "lead_to_sale_pct",
        "lead_to_sale_percentage",
        "lead_to_sale_rate",
        "percentage_leads_with_sale",
        "percentage_leads_with_sales",

        # Approved application -> sale
        "approved_to_sale_pct",
        "approved_to_sale_percentage",
        "approved_to_sale_rate",
        "approval_to_sale_pct",
        "percentage_approved_applications_with_sale",
        "percentage_approved_applications_with_sales",

        # General application -> sale variants
        "application_to_sale_pct",
        "application_to_sale_percentage",
        "application_to_sale_rate",
    ),

    "approval_pct": (
        "approval_pct",
        "approval_percentage",
        "approval_rate",
        "application_approval_pct",
        "application_approval_percentage",
        "application_approval_rate",
        "percentage_applications_approved",
        "percentage_of_applications_approved",
    ),

    "rejection_pct": (
        "rejection_pct",
        "rejection_percentage",
        "rejection_rate",
        "application_rejection_pct",
        "application_rejection_percentage",
        "application_rejection_rate",
        "percentage_applications_rejected",
        "percentage_of_applications_rejected",
    ),

    "growth_pct": (
        "growth_pct",
        "growth_percentage",
        "percentage_change",
        "pct_change",
        "sales_growth_pct",
        "sales_percentage_change",
    ),

    # -------------------------------------------------------------
    # Year-over-year / temporal fields
    # -------------------------------------------------------------

    "sales_2024": (
        "sales_2024",
        "sales_count_2024",
        "sales2024",
        "sales_2024_count",
    ),

    "sales_2025": (
        "sales_2025",
        "sales_count_2025",
        "sales2025",
        "sales_2025_count",
    ),

    "leads_2024": (
        "leads_2024",
        "lead_count_2024",
        "leads2024",
    ),

    "leads_2025": (
        "leads_2025",
        "lead_count_2025",
        "leads2025",
    ),

    "difference": (
        "difference",
        "sales_difference",
        "difference_sales",
        "sales_gap",
    ),

    "gap": (
        "gap",
        "application_sales_gap",
        "applications_sales_gap",
        "applications_minus_sales",
        "difference",
    ),

    "applications_per_lead_pct": (
        "applications_per_lead_pct",
        "applications_per_lead_percentage",
        "application_to_lead_pct",
        "application_lead_pct",
        "applications_divided_by_leads_pct",
    ),

    # -------------------------------------------------------------
    # C6 funnel metrics
    # -------------------------------------------------------------

    "lead_to_application_pct": (
        "lead_to_application_pct",
        "lead_to_application_percentage",
        "lead_to_application_rate",
        "percentage_leads_with_application",
        "percentage_of_leads_with_application",
    ),

    "application_approval_pct": (
        "application_approval_pct",
        "application_approval_percentage",
        "application_approval_rate",
        "approval_pct",
        "approval_percentage",
        "approval_rate",
        "percentage_applications_approved",
    ),

    "approved_to_sale_pct": (
        "approved_to_sale_pct",
        "approved_to_sale_percentage",
        "approved_to_sale_rate",
        "approval_to_sale_pct",
        "approved_application_to_sale_pct",
        "percentage_approved_applications_sold",
    ),

    "lead_to_sale_pct": (
        "lead_to_sale_pct",
        "lead_to_sale_percentage",
        "lead_to_sale_rate",
        "percentage_leads_with_sale",
        "percentage_leads_with_sales",
    ),

    "median_lead_to_sale_pct": (
        "median_lead_to_sale_pct",
        "median_lead_to_sale_percentage",
        "median_reference_percentage",
        "median_reference_pct",
        "median_conversion_pct",
        "overall_median_lead_to_sale_pct",
    ),

    "lead_to_sale_pct_2024": (
        "lead_to_sale_pct_2024",
        "lead_to_sale_percentage_2024",
        "lead_to_sale_rate_2024",
    ),

    "lead_to_sale_pct_2025": (
        "lead_to_sale_pct_2025",
        "lead_to_sale_percentage_2025",
        "lead_to_sale_rate_2025",
    ),

    "improvement_percentage_points": (
        "improvement_percentage_points",
        "percentage_point_improvement",
        "improvement_pp",
        "lead_to_sale_improvement_percentage_points",
    ),

    "weakest_stage": (
        "weakest_stage",
        "weakest_funnel_stage",
        "funnel_weakest_stage",
    ),

    "conversion_rank": (
        "conversion_rank",
        "lead_to_sale_rank",
        "conversion_ranking",
    ),

    "revenue_rank": (
        "revenue_rank",
        "revenue_ranking",
    ),

    "same_country_leads_both": (
        "same_country_leads_both",
        "same_country_top_both",
        "same_country_leads_both_rankings",
    ),

    # -------------------------------------------------------------
    # Explicit derived-output aliases
    # -------------------------------------------------------------

    "highest_sales_month": (
        "highest_sales_month",
        "top_sales_month",
        "month_with_highest_sales",
    ),

    "highest_revenue_quarter": (
        "highest_revenue_quarter",
        "top_revenue_quarter",
        "quarter_with_highest_revenue",
    ),

    "highest_percentage_month": (
        "highest_percentage_month",
        "top_percentage_month",
        "month_with_highest_percentage",
    ),

    "largest_gap_month": (
        "largest_gap_month",
        "month_with_largest_gap",
        "max_gap_month",
    ),

    "highest_revenue_month": (
        "highest_revenue_month",
        "top_revenue_month",
        "month_with_highest_revenue",
    ),

    "highest_lead_to_sale_country": (
        "highest_lead_to_sale_country",
        "top_lead_to_sale_country",
        "country_with_highest_lead_to_sale",
    ),

    "highest_lead_to_sale_quarter": (
        "highest_lead_to_sale_quarter",
        "top_lead_to_sale_quarter",
        "quarter_with_highest_lead_to_sale",
    ),
}


# ---------------------------------------------------------------------
# NUMERIC SEMANTICS
# ---------------------------------------------------------------------

COUNT_COMPONENTS = {
    "dealer_count",
    "lead_count",
    "leads",
    "referral_lead_count",
    "application_count",
    "applications",
    "approved_application_count",
    "approved_applications",
    "rejected_application_count",
    "sales_count",
    "sales",
    "sales_2024",
    "sales_2025",
    "leads_2024",
    "leads_2025",
    "conversion_rank",
    "revenue_rank",
}


PERCENTAGE_COMPONENT_HINTS = (
    "_pct",
    "_percentage",
    "_rate",
    "percentage_points",
)


# Strong causal wording that should not appear in a benchmark explanation
# unless causal evidence exists. The benchmark only contains observational
# aggregate analytics.
STRONG_CAUSAL_PATTERNS = (
    r"\bcaused\b",
    r"\bcauses\b",
    r"\bcausing\b",
    r"\bdriven by\b",
    r"\bled to\b",
    r"\bresulted from\b",
    r"\bresponsible for\b",
)


# ---------------------------------------------------------------------
# RESULT OBJECTS
# ---------------------------------------------------------------------

@dataclass
class ComponentScore:
    component: str
    correct: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TaskEvaluation:
    task_id: str

    execution_success: bool
    factual_correctness: bool
    full_task_success: bool

    component_completion: float
    correct_components: int
    total_components: int

    components: list[ComponentScore]

    column_mapping: dict[str, str]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Compatibility aliases.
EvaluationResult = TaskEvaluation
TaskScore = TaskEvaluation
ComponentEvaluation = ComponentScore


# ---------------------------------------------------------------------
# FILE LOADING
# ---------------------------------------------------------------------

def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _index_by_task_id(
    data: Any,
) -> dict[str, dict[str, Any]]:
    """Normalize supported JSON structures to task_id -> record."""

    if isinstance(data, dict):

        # Common shape:
        #
        # {
        #   "C1_DEV_01": {...},
        #   ...
        # }
        if data and all(
            isinstance(value, dict)
            for value in data.values()
        ):
            indexed: dict[str, dict[str, Any]] = {}

            for key, value in data.items():
                record = dict(value)
                record.setdefault("task_id", key)
                indexed[str(key)] = record

            return indexed

        # Alternate wrapped shapes.
        for key in (
            "results",
            "tasks",
            "gold",
        ):
            value = data.get(key)

            if isinstance(value, list):
                return _index_by_task_id(value)

    if isinstance(data, list):
        indexed = {}

        for item in data:
            if not isinstance(item, dict):
                continue

            task_id = item.get("task_id")

            if task_id:
                indexed[str(task_id)] = dict(item)

        return indexed

    raise ValueError(
        "Could not index JSON records by task_id."
    )


def _normalize_gold_record(
    record: dict[str, Any],
) -> dict[str, Any]:
    """Accept both columns/rows and expected_columns/expected_rows."""

    columns = (
        record.get("columns")
        or record.get("expected_columns")
        or []
    )

    rows = (
        record.get("rows")
        or record.get("expected_rows")
        or []
    )

    return {
        **record,
        "columns": list(columns),
        "rows": list(rows),
    }


# ---------------------------------------------------------------------
# NORMALIZATION
# ---------------------------------------------------------------------

def _norm(value: Any) -> str:
    text = str(value or "").strip().lower()

    text = text.replace(
        "%",
        "pct",
    )

    text = re.sub(
        r"[^a-z0-9]+",
        "_",
        text,
    )

    text = re.sub(
        r"_+",
        "_",
        text,
    )

    return text.strip("_")


def _is_number(
    value: Any,
) -> bool:
    if value is None or isinstance(value, bool):
        return False

    try:
        number = float(value)

    except (
        TypeError,
        ValueError,
    ):
        return False

    return math.isfinite(number)


def _number(
    value: Any,
) -> float | None:
    if not _is_number(value):
        return None

    return float(value)


def _canonical_temporal_value(
    component: str,
    value: Any,
) -> str | None:
    """Normalize benchmark month/quarter identities across equivalent formats.

    PostgreSQL date buckets are serialized in the frozen gold files as values
    such as ``2025-04-01`` while a system may correctly return the same month
    as ``2025-04``.  Those representations are semantically identical for a
    benchmark component named ``month``.  The same principle is applied to
    quarter identities.
    """

    normalized_component = _norm(component)

    if normalized_component not in {"month", "quarter"}:
        return None

    if value is None:
        return None

    # Support date/datetime-like objects without importing pandas.
    if (
        normalized_component == "month"
        and hasattr(value, "year")
        and hasattr(value, "month")
    ):
        try:
            return f"{int(value.year):04d}-{int(value.month):02d}"
        except (TypeError, ValueError):
            pass

    text = str(value).strip()
    if not text:
        return None

    if normalized_component == "month":
        # YYYY-MM, YYYY-MM-DD, and ISO timestamps.  Since the benchmark
        # component itself is a month bucket, any day in that month maps to
        # the same semantic month identity.
        match = re.match(
            r"^(\d{4})[-/](\d{1,2})(?:[-/](\d{1,2}))?(?:[T\s].*)?$",
            text,
        )
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            if 1 <= month <= 12:
                return f"{year:04d}-{month:02d}"

        # Common human-readable month forms.
        month_names = {
            "jan": 1, "january": 1,
            "feb": 2, "february": 2,
            "mar": 3, "march": 3,
            "apr": 4, "april": 4,
            "may": 5,
            "jun": 6, "june": 6,
            "jul": 7, "july": 7,
            "aug": 8, "august": 8,
            "sep": 9, "sept": 9, "september": 9,
            "oct": 10, "october": 10,
            "nov": 11, "november": 11,
            "dec": 12, "december": 12,
        }

        lowered = text.lower().replace(",", " ")
        tokens = [token for token in re.split(r"[\s_/.-]+", lowered) if token]

        year = next(
            (int(token) for token in tokens if re.fullmatch(r"\d{4}", token)),
            None,
        )
        month = next(
            (month_names[token] for token in tokens if token in month_names),
            None,
        )

        if year is not None and month is not None:
            return f"{year:04d}-{month:02d}"

        return None

    # Quarter formats: 2025-Q1, 2025 Q1, Q1-2025, Q1 2025.
    compact = re.sub(r"[^a-z0-9]+", "", text.lower())

    match = re.fullmatch(r"(\d{4})q([1-4])", compact)
    if match:
        return f"{int(match.group(1)):04d}-Q{match.group(2)}"

    match = re.fullmatch(r"q([1-4])(\d{4})", compact)
    if match:
        return f"{int(match.group(2)):04d}-Q{match.group(1)}"

    return None


# ---------------------------------------------------------------------
# NUMERIC COMPARISON
# ---------------------------------------------------------------------

def _is_count_component(
    component: str,
) -> bool:
    normalized = _norm(component)

    return (
        normalized in COUNT_COMPONENTS
        or normalized.endswith("_count")
        or normalized.startswith("count_")
    )


def _is_usd_component(
    component: str,
) -> bool:
    normalized = _norm(component)

    return (
        "usd" in normalized
        or normalized
        in {
            "revenue",
            "total_revenue",
            "sales_revenue",
        }
    )


def _is_percentage_component(
    component: str,
) -> bool:
    normalized = _norm(component)

    return any(
        hint in normalized
        for hint in PERCENTAGE_COMPONENT_HINTS
    )


def _equal(
    expected: Any,
    actual: Any,
    component: str,
) -> bool:
    """Compare one gold value with one returned value."""

    if expected is None or actual is None:
        return (
            expected is None
            and actual is None
        )

    expected_temporal = _canonical_temporal_value(
        component,
        expected,
    )
    actual_temporal = _canonical_temporal_value(
        component,
        actual,
    )

    if (
        expected_temporal is not None
        or actual_temporal is not None
    ):
        return (
            expected_temporal is not None
            and actual_temporal is not None
            and expected_temporal == actual_temporal
        )

    if isinstance(expected, bool) or isinstance(actual, bool):
        return bool(expected) is bool(actual)

    expected_num = _number(expected)
    actual_num = _number(actual)

    if (
        expected_num is not None
        and actual_num is not None
    ):

        # Exact counts.
        if _is_count_component(component):
            return (
                expected_num
                == actual_num
            )

        # USD +/- 0.01.
        if _is_usd_component(component):
            return math.isclose(
                expected_num,
                actual_num,
                rel_tol=0.0,
                abs_tol=0.01,
            )

        # Percentage points +/- 0.01.
        if _is_percentage_component(component):
            return math.isclose(
                expected_num,
                actual_num,
                rel_tol=0.0,
                abs_tol=0.01,
            )

        # Generic decimal.
        return math.isclose(
            expected_num,
            actual_num,
            rel_tol=0.0,
            abs_tol=0.0001,
        )

    return (
        _norm(expected)
        == _norm(actual)
    )


# ---------------------------------------------------------------------
# SEMANTIC COLUMN MAPPING
# ---------------------------------------------------------------------

def _alias_candidates(
    expected: str,
) -> tuple[str, ...]:
    normalized = _norm(expected)

    aliases = ALIASES.get(
        normalized
    )

    if not aliases:
        return (normalized,)

    ordered = [normalized]

    ordered.extend(
        _norm(alias)
        for alias in aliases
    )

    seen: set[str] = set()
    result: list[str] = []

    for candidate in ordered:
        if candidate in seen:
            continue

        seen.add(candidate)
        result.append(candidate)

    return tuple(result)


def _build_mapping(
    expected_columns: list[str],
    actual_columns: list[str],
) -> tuple[
    dict[str, str],
    list[str],
]:
    """
    Build deterministic semantic column mapping.

    IMPORTANT:
    No positional fallback is used.

    Same-width tables are not automatically semantically equivalent.
    """

    mapping: dict[str, str] = {}
    notes: list[str] = []

    actual_norm: dict[str, str] = {}

    for column in actual_columns:
        normalized = _norm(column)

        actual_norm.setdefault(
            normalized,
            column,
        )

    used: set[str] = set()

    # -------------------------------------------------------------
    # Pass 1: exact normalized column names.
    # -------------------------------------------------------------

    for expected in expected_columns:
        actual = actual_norm.get(
            _norm(expected)
        )

        if (
            actual is not None
            and actual not in used
        ):
            mapping[expected] = actual
            used.add(actual)

    # -------------------------------------------------------------
    # Pass 2: semantic aliases.
    # -------------------------------------------------------------

    for expected in expected_columns:

        if expected in mapping:
            continue

        for candidate in _alias_candidates(
            expected
        ):

            actual = actual_norm.get(
                candidate
            )

            if (
                actual is None
                or actual in used
            ):
                continue

            mapping[expected] = actual
            used.add(actual)

            if (
                _norm(expected)
                != _norm(actual)
            ):
                notes.append(
                    f"Alias mapping: "
                    f"{expected} -> {actual}"
                )

            break

    return mapping, notes


# ---------------------------------------------------------------------
# ROW ALIGNMENT
# ---------------------------------------------------------------------

def _identity_columns(
    expected_columns: list[str],
    mapping: dict[str, str],
) -> list[str]:

    present = [
        column
        for column in IDENTITY_PRIORITY
        if (
            column in expected_columns
            and column in mapping
        )
    ]

    if "dealer_name" in present:
        return ["dealer_name"]

    if (
        "country" in present
        and "quarter" in present
    ):
        return [
            "country",
            "quarter",
        ]

    if (
        "country" in present
        and "month" in present
    ):
        return [
            "country",
            "month",
        ]

    if "financing_bank" in present:
        return ["financing_bank"]

    if "quarter" in present:
        return ["quarter"]

    if "month" in present:
        return ["month"]

    if "country" in present:
        return ["country"]

    return []


def _row_key(
    row: dict[str, Any],
    identity_columns: list[str],
    mapping: dict[str, str] | None = None,
) -> tuple[Any, ...]:

    values: list[Any] = []

    for column in identity_columns:

        source = (
            mapping[column]
            if mapping
            else column
        )

        value = row.get(source)

        temporal_value = _canonical_temporal_value(
            column,
            value,
        )

        if temporal_value is not None:
            value = temporal_value
        elif isinstance(value, str):
            value = _norm(value)

        values.append(value)

    return tuple(values)


def _align_rows(
    expected_rows: list[dict[str, Any]],
    actual_rows: list[dict[str, Any]],
    expected_columns: list[str],
    mapping: dict[str, str],
) -> tuple[
    list[
        tuple[
            dict[str, Any],
            dict[str, Any],
        ]
    ],
    bool,
    str,
]:

    if (
        len(expected_rows)
        != len(actual_rows)
    ):
        return (
            [],
            False,
            (
                "Returned row count differs "
                "from gold: "
                f"expected {len(expected_rows)}, "
                f"actual {len(actual_rows)}."
            ),
        )

    # Scalar / one-row results.
    if len(expected_rows) <= 1:
        return (
            list(
                zip(
                    expected_rows,
                    actual_rows,
                )
            ),
            True,
            "Single-row output aligned.",
        )

    identities = _identity_columns(
        expected_columns,
        mapping,
    )

    if not identities:
        return (
            [],
            False,
            (
                "No stable identity column "
                "available for multi-row alignment."
            ),
        )

    expected_index: dict[
        tuple[Any, ...],
        dict[str, Any],
    ] = {}

    actual_index: dict[
        tuple[Any, ...],
        dict[str, Any],
    ] = {}

    for row in expected_rows:

        key = _row_key(
            row,
            identities,
        )

        if key in expected_index:
            return (
                [],
                False,
                (
                    "Gold result contains "
                    "duplicate row identities."
                ),
            )

        expected_index[key] = row

    for row in actual_rows:

        key = _row_key(
            row,
            identities,
            mapping,
        )

        if key in actual_index:
            return (
                [],
                False,
                (
                    "Returned result contains "
                    "duplicate row identities."
                ),
            )

        actual_index[key] = row

    if (
        set(expected_index)
        != set(actual_index)
    ):
        return (
            [],
            False,
            (
                "Returned row identities "
                "do not match gold."
            ),
        )

    aligned = [
        (
            expected_index[key],
            actual_index[key],
        )
        for key in expected_index
    ]

    return (
        aligned,
        True,
        "Rows aligned by semantic identity.",
    )


# ---------------------------------------------------------------------
# DIRECT COMPONENT SCORING
# ---------------------------------------------------------------------

def _direct_component_correct(
    component: str,
    expected_columns: list[str],
    expected_rows: list[dict[str, Any]],
    actual_rows: list[dict[str, Any]],
    mapping: dict[str, str],
) -> tuple[bool, str]:

    if component not in expected_columns:
        return (
            False,
            (
                "No direct gold column for "
                f"{component!r}."
            ),
        )

    if component not in mapping:
        return (
            False,
            (
                "No returned column mapped to "
                f"{component!r}."
            ),
        )

    aligned, ok, detail = _align_rows(
        expected_rows,
        actual_rows,
        expected_columns,
        mapping,
    )

    if not ok:
        return False, detail

    actual_column = mapping[
        component
    ]

    for (
        expected_row,
        actual_row,
    ) in aligned:

        expected_value = (
            expected_row.get(
                component
            )
        )

        actual_value = (
            actual_row.get(
                actual_column
            )
        )

        if not _equal(
            expected_value,
            actual_value,
            component,
        ):
            return (
                False,
                (
                    f"{component} mismatch: "
                    f"expected "
                    f"{expected_value!r}, "
                    f"actual "
                    f"{actual_value!r}. "
                    f"{detail}"
                ),
            )

    return (
        True,
        f"{component} matches gold.",
    )


# ---------------------------------------------------------------------
# RANKING
# ---------------------------------------------------------------------

def _ranking_metric(
    task: dict[str, Any],
    component: str,
    expected_columns: list[str],
) -> str | None:

    required = set(
        task.get(
            "required_components",
            [],
        )
    )

    prompt = str(
        task.get(
            "prompt",
            "",
        )
    ).lower()

    # Explicit C6_DEV_01 ranking component.
    if component == "descending_lead_volume":

        if "leads" in expected_columns:
            return "leads"

        if "lead_count" in expected_columns:
            return "lead_count"

        return None

    # C6_TEST_05.
    if (
        "improvement_percentage_points"
        in required
    ):
        return (
            "improvement_percentage_points"
        )

    # C6_TEST_01.
    if (
        "lead_to_sale_pct" in required
        and "highest eventual lead-to-sale"
        in prompt
    ):
        return "lead_to_sale_pct"

    # Revenue ranking has priority over sales count
    # when both appear in a revenue-ranking task.
    if (
        "revenue" in prompt
        and "revenue_usd"
        in expected_columns
    ):
        return "revenue_usd"

    if (
        "referral" in prompt
        and "referral_lead_count"
        in expected_columns
    ):
        return "referral_lead_count"

    if (
        "application" in prompt
        and "application_count"
        in expected_columns
    ):
        return "application_count"

    if (
        "sales" in prompt
        and "sales_count"
        in expected_columns
    ):
        return "sales_count"

    if "lead" in prompt:

        if "lead_count" in expected_columns:
            return "lead_count"

        if "leads" in expected_columns:
            return "leads"

    # Deterministic fallback.
    priority = (
        "lead_to_sale_pct",
        "improvement_percentage_points",
        "revenue_usd",
        "application_count",
        "sales_count",
        "referral_lead_count",
        "lead_count",
        "leads",
    )

    for candidate in priority:

        if candidate in expected_columns:
            return candidate

    return None


def _ranking_correct(
    task: dict[str, Any],
    component: str,
    expected_rows: list[dict[str, Any]],
    actual_rows: list[dict[str, Any]],
    expected_columns: list[str],
    mapping: dict[str, str],
) -> tuple[bool, str]:

    identities = _identity_columns(
        expected_columns,
        mapping,
    )

    if not identities:
        return (
            False,
            (
                "No stable identity "
                "column for ranking."
            ),
        )

    if (
        len(expected_rows)
        != len(actual_rows)
    ):
        return (
            False,
            (
                "Ranking row count "
                "differs from gold."
            ),
        )

    expected_identities = [
        _row_key(
            row,
            identities,
        )
        for row in expected_rows
    ]

    actual_identities = [
        _row_key(
            row,
            identities,
            mapping,
        )
        for row in actual_rows
    ]

    # Correct entities must be present.
    if (
        set(expected_identities)
        != set(actual_identities)
    ):
        return (
            False,
            (
                "Ranked entities "
                "do not match gold."
            ),
        )

    metric = _ranking_metric(
        task,
        component,
        expected_columns,
    )

    # If metric cannot be identified,
    # require exact ordering.
    if metric is None:

        if (
            expected_identities
            == actual_identities
        ):
            return (
                True,
                "Ranking order matches gold.",
            )

        return (
            False,
            (
                "Could not identify ranking "
                "metric and entity order differs."
            ),
        )

    if metric not in mapping:
        return (
            False,
            (
                "No returned column mapped "
                f"to ranking metric {metric!r}."
            ),
        )

    actual_metric_column = (
        mapping[metric]
    )

    expected_metric_values = [
        row.get(metric)
        for row in expected_rows
    ]

    actual_metric_values = [
        row.get(actual_metric_column)
        for row in actual_rows
    ]

    for (
        expected_value,
        actual_value,
    ) in zip(
        expected_metric_values,
        actual_metric_values,
    ):

        if not _equal(
            expected_value,
            actual_value,
            metric,
        ):
            return (
                False,
                (
                    "Ranking metric sequence "
                    f"differs for {metric!r}. "
                    f"Expected "
                    f"{expected_metric_values!r}; "
                    f"actual "
                    f"{actual_metric_values!r}."
                ),
            )

    if (
        expected_identities
        == actual_identities
    ):
        return (
            True,
            (
                f"Ranking by {metric} "
                "matches gold."
            ),
        )

    # Metric sequence matches and entity set matches.
    # Therefore differing order is only inside tied groups.
    return (
        True,
        (
            f"Ranking by {metric} "
            "matches gold; entity order "
            "differs only within tied "
            "metric groups."
        ),
    )


# ---------------------------------------------------------------------
# DERIVED COMPONENTS
# ---------------------------------------------------------------------

def _mapped_rows(
    actual_rows: list[dict[str, Any]],
    mapping: dict[str, str],
) -> list[dict[str, Any]]:

    return [
        {
            gold_column: (
                row.get(
                    actual_column
                )
            )
            for (
                gold_column,
                actual_column,
            ) in mapping.items()
        }
        for row in actual_rows
    ]


def _max_identity(
    rows: list[dict[str, Any]],
    identity_column: str,
    metric_column: str,
) -> set[Any]:

    usable = [
        row
        for row in rows
        if (
            row.get(identity_column)
            is not None
            and _is_number(
                row.get(metric_column)
            )
        )
    ]

    if not usable:
        return set()

    target = max(
        float(
            row[metric_column]
        )
        for row in usable
    )

    winners: set[Any] = set()

    for row in usable:
        if not _equal(
            target,
            row[metric_column],
            metric_column,
        ):
            continue

        identity_value = row[identity_column]
        canonical_identity = _canonical_temporal_value(
            identity_column,
            identity_value,
        )

        winners.add(
            canonical_identity
            if canonical_identity is not None
            else identity_value
        )

    return winners


def _with_derived_gap(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    derived = []

    for row in rows:

        copy = dict(row)

        if not _is_number(
            copy.get("gap")
        ):

            applications = _number(
                copy.get(
                    "application_count",
                    copy.get("applications"),
                )
            )

            sales = _number(
                copy.get(
                    "sales_count",
                    copy.get("sales"),
                )
            )

            if (
                applications is not None
                and sales is not None
            ):
                copy["gap"] = (
                    applications
                    - sales
                )

        derived.append(copy)

    return derived


def _with_derived_lead_to_sale(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    derived = []

    for row in rows:

        copy = dict(row)

        if not _is_number(
            copy.get(
                "lead_to_sale_pct"
            )
        ):

            leads = _number(
                copy.get(
                    "leads",
                    copy.get(
                        "lead_count"
                    ),
                )
            )

            sales = _number(
                copy.get(
                    "sales",
                    copy.get(
                        "sales_count"
                    ),
                )
            )

            if (
                leads is not None
                and leads != 0
                and sales is not None
            ):
                copy[
                    "lead_to_sale_pct"
                ] = (
                    100.0
                    * sales
                    / leads
                )

        derived.append(copy)

    return derived


def _derived_component_correct(
    component: str,
    expected_rows: list[dict[str, Any]],
    actual_rows: list[dict[str, Any]],
    mapping: dict[str, str],
) -> tuple[bool, str]:

    actual = _mapped_rows(
        actual_rows,
        mapping,
    )

    rules = {

        "highest_sales_month": (
            "month",
            "sales_count",
        ),

        "highest_revenue_quarter": (
            "quarter",
            "revenue_usd",
        ),

        "highest_percentage_month": (
            "month",
            "applications_per_lead_pct",
        ),

        "largest_gap_month": (
            "month",
            "gap",
        ),

        "highest_revenue_month": (
            "month",
            "revenue_usd",
        ),

        "highest_lead_to_sale_country": (
            "country",
            "lead_to_sale_pct",
        ),

        "highest_lead_to_sale_quarter": (
            "quarter",
            "lead_to_sale_pct",
        ),
    }

    # -------------------------------------------------------------
    # Same country leading both rankings
    # -------------------------------------------------------------

    if (
        component
        == "same_country_leads_both"
    ):

        expected_direct = {
            row.get(component)
            for row in expected_rows
            if (
                component in row
                and row.get(component)
                is not None
            )
        }

        if expected_direct:

            expected_value = next(
                iter(
                    expected_direct
                )
            )

        else:

            conversion_winners = {
                row.get("country")
                for row in expected_rows
                if (
                    row.get(
                        "conversion_rank"
                    )
                    == 1
                )
            }

            revenue_winners = {
                row.get("country")
                for row in expected_rows
                if (
                    row.get(
                        "revenue_rank"
                    )
                    == 1
                )
            }

            expected_value = bool(
                conversion_winners
                and (
                    conversion_winners
                    == revenue_winners
                )
            )

        actual_direct = {
            row.get(component)
            for row in actual
            if (
                component in row
                and row.get(component)
                is not None
            )
        }

        if actual_direct:

            observed_value = next(
                iter(
                    actual_direct
                )
            )

        else:

            conversion_winners = {
                row.get("country")
                for row in actual
                if (
                    row.get(
                        "conversion_rank"
                    )
                    == 1
                )
            }

            revenue_winners = {
                row.get("country")
                for row in actual
                if (
                    row.get(
                        "revenue_rank"
                    )
                    == 1
                )
            }

            observed_value = bool(
                conversion_winners
                and (
                    conversion_winners
                    == revenue_winners
                )
            )

        correct = _equal(
            expected_value,
            observed_value,
            component,
        )

        return (
            correct,
            (
                f"Gold {component}="
                f"{expected_value!r}; "
                f"actual="
                f"{observed_value!r}."
            ),
        )

    # -------------------------------------------------------------
    # Remaining deterministic derived rules
    # -------------------------------------------------------------

    if component not in rules:
        return (
            False,
            (
                "No deterministic rule "
                f"for {component!r}."
            ),
        )

    (
        identity_column,
        metric_column,
    ) = rules[component]

    expected_working = list(
        expected_rows
    )

    actual_working = list(
        actual
    )

    if component == "largest_gap_month":

        expected_working = (
            _with_derived_gap(
                expected_working
            )
        )

        actual_working = (
            _with_derived_gap(
                actual_working
            )
        )

    if component in {
        "highest_lead_to_sale_country",
        "highest_lead_to_sale_quarter",
    }:

        expected_working = (
            _with_derived_lead_to_sale(
                expected_working
            )
        )

        actual_working = (
            _with_derived_lead_to_sale(
                actual_working
            )
        )

    expected = _max_identity(
        expected_working,
        identity_column,
        metric_column,
    )

    observed = _max_identity(
        actual_working,
        identity_column,
        metric_column,
    )

    correct = (
        bool(expected)
        and expected == observed
    )

    return (
        correct,
        (
            f"Gold {component}="
            f"{sorted(map(str, expected))}; "
            f"actual="
            f"{sorted(map(str, observed))}."
        ),
    )


# ---------------------------------------------------------------------
# EXPLANATION SCORING
# ---------------------------------------------------------------------

def _extract_numeric_percentages(
    text: str,
) -> list[float]:

    values: list[float] = []

    for match in re.finditer(
        (
            r"(?<![\w.])"
            r"(-?\d[\d,]*(?:\.\d+)?)"
            r"\s*%"
        ),
        text,
    ):

        raw = (
            match.group(1)
            .replace(
                ",",
                "",
            )
        )

        try:
            values.append(
                float(raw)
            )

        except ValueError:
            pass

    return values


def _evidence_percentage_values(
    question: str,
    actual_rows: list[dict[str, Any]],
) -> list[float]:

    allowed = (
        _extract_numeric_percentages(
            question
        )
    )

    for row in actual_rows:

        for (
            column,
            value,
        ) in row.items():

            if (
                _is_number(value)
                and _is_percentage_component(
                    column
                )
            ):
                allowed.append(
                    float(value)
                )

    return allowed


def _explanation_correct(
    question: str,
    explanation: Any,
    actual_rows: list[dict[str, Any]],
) -> tuple[bool, str]:

    if (
        not isinstance(
            explanation,
            str,
        )
        or not explanation.strip()
    ):
        return (
            False,
            "Required explanation is missing.",
        )

    text = explanation.strip()

    # Aggregate benchmark results do not establish causality.
    for pattern in STRONG_CAUSAL_PATTERNS:

        if re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):
            return (
                False,
                (
                    "Explanation uses unsupported "
                    "causal wording matching "
                    f"{pattern!r}."
                ),
            )

    # Verify explicit percentage claims when present.
    claimed_percentages = (
        _extract_numeric_percentages(
            text
        )
    )

    allowed_percentages = (
        _evidence_percentage_values(
            question,
            actual_rows,
        )
    )

    unsupported = []

    for claimed in claimed_percentages:

        supported = any(
            math.isclose(
                claimed,
                allowed,
                rel_tol=0.0,
                abs_tol=0.01,
            )
            for allowed in allowed_percentages
        )

        if not supported:
            unsupported.append(
                claimed
            )

    if unsupported:
        return (
            False,
            (
                "Explanation contains "
                "percentage value(s) not "
                "grounded in returned evidence: "
                f"{unsupported!r}."
            ),
        )

    return (
        True,
        (
            "Explanation is present and "
            "passes deterministic grounding checks."
        ),
    )


# ---------------------------------------------------------------------
# VISUALIZATION SCORING
# ---------------------------------------------------------------------

# Explicit, pre-registered visualization requirements for the two
# visualization-required benchmark tasks.
#
# These are evaluator-side scoring specifications only. They contain no
# gold numeric answers and are used only to verify that the exact rows and
# series passed to the deterministic plotting tool match the frozen gold data.
VISUALIZATION_SPECS: dict[str, dict[str, Any]] = {
    "C6_DEV_02": {
        "x_component": "month",
        "series_components": (
            "application_count",
            "sales_count",
        ),
    },
    "C6_TEST_06": {
        "x_component": "month",
        "series_components": (
            "application_count",
            "sales_count",
            "revenue_usd",
        ),
    },
}


def _visualization_path(
    value: Any,
) -> str | None:
    """Extract an artifact path from supported visualization result shapes."""

    if (
        isinstance(value, str)
        and value.strip()
    ):
        return value.strip()

    if isinstance(value, dict):

        for key in (
            "path",
            "file_path",
            "visualization_path",
        ):
            candidate = value.get(key)

            if (
                isinstance(candidate, str)
                and candidate.strip()
            ):
                return candidate.strip()

    return None


def _find_visualization_tool_call(
    result: dict[str, Any],
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
]:
    """Return the most recent create_visualization call and its tool result."""

    trajectory = result.get(
        "trajectory",
        [],
    )

    if not isinstance(trajectory, list):
        return None, None

    selected_call: dict[str, Any] | None = None
    selected_result: dict[str, Any] | None = None

    for index, event in enumerate(trajectory):

        if not isinstance(event, dict):
            continue

        if (
            event.get("event") != "tool_call"
            or event.get("tool") != "create_visualization"
        ):
            continue

        selected_call = event
        selected_result = None

        for later_event in trajectory[index + 1 :]:

            if not isinstance(later_event, dict):
                continue

            if (
                later_event.get("event") == "tool_result"
                and later_event.get("tool") == "create_visualization"
            ):
                selected_result = later_event
                break

            if later_event.get("event") == "tool_call":
                break

    return selected_call, selected_result


def _canonical_visualization_column(
    actual_name: str,
    expected_components: Iterable[str],
) -> str | None:
    """Map one plotting key to one expected benchmark component."""

    actual_normalized = _norm(actual_name)

    for component in expected_components:
        if actual_normalized in {
            _norm(candidate)
            for candidate in _alias_candidates(component)
        }:
            return component

    return None


def _parse_visualization_rows(
    arguments: dict[str, Any],
) -> tuple[
    list[dict[str, Any]] | None,
    str | None,
]:
    """Parse the exact rows supplied to create_visualization."""

    data_json = arguments.get("data_json")

    if not isinstance(data_json, str):
        return (
            None,
            "Visualization tool call has no string data_json argument.",
        )

    try:
        rows = json.loads(data_json)
    except json.JSONDecodeError as exc:
        return (
            None,
            f"Visualization data_json could not be parsed: {exc}",
        )

    if (
        not isinstance(rows, list)
        or not rows
        or not all(isinstance(row, dict) for row in rows)
    ):
        return (
            None,
            "Visualization data_json must contain a non-empty array of row objects.",
        )

    return rows, None


def _visualization_data_matches_gold(
    task_id: str,
    chart_rows: list[dict[str, Any]],
    x_key: str,
    y_keys: list[str],
    expected_rows: list[dict[str, Any]],
) -> tuple[bool, str]:
    """Verify exact chart scope, series, and plotted values against gold."""

    spec = VISUALIZATION_SPECS.get(task_id)

    if spec is None:
        return (
            False,
            f"No frozen visualization specification exists for {task_id!r}.",
        )

    expected_x = str(spec["x_component"])
    expected_series = tuple(spec["series_components"])

    mapped_x = _canonical_visualization_column(
        x_key,
        (expected_x,),
    )

    if mapped_x != expected_x:
        return (
            False,
            (
                "Visualization x-axis does not match required component "
                f"{expected_x!r}: received {x_key!r}."
            ),
        )

    mapped_series: dict[str, str] = {}

    for actual_key in y_keys:
        component = _canonical_visualization_column(
            actual_key,
            expected_series,
        )

        if component is None:
            return (
                False,
                f"Visualization contains an unrecognized plotted series: {actual_key!r}.",
            )

        if component in mapped_series:
            return (
                False,
                (
                    "Visualization maps multiple series to benchmark component "
                    f"{component!r}."
                ),
            )

        mapped_series[component] = actual_key

    missing_series = [
        component
        for component in expected_series
        if component not in mapped_series
    ]

    if missing_series:
        return (
            False,
            f"Visualization is missing required series: {missing_series!r}.",
        )

    mapping = {expected_x: x_key}
    mapping.update(mapped_series)

    comparison_columns = [
        expected_x,
        *expected_series,
    ]

    aligned, ok, detail = _align_rows(
        expected_rows,
        chart_rows,
        comparison_columns,
        mapping,
    )

    if not ok:
        return (
            False,
            f"Visualization categories/scope do not match gold. {detail}",
        )

    for expected_row, chart_row in aligned:
        for component in expected_series:
            actual_column = mapping[component]
            expected_value = expected_row.get(component)
            actual_value = chart_row.get(actual_column)

            if not _equal(
                expected_value,
                actual_value,
                component,
            ):
                return (
                    False,
                    (
                        f"Visualization value mismatch for {component!r}: "
                        f"expected {expected_value!r}, actual {actual_value!r}."
                    ),
                )

    return (
        True,
        (
            "Visualization scope, categories, series, and plotted values "
            "match gold."
        ),
    )


def _visualization_correct(
    task: dict[str, Any],
    result: dict[str, Any],
    expected_rows: list[dict[str, Any]],
) -> tuple[bool, str]:
    """Score a required visualization deterministically from recorded tool inputs."""

    task_id = str(
        result.get("task_id")
        or task.get("task_id")
        or ""
    )

    if not task_id:
        return False, "Visualization task has no task_id."

    spec = VISUALIZATION_SPECS.get(task_id)

    if spec is None:
        return (
            False,
            f"No frozen visualization specification exists for {task_id!r}.",
        )

    tool_call, tool_result_event = _find_visualization_tool_call(result)

    if tool_call is None:
        return (
            False,
            "Required create_visualization tool call was not recorded.",
        )

    arguments = tool_call.get("arguments", {})

    if not isinstance(arguments, dict):
        return (
            False,
            "Visualization tool arguments are missing or invalid.",
        )

    tool_result: dict[str, Any] | None = None

    if isinstance(tool_result_event, dict):
        candidate = tool_result_event.get("result")
        if isinstance(candidate, dict):
            tool_result = candidate

    fallback_value = (
        result.get("visualization")
        or result.get("visualization_path")
    )

    path_text: str | None = None

    if tool_result is not None:
        if tool_result.get("status") != "success":
            return (
                False,
                "create_visualization did not return success.",
            )

        path_text = _visualization_path(tool_result)

    if not path_text:
        path_text = _visualization_path(fallback_value)

    if not path_text:
        return (
            False,
            "Required visualization artifact path is missing.",
        )

    path = Path(path_text)

    if not path.exists():
        return (
            False,
            f"Visualization path does not exist: {path_text}",
        )

    if path.suffix.lower() not in {
        ".png",
        ".jpg",
        ".jpeg",
        ".svg",
        ".pdf",
    }:
        return (
            False,
            f"Visualization has unsupported file type: {path.suffix}",
        )

    chart_type = str(arguments.get("chart_type", "")).strip().lower()

    if chart_type not in {"line", "bar"}:
        return (
            False,
            f"Visualization chart type is unsupported: {chart_type!r}.",
        )

    title = arguments.get("title")
    x_key = arguments.get("x_key")
    y_keys = arguments.get("y_keys")

    if not isinstance(title, str) or not title.strip():
        return False, "Visualization title is missing."

    if not isinstance(x_key, str) or not x_key.strip():
        return False, "Visualization x-axis key is missing."

    if (
        not isinstance(y_keys, list)
        or not y_keys
        or not all(
            isinstance(key, str) and key.strip()
            for key in y_keys
        )
    ):
        return (
            False,
            "Visualization series labels are missing or invalid.",
        )

    chart_rows, parse_error = _parse_visualization_rows(arguments)

    if chart_rows is None:
        return (
            False,
            parse_error or "Visualization rows are unavailable.",
        )

    if tool_result is not None:
        row_count = tool_result.get("row_count")

        if (
            _is_number(row_count)
            and int(float(row_count)) != len(chart_rows)
        ):
            return (
                False,
                (
                    "Visualization tool result row_count does not match "
                    "the supplied chart data."
                ),
            )

        returned_series = tool_result.get("series")

        if (
            isinstance(returned_series, list)
            and [_norm(value) for value in returned_series]
            != [_norm(value) for value in y_keys]
        ):
            return (
                False,
                (
                    "Visualization tool result series metadata does not match "
                    "the requested plotted series."
                ),
            )

    data_ok, data_detail = _visualization_data_matches_gold(
        task_id,
        chart_rows,
        x_key,
        y_keys,
        expected_rows,
    )

    if not data_ok:
        return False, data_detail

    expected_series = tuple(spec["series_components"])

    return (
        True,
        (
            "Visualization artifact exists; "
            f"x-axis={spec['x_component']!r}; "
            f"required series={list(expected_series)!r}; "
            "scope/categories and plotted values match gold; "
            "title and series labels are identifiable."
        ),
    )


# ---------------------------------------------------------------------
# SYSTEM RESULT EXTRACTION
# ---------------------------------------------------------------------

def _result_table(
    result: dict[str, Any],
) -> tuple[
    list[str],
    list[dict[str, Any]],
]:
    """
    Read evaluator-facing rows.

    System C also stores primary_result explicitly, so use it as a
    fallback if top-level columns/rows are unavailable.
    """

    columns = result.get(
        "columns"
    )

    rows = result.get(
        "rows"
    )

    if (
        isinstance(columns, list)
        and isinstance(rows, list)
    ):
        return (
            list(columns),
            list(rows),
        )

    primary = result.get(
        "primary_result"
    )

    if isinstance(
        primary,
        dict,
    ):

        primary_columns = (
            primary.get(
                "columns",
                [],
            )
        )

        primary_rows = (
            primary.get(
                "rows",
                [],
            )
        )

        if (
            isinstance(
                primary_columns,
                list,
            )
            and isinstance(
                primary_rows,
                list,
            )
        ):
            return (
                list(
                    primary_columns
                ),
                list(
                    primary_rows
                ),
            )

    return [], []


# ---------------------------------------------------------------------
# MAIN EVALUATOR
# ---------------------------------------------------------------------

class BenchmarkEvaluator:
    """Shared deterministic evaluator for Systems A, B, and C."""

    def __init__(
        self,
        tasks_path: (
            str
            | Path
            | list[dict[str, Any]]
            | dict[str, Any]
        ) = TASKS_PATH,
        gold_results_path: (
            str
            | Path
            | list[dict[str, Any]]
            | dict[str, Any]
        ) = GOLD_RESULTS_PATH,
        *,
        gold_path: (
            str
            | Path
            | None
        ) = None,
        tasks: Any = None,
        gold: Any = None,
    ) -> None:

        # ---------------------------------------------------------
        # Tasks
        # ---------------------------------------------------------

        if tasks is not None:

            raw_tasks = tasks

            self.tasks_path = (
                TASKS_PATH
            )

        elif isinstance(
            tasks_path,
            (
                dict,
                list,
            ),
        ):

            raw_tasks = tasks_path

            self.tasks_path = (
                TASKS_PATH
            )

        else:

            self.tasks_path = Path(
                tasks_path
            )

            raw_tasks = _load_json(
                self.tasks_path
            )

        self.tasks = _index_by_task_id(
            raw_tasks
        )

        # ---------------------------------------------------------
        # Gold results
        # ---------------------------------------------------------

        selected_gold = (
            gold_path
            if gold_path is not None
            else gold_results_path
        )

        if gold is not None:

            raw_gold = gold

            self.gold_results_path = (
                GOLD_RESULTS_PATH
            )

        elif isinstance(
            selected_gold,
            (
                dict,
                list,
            ),
        ):

            raw_gold = selected_gold

            self.gold_results_path = (
                GOLD_RESULTS_PATH
            )

        else:

            self.gold_results_path = Path(
                selected_gold
            )

            raw_gold = _load_json(
                self.gold_results_path
            )

        indexed_gold = (
            _index_by_task_id(
                raw_gold
            )
        )

        self.gold = {
            task_id: (
                _normalize_gold_record(
                    record
                )
            )
            for (
                task_id,
                record,
            ) in indexed_gold.items()
        }

    # -------------------------------------------------------------
    # CORE EVALUATION
    # -------------------------------------------------------------

    def evaluate(
        self,
        result: dict[str, Any],
    ) -> TaskEvaluation:

        task_id = str(
            result.get(
                "task_id"
            )
            or ""
        )

        if not task_id:
            raise ValueError(
                (
                    "Result record "
                    "is missing task_id."
                )
            )

        task = self.tasks.get(
            task_id
        )

        if task is None:
            raise KeyError(
                (
                    f"Task {task_id!r} "
                    "is not present in "
                    f"{self.tasks_path}."
                )
            )

        gold_record = (
            self.gold.get(
                task_id
            )
        )

        if gold_record is None:
            raise KeyError(
                (
                    "Gold result for "
                    f"{task_id!r} "
                    "is not present in "
                    f"{self.gold_results_path}."
                )
            )

        required = list(
            task.get(
                "required_components",
                [],
            )
        )

        execution_success = bool(
            result.get(
                "execution_success",
                False,
            )
        )

        # ---------------------------------------------------------
        # Execution failure
        # ---------------------------------------------------------

        if not execution_success:

            components = [
                ComponentScore(
                    component=component,
                    correct=False,
                    detail=(
                        "Execution failed; "
                        "no component credit."
                    ),
                )
                for component in required
            ]

            error_type = result.get(
                "error_type"
            )

            error_message = result.get(
                "error_message"
            )

            if (
                error_type
                or error_message
            ):
                note = (
                    f"{error_type}: "
                    f"{error_message}"
                )

            else:
                note = (
                    "Execution failed."
                )

            return TaskEvaluation(
                task_id=task_id,
                execution_success=False,
                factual_correctness=False,
                full_task_success=False,
                component_completion=0.0,
                correct_components=0,
                total_components=len(
                    required
                ),
                components=components,
                column_mapping={},
                notes=[note],
            )

        # ---------------------------------------------------------
        # Load expected / actual data
        # ---------------------------------------------------------

        expected_columns = list(
            gold_record.get(
                "columns",
                [],
            )
        )

        expected_rows = list(
            gold_record.get(
                "rows",
                [],
            )
        )

        (
            actual_columns,
            actual_rows,
        ) = _result_table(
            result
        )

        (
            mapping,
            notes,
        ) = _build_mapping(
            expected_columns,
            actual_columns,
        )

        component_scores: list[
            ComponentScore
        ] = []

        # ---------------------------------------------------------
        # Component-by-component evaluation
        # ---------------------------------------------------------

        for component in required:

            # -----------------------------------------------------
            # Explanation
            # -----------------------------------------------------

            if component == "explanation":

                value = (
                    result.get(
                        "explanation"
                    )
                    or result.get(
                        "final_response"
                    )
                )

                correct, detail = (
                    _explanation_correct(
                        str(
                            result.get(
                                "question"
                            )
                            or task.get(
                                "prompt"
                            )
                            or ""
                        ),
                        value,
                        actual_rows,
                    )
                )

            # -----------------------------------------------------
            # Visualization
            # -----------------------------------------------------

            elif component == "visualization":

                correct, detail = (
                    _visualization_correct(
                        task,
                        result,
                        expected_rows,
                    )
                )

            # -----------------------------------------------------
            # Ranking
            # -----------------------------------------------------

            elif (
                component
                in RANKING_COMPONENTS
            ):

                correct, detail = (
                    _ranking_correct(
                        task,
                        component,
                        expected_rows,
                        actual_rows,
                        expected_columns,
                        mapping,
                    )
                )

            # -----------------------------------------------------
            # Direct returned component
            # -----------------------------------------------------

            elif (
                component
                in expected_columns
                and component
                in mapping
            ):

                correct, detail = (
                    _direct_component_correct(
                        component,
                        expected_columns,
                        expected_rows,
                        actual_rows,
                        mapping,
                    )
                )

            # -----------------------------------------------------
            # Deterministically derived conclusion
            # -----------------------------------------------------

            elif (
                component
                in META_COMPONENTS
            ):

                correct, detail = (
                    _derived_component_correct(
                        component,
                        expected_rows,
                        actual_rows,
                        mapping,
                    )
                )

            # -----------------------------------------------------
            # Normal direct component
            # -----------------------------------------------------

            else:

                correct, detail = (
                    _direct_component_correct(
                        component,
                        expected_columns,
                        expected_rows,
                        actual_rows,
                        mapping,
                    )
                )

            component_scores.append(
                ComponentScore(
                    component=component,
                    correct=bool(
                        correct
                    ),
                    detail=detail,
                )
            )

        # ---------------------------------------------------------
        # Aggregate scores
        # ---------------------------------------------------------

        correct_count = sum(
            1
            for score
            in component_scores
            if score.correct
        )

        total = len(
            component_scores
        )

        completion = (
            correct_count / total
            if total
            else 0.0
        )

        # Factual correctness excludes only presentation components.
        factual_scores = [
            score
            for score
            in component_scores
            if (
                score.component
                not in PRESENTATION_COMPONENTS
            )
        ]

        factual_correctness = bool(
            factual_scores
            and all(
                score.correct
                for score
                in factual_scores
            )
        )

        full_task_success = bool(
            execution_success
            and total > 0
            and correct_count == total
        )

        return TaskEvaluation(
            task_id=task_id,
            execution_success=execution_success,
            factual_correctness=factual_correctness,
            full_task_success=full_task_success,
            component_completion=round(
                completion,
                4,
            ),
            correct_components=correct_count,
            total_components=total,
            components=component_scores,
            column_mapping=mapping,
            notes=notes,
        )

    # -------------------------------------------------------------
    # COMPATIBILITY WRAPPERS
    # -------------------------------------------------------------
    #
    # These allow existing evaluation scripts to keep working even
    # if they used an earlier method name.
    # -------------------------------------------------------------

    def evaluate_result(
        self,
        result: dict[str, Any],
    ) -> TaskEvaluation:

        return self.evaluate(
            result
        )

    def evaluate_record(
        self,
        result: dict[str, Any],
    ) -> TaskEvaluation:

        return self.evaluate(
            result
        )

    def score(
        self,
        result: dict[str, Any],
    ) -> TaskEvaluation:

        return self.evaluate(
            result
        )

    def evaluate_task(
        self,
        task_or_result: (
            str
            | dict[str, Any]
        ),
        result: (
            dict[str, Any]
            | None
        ) = None,
    ) -> TaskEvaluation:

        # evaluate_task(result)
        if isinstance(
            task_or_result,
            dict,
        ):
            return self.evaluate(
                task_or_result
            )

        # evaluate_task(task_id, result)
        if result is None:
            raise ValueError(
                (
                    "evaluate_task(task_id, result) "
                    "requires a result record."
                )
            )

        record = dict(
            result
        )

        record.setdefault(
            "task_id",
            task_or_result,
        )

        return self.evaluate(
            record
        )

    def evaluate_many(
        self,
        results: Iterable[
            dict[str, Any]
        ],
    ) -> list[TaskEvaluation]:

        return [
            self.evaluate(
                result
            )
            for result in results
        ]