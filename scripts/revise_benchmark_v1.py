from __future__ import annotations

import json
from pathlib import Path


TASKS_PATH = Path("benchmark/tasks_v1.json")
GOLD_QUERIES_PATH = Path("benchmark/gold/gold_queries_v1.json")
SCORING_SPEC_PATH = Path("benchmark/scoring_spec.md")
README_PATH = Path("benchmark/README.md")


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path: Path, data) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )


def main() -> None:
    """
    Apply the final methodological revision to benchmark v1.

    Changes
    -------
    1. Converts selected C6 funnel tasks from event-period ratios to
       true linked-cohort analysis.
    2. Makes the maturation-buffer semantics explicit in the prompts.
    3. Writes a deterministic scoring specification.
    4. Keeps development/test membership and the 48-task structure
       unchanged.
    """

    if not TASKS_PATH.exists():
        raise FileNotFoundError(
            f"Could not find {TASKS_PATH}. Run this script from the project root."
        )

    if not GOLD_QUERIES_PATH.exists():
        raise FileNotFoundError(
            f"Could not find {GOLD_QUERIES_PATH}. Run this script from the project root."
        )

    tasks = load_json(TASKS_PATH)
    gold = load_json(GOLD_QUERIES_PATH)

    tasks_by_id = {
        task["task_id"]: task
        for task in tasks
    }

    # -----------------------------------------------------------------
    # REVISE C6 TASK WORDING AND TIME SEMANTICS
    # -----------------------------------------------------------------

    tasks_by_id["C6_DEV_01"]["prompt"] = (
        "Among dealers with at least 200 leads generated during 2025, "
        "identify the five dealers with the highest lead volume whose eventual "
        "lead-to-sale percentage was below the overall median dealer "
        "lead-to-sale percentage for 2025 lead cohorts. Follow each 2025 lead "
        "to any resulting application and sale, including the January 2026 "
        "maturation buffer when necessary. Return dealer name, country, leads, "
        "applications, approved applications, sales, lead-to-sale percentage, "
        "and the median reference percentage. Briefly explain why these "
        "dealers represent high-volume but relatively weak downstream conversion."
    )
    tasks_by_id["C6_DEV_01"]["time_semantics"] = "cohort"

    tasks_by_id["C6_TEST_01"]["prompt"] = (
        "Among Ghanaian dealers with at least 150 leads generated during 2025, "
        "identify the five dealers with the highest eventual lead-to-sale "
        "percentage. Follow each 2025 lead through any resulting application, "
        "approval, and sale, including the January 2026 maturation buffer when "
        "necessary. For each dealer, report leads, applications, approved "
        "applications, sales, lead-to-application percentage, application-approval "
        "percentage, approved-to-sale percentage, and identify the weakest funnel "
        "stage. Briefly explain the result."
    )
    tasks_by_id["C6_TEST_01"]["time_semantics"] = "cohort"

    tasks_by_id["C6_TEST_02"]["prompt"] = (
        "Compare the four countries using 2025 lead cohorts. For leads generated "
        "during 2025, report the number of leads, eventual applications, eventual "
        "approved applications, eventual sales, revenue from those resulting sales, "
        "and eventual lead-to-sale percentage. Follow the 2025 leads into the "
        "January 2026 maturation buffer when necessary. Rank countries by "
        "lead-to-sale percentage and by revenue, then state whether the same "
        "country leads both rankings."
    )
    tasks_by_id["C6_TEST_02"]["time_semantics"] = "cohort"

    tasks_by_id["C6_TEST_03"]["prompt"] = (
        "For each quarterly lead cohort of 2025 in Nigeria, report leads, eventual "
        "applications, eventual approved applications, eventual sales, "
        "lead-to-application percentage, application-approval percentage, and "
        "approved-to-sale percentage. Follow each lead through downstream events, "
        "including the January 2026 maturation buffer when necessary. Identify the "
        "weakest funnel stage in each quarter and the quarter with the highest "
        "eventual lead-to-sale percentage. Summarize the pattern."
    )
    tasks_by_id["C6_TEST_03"]["time_semantics"] = "cohort"

    tasks_by_id["C6_TEST_05"]["prompt"] = (
        "Among dealers with at least 150 leads generated in both 2024 and 2025, "
        "identify the five dealers whose eventual lead-to-sale percentage improved "
        "the most from the 2024 lead cohort to the 2025 lead cohort. For each year, "
        "follow the leads to any resulting sales; for the 2025 cohort, include the "
        "January 2026 maturation buffer when necessary. Report dealer name, country, "
        "leads and resulting sales for each year, both yearly lead-to-sale "
        "percentages, and the percentage-point improvement. Briefly explain what "
        "the ranking means."
    )
    tasks_by_id["C6_TEST_05"]["time_semantics"] = "cohort"

    # -----------------------------------------------------------------
    # REPLACE GOLD SQL FOR COHORT-BASED C6 TASKS
    # -----------------------------------------------------------------

    gold["C6_DEV_01"] = {
        "expected_columns": [
            "dealer_name",
            "country",
            "leads",
            "applications",
            "approved_applications",
            "sales",
            "lead_to_sale_pct",
            "median_lead_to_sale_pct",
        ],
        "sql": """
WITH cohort AS (
    SELECT
        lead_id,
        dealer_id
    FROM leads
    WHERE lead_date >= DATE '2025-01-01'
      AND lead_date < DATE '2026-01-01'
),
metrics AS (
    SELECT
        d.dealer_id,
        d.dealer_name,
        d.country,
        COUNT(c.lead_id) AS leads,
        COUNT(a.application_id) AS applications,
        COUNT(a.application_id) FILTER (
            WHERE a.status = 'approved'
        ) AS approved_applications,
        COUNT(s.sale_id) AS sales,
        ROUND(
            100.0 * COUNT(s.sale_id)::numeric
            / NULLIF(COUNT(c.lead_id), 0),
            2
        ) AS lead_to_sale_pct
    FROM dealers d
    LEFT JOIN cohort c
        ON c.dealer_id = d.dealer_id
    LEFT JOIN applications a
        ON a.lead_id = c.lead_id
    LEFT JOIN sales s
        ON s.lead_id = c.lead_id
    GROUP BY
        d.dealer_id,
        d.dealer_name,
        d.country
),
median_value AS (
    SELECT
        PERCENTILE_CONT(0.5)
        WITHIN GROUP (
            ORDER BY lead_to_sale_pct
        ) AS median_lead_to_sale_pct
    FROM metrics
    WHERE leads > 0
)
SELECT
    m.dealer_name,
    m.country,
    m.leads,
    m.applications,
    m.approved_applications,
    m.sales,
    m.lead_to_sale_pct,
    ROUND(
        v.median_lead_to_sale_pct::numeric,
        2
    ) AS median_lead_to_sale_pct
FROM metrics m
CROSS JOIN median_value v
WHERE m.leads >= 200
  AND m.lead_to_sale_pct < v.median_lead_to_sale_pct
ORDER BY
    m.leads DESC,
    m.dealer_name ASC
LIMIT 5;
""".strip(),
    }

    gold["C6_TEST_01"] = {
        "expected_columns": [
            "dealer_name",
            "leads",
            "applications",
            "approved_applications",
            "sales",
            "lead_to_application_pct",
            "application_approval_pct",
            "approved_to_sale_pct",
            "weakest_stage",
        ],
        "sql": """
WITH cohort AS (
    SELECT
        l.lead_id,
        l.dealer_id
    FROM leads l
    JOIN dealers d
        ON d.dealer_id = l.dealer_id
    WHERE d.country = 'GH'
      AND l.lead_date >= DATE '2025-01-01'
      AND l.lead_date < DATE '2026-01-01'
),
metrics AS (
    SELECT
        d.dealer_id,
        d.dealer_name,
        COUNT(c.lead_id) AS leads,
        COUNT(a.application_id) AS applications,
        COUNT(a.application_id) FILTER (
            WHERE a.status = 'approved'
        ) AS approved_applications,
        COUNT(s.sale_id) AS sales,
        ROUND(
            100.0 * COUNT(a.application_id)::numeric
            / NULLIF(COUNT(c.lead_id), 0),
            2
        ) AS lead_to_application_pct,
        ROUND(
            100.0 * COUNT(a.application_id) FILTER (
                WHERE a.status = 'approved'
            )::numeric
            / NULLIF(COUNT(a.application_id), 0),
            2
        ) AS application_approval_pct,
        ROUND(
            100.0 * COUNT(s.sale_id)::numeric
            / NULLIF(
                COUNT(a.application_id) FILTER (
                    WHERE a.status = 'approved'
                ),
                0
            ),
            2
        ) AS approved_to_sale_pct,
        ROUND(
            100.0 * COUNT(s.sale_id)::numeric
            / NULLIF(COUNT(c.lead_id), 0),
            2
        ) AS lead_to_sale_pct
    FROM dealers d
    LEFT JOIN cohort c
        ON c.dealer_id = d.dealer_id
    LEFT JOIN applications a
        ON a.lead_id = c.lead_id
    LEFT JOIN sales s
        ON s.lead_id = c.lead_id
    WHERE d.country = 'GH'
    GROUP BY
        d.dealer_id,
        d.dealer_name
)
SELECT
    dealer_name,
    leads,
    applications,
    approved_applications,
    sales,
    lead_to_application_pct,
    application_approval_pct,
    approved_to_sale_pct,
    CASE
        WHEN lead_to_application_pct <= application_approval_pct
         AND lead_to_application_pct <= approved_to_sale_pct
            THEN 'lead_to_application'
        WHEN application_approval_pct <= approved_to_sale_pct
            THEN 'application_to_approval'
        ELSE 'approval_to_sale'
    END AS weakest_stage
FROM metrics
WHERE leads >= 150
ORDER BY
    lead_to_sale_pct DESC,
    dealer_name ASC
LIMIT 5;
""".strip(),
    }

    gold["C6_TEST_02"] = {
        "expected_columns": [
            "country",
            "leads",
            "applications",
            "approved_applications",
            "sales",
            "revenue_usd",
            "lead_to_sale_pct",
            "conversion_rank",
            "revenue_rank",
        ],
        "sql": """
WITH cohort AS (
    SELECT
        lead_id,
        dealer_id,
        country
    FROM leads
    WHERE lead_date >= DATE '2025-01-01'
      AND lead_date < DATE '2026-01-01'
),
metrics AS (
    SELECT
        c.country,
        COUNT(c.lead_id) AS leads,
        COUNT(a.application_id) AS applications,
        COUNT(a.application_id) FILTER (
            WHERE a.status = 'approved'
        ) AS approved_applications,
        COUNT(s.sale_id) AS sales,
        ROUND(
            COALESCE(SUM(s.sale_amount_usd), 0),
            2
        ) AS revenue_usd,
        ROUND(
            100.0 * COUNT(s.sale_id)::numeric
            / NULLIF(COUNT(c.lead_id), 0),
            2
        ) AS lead_to_sale_pct
    FROM cohort c
    LEFT JOIN applications a
        ON a.lead_id = c.lead_id
    LEFT JOIN sales s
        ON s.lead_id = c.lead_id
    GROUP BY c.country
)
SELECT
    country,
    leads,
    applications,
    approved_applications,
    sales,
    revenue_usd,
    lead_to_sale_pct,
    DENSE_RANK() OVER (
        ORDER BY lead_to_sale_pct DESC
    ) AS conversion_rank,
    DENSE_RANK() OVER (
        ORDER BY revenue_usd DESC
    ) AS revenue_rank
FROM metrics
ORDER BY country;
""".strip(),
    }

    gold["C6_TEST_03"] = {
        "expected_columns": [
            "quarter",
            "leads",
            "applications",
            "approved_applications",
            "sales",
            "lead_to_application_pct",
            "application_approval_pct",
            "approved_to_sale_pct",
            "lead_to_sale_pct",
            "weakest_stage",
            "lead_to_sale_rank",
        ],
        "sql": """
WITH quarters AS (
    SELECT generate_series(1, 4) AS quarter
),
cohort AS (
    SELECT
        lead_id,
        EXTRACT(
            QUARTER FROM lead_date
        )::integer AS quarter
    FROM leads
    WHERE country = 'NG'
      AND lead_date >= DATE '2025-01-01'
      AND lead_date < DATE '2026-01-01'
),
metrics AS (
    SELECT
        q.quarter,
        COUNT(c.lead_id) AS leads,
        COUNT(a.application_id) AS applications,
        COUNT(a.application_id) FILTER (
            WHERE a.status = 'approved'
        ) AS approved_applications,
        COUNT(s.sale_id) AS sales,
        ROUND(
            100.0 * COUNT(a.application_id)::numeric
            / NULLIF(COUNT(c.lead_id), 0),
            2
        ) AS lead_to_application_pct,
        ROUND(
            100.0 * COUNT(a.application_id) FILTER (
                WHERE a.status = 'approved'
            )::numeric
            / NULLIF(COUNT(a.application_id), 0),
            2
        ) AS application_approval_pct,
        ROUND(
            100.0 * COUNT(s.sale_id)::numeric
            / NULLIF(
                COUNT(a.application_id) FILTER (
                    WHERE a.status = 'approved'
                ),
                0
            ),
            2
        ) AS approved_to_sale_pct,
        ROUND(
            100.0 * COUNT(s.sale_id)::numeric
            / NULLIF(COUNT(c.lead_id), 0),
            2
        ) AS lead_to_sale_pct
    FROM quarters q
    LEFT JOIN cohort c
        ON c.quarter = q.quarter
    LEFT JOIN applications a
        ON a.lead_id = c.lead_id
    LEFT JOIN sales s
        ON s.lead_id = c.lead_id
    GROUP BY q.quarter
),
diagnosed AS (
    SELECT
        quarter,
        leads,
        applications,
        approved_applications,
        sales,
        lead_to_application_pct,
        application_approval_pct,
        approved_to_sale_pct,
        lead_to_sale_pct,
        CASE
            WHEN lead_to_application_pct <= application_approval_pct
             AND lead_to_application_pct <= approved_to_sale_pct
                THEN 'lead_to_application'
            WHEN application_approval_pct <= approved_to_sale_pct
                THEN 'application_to_approval'
            ELSE 'approval_to_sale'
        END AS weakest_stage
    FROM metrics
)
SELECT
    quarter,
    leads,
    applications,
    approved_applications,
    sales,
    lead_to_application_pct,
    application_approval_pct,
    approved_to_sale_pct,
    lead_to_sale_pct,
    weakest_stage,
    DENSE_RANK() OVER (
        ORDER BY lead_to_sale_pct DESC
    ) AS lead_to_sale_rank
FROM diagnosed
ORDER BY quarter;
""".strip(),
    }

    gold["C6_TEST_05"] = {
        "expected_columns": [
            "dealer_name",
            "country",
            "leads_2024",
            "sales_2024",
            "lead_to_sale_pct_2024",
            "leads_2025",
            "sales_2025",
            "lead_to_sale_pct_2025",
            "improvement_percentage_points",
        ],
        "sql": """
WITH yearly AS (
    SELECT
        d.dealer_id,
        d.dealer_name,
        d.country,
        EXTRACT(
            YEAR FROM l.lead_date
        )::integer AS cohort_year,
        COUNT(l.lead_id) AS leads,
        COUNT(s.sale_id) AS sales,
        ROUND(
            100.0 * COUNT(s.sale_id)::numeric
            / NULLIF(COUNT(l.lead_id), 0),
            2
        ) AS lead_to_sale_pct
    FROM dealers d
    JOIN leads l
        ON l.dealer_id = d.dealer_id
    LEFT JOIN sales s
        ON s.lead_id = l.lead_id
    WHERE l.lead_date >= DATE '2024-01-01'
      AND l.lead_date < DATE '2026-01-01'
    GROUP BY
        d.dealer_id,
        d.dealer_name,
        d.country,
        EXTRACT(YEAR FROM l.lead_date)
),
y2024 AS (
    SELECT *
    FROM yearly
    WHERE cohort_year = 2024
),
y2025 AS (
    SELECT *
    FROM yearly
    WHERE cohort_year = 2025
)
SELECT
    y2025.dealer_name,
    y2025.country,
    y2024.leads AS leads_2024,
    y2024.sales AS sales_2024,
    y2024.lead_to_sale_pct AS lead_to_sale_pct_2024,
    y2025.leads AS leads_2025,
    y2025.sales AS sales_2025,
    y2025.lead_to_sale_pct AS lead_to_sale_pct_2025,
    ROUND(
        y2025.lead_to_sale_pct
        - y2024.lead_to_sale_pct,
        2
    ) AS improvement_percentage_points
FROM y2024
JOIN y2025
    ON y2025.dealer_id = y2024.dealer_id
WHERE y2024.leads >= 150
  AND y2025.leads >= 150
ORDER BY
    improvement_percentage_points DESC,
    y2025.dealer_name ASC
LIMIT 5;
""".strip(),
    }

    # -----------------------------------------------------------------
    # SAVE REVISED TASKS / GOLD QUERIES
    # -----------------------------------------------------------------

    save_json(
        TASKS_PATH,
        tasks,
    )

    save_json(
        GOLD_QUERIES_PATH,
        gold,
    )

    # Gold results must be regenerated after changing gold queries.
    Path("benchmark/gold/gold_results_v1.json").write_text(
        "{}\n",
        encoding="utf-8",
    )

    # -----------------------------------------------------------------
    # CREATE SCORING SPECIFICATION
    # -----------------------------------------------------------------

    scoring_spec = """# Dealer AI Copilot 2.0 — Benchmark Scoring Specification

## Purpose

This document defines how benchmark responses are scored before the
experimental systems are evaluated.

The same scoring rules apply to Systems A, B, and C.

## 1. Primary scores

### Full Task Success

A task receives Full Task Success = 1 only when every mandatory component
listed in `required_components` is correct.

Otherwise:

Full Task Success = 0.

### Component Completion

Component Completion is:

correct required components / total required components

This provides partial credit without redefining the task after evaluation.

## 2. Deterministic factual scoring

### Integer counts

Counts must match the gold result exactly.

### Currency

Currency values are compared after normalization to USD and must be within
USD 0.01 of the gold value unless the prompt explicitly requests a coarser
rounding.

### Percentages

Gold percentage fields ending in `_pct` are expressed in percentage points.

Example:

10.64 means 10.64%, not 0.1064.

A submitted percentage is accepted when it is semantically equivalent and
within 0.01 percentage points of the gold value.

### Other decimal values

Unless a task specifies another precision, decimal values are accepted within
an absolute tolerance of 0.0001 after normalization.

## 3. Tables

A required table is correct when:

- all required columns are present semantically;
- required rows match the gold result;
- factual values satisfy the numeric rules above;
- no required row is omitted.

Column labels do not need to match the internal gold column names exactly when
their meaning is unambiguous.

## 4. Rankings

Ranked tasks are evaluated primarily on the requested ranking metric.

The system must return the correct entities and ranking values.

When two or more entities tie on the primary ranking metric, any ordering
within the tied group is accepted unless the user prompt explicitly defines a
tie-break rule.

Secondary `ORDER BY` clauses in gold SQL exist for deterministic storage and
do not automatically become user-facing scoring requirements.

## 5. Derived conclusions

Conclusions such as:

- highest-sales month;
- highest-revenue quarter;
- largest-gap month;
- highest-conversion country;
- weakest funnel stage

are derived deterministically from the gold result.

A conclusion component is correct only when it agrees with that deterministic
gold derivation.

Rank helper fields such as `sales_rank = 1`, `gap_rank = 1`, or
`lead_to_sale_rank = 1` are internal evidence used to derive the requested
conclusion.

## 6. Explanations

When `explanation_required` is false, explanation quality does not affect the
task score.

When `explanation_required` is true, the explanation component is correct when
all of the following hold:

1. it states the requested analytical conclusion;
2. the conclusion is supported by the factual result;
3. it does not introduce contradictory numerical claims;
4. it does not claim causal explanations that are unsupported by the data.

Stylistic quality alone is not part of objective correctness.

Human-study measures of clarity, usefulness, and comprehension are evaluated
separately from this benchmark.

## 7. Visualizations

When `visualization_required` is false, no visualization is required and its
absence cannot reduce the score.

When `visualization_required` is true, the visualization component is correct
when:

1. a visualization is actually produced;
2. it contains the requested metric(s);
3. the categories or time axis match the requested scope;
4. plotted values are consistent with the gold data;
5. labels or legends make the represented series identifiable.

A visualization is not scored for aesthetics in the objective benchmark.

## 8. Time semantics

### event_period

The relevant event itself is filtered to the requested time period.

Example:

"sales during 2025" filters `sale_date` to 2025.

### cohort

The starting population is selected from the requested time period and linked
downstream records are followed using relational identifiers.

Example:

"leads generated in December 2025 that eventually became sales" selects
December 2025 leads and may follow them into the January 2026 maturation
buffer.

Cohort tasks must not substitute same-period event counts for linked cohort
outcomes.

### all_time

No additional time restriction is required.

## 9. Visualization and explanation neutrality

Systems are scored only for capabilities explicitly requested by each task.

A system is never penalized for:

- failing to produce a chart when no chart was requested;
- failing to provide an explanation when no explanation was requested.

## 10. SQL equivalence

Exact SQL string matching is not a correctness criterion.

Different SQL queries are acceptable when they return semantically equivalent
results and respect the task's time semantics and data boundary.

## 11. Data boundary

Evaluated systems may access only the visible experimental database tables:

- dealers
- leads
- applications
- sales

They must not access:

- `data/research_truth/`;
- hidden simulation parameters;
- gold SQL;
- gold benchmark results.

## 12. Primary benchmark reporting

The primary benchmark report will include:

- Full Task Success;
- Component Completion;
- factual/numeric correctness;
- instruction adherence;
- first-attempt success;
- latency;
- model calls;
- database/tool calls;
- token usage;
- estimated cost.

Architecture-specific diagnostic metrics are reported separately and do not
replace the shared outcome metrics.
"""

    SCORING_SPEC_PATH.write_text(
        scoring_spec,
        encoding="utf-8",
    )

    # -----------------------------------------------------------------
    # UPDATE BENCHMARK README
    # -----------------------------------------------------------------

    readme = """# Benchmark files

`tasks_v1.json` contains the business questions, task metadata, and required
answer components used by the experimental systems.

`gold/gold_queries_v1.json` contains researcher-only deterministic SQL used
to generate ground-truth results.

`gold/gold_results_v1.json` is generated by:

    python -m scripts.generate_gold_results

`scoring_spec.md` defines the scoring rules applied consistently to Systems
A, B, and C.

Before generating gold results, run:

    python -m scripts.validate_benchmark

The gold-query and gold-result files must never be exposed to an evaluated
system.
"""

    README_PATH.write_text(
        readme,
        encoding="utf-8",
    )

    print("=" * 70)
    print("BENCHMARK V1 METHODOLOGICAL REVISION")
    print("=" * 70)
    print("[PASS] Revised C6_DEV_01 to linked-cohort semantics.")
    print("[PASS] Revised C6_TEST_01 to linked-cohort semantics.")
    print("[PASS] Revised C6_TEST_02 to linked-cohort semantics.")
    print("[PASS] Revised C6_TEST_03 to linked-cohort semantics.")
    print("[PASS] Revised C6_TEST_05 to linked-cohort semantics.")
    print("[PASS] Created benchmark/scoring_spec.md.")
    print("[PASS] Cleared old gold results; regenerate them next.")
    print()
    print("Next:")
    print("  python -m scripts.validate_benchmark")
    print("  python -m scripts.generate_gold_results")


if __name__ == "__main__":
    main()
