# Dealer AI Copilot 2.0 — Research Benchmark v1.0

## Purpose

This benchmark is the fixed objective evaluation set for comparing System A (Text-to-SQL), System B (Text-to-SQL + natural-language explanation), and System C (tool-grounded agentic analytics). The benchmark is defined before system implementation and final evaluation.

## Composition

48 total tasks: 12 development tasks and 36 held-out test tasks. Each complexity level C1–C6 contains 8 tasks: 2 development and 6 held-out test tasks.

## Complexity

C1: simple retrieval.
C2: filtered aggregation.
C3: ranking/comparison.
C4: derived analytics.
C5: temporal and multi-metric analytics.
C6: compositional business analytics.

## Data boundary

Evaluated systems may access only `dealers`, `leads`, `applications`, and `sales`. Research-truth files and hidden simulation parameters are prohibited.

## Time semantics

`event_period` means the event itself is filtered to the stated period. `cohort` means entities are selected by the stated starting event/time window and may be followed into the maturation buffer where explicitly required. `all_time` means no time restriction is required.

## Scoring principle

Systems are scored only on components explicitly required by the task. Exact SQL string matching is not required; correctness is based on semantic result equivalence and completion of required analytical components. Visualization is required only when `visualization_required` is true. Explanation is required only when `explanation_required` is true.

## Freeze policy

After `benchmark-v1.0` is frozen, held-out test tasks must not be used to tune prompts, tools, routing, model settings, or system behavior.
