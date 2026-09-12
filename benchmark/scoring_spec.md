# Dealer AI Copilot 2.0 — Benchmark Scoring Specification

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
