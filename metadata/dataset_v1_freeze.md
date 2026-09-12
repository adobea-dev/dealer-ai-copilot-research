# Synthetic Dealer Analytics Dataset v1.0

## Status

Frozen for experimental development.

## Generator

Generator version: 2.1.0  
Random seed: 42

## Analysis Window

2024-01-01 to 2025-12-31

## Maturation Buffer

Downstream applications and sales may occur through 2026-01-31 for
leads created before the end of the analysis window.

No new leads are generated during the maturation buffer.

## Countries

- GH
- NG
- KE
- UG

Country-level parameters and observed differences are synthetic
simulation characteristics and must not be interpreted as empirical
claims about real automotive markets.

## Dataset Size

- Dealers: 125
- Leads: 82,716
- Applications: 24,512
- Approved applications: 15,839
- Sales: 8,801

## Overall Funnel

- Lead to application: 29.63%
- Application approval: 64.62%
- Approved application to sale: 55.57%
- Lead to sale: 10.64%

## Validation

45 of 45 structural validation checks passed.

The dataset was also audited for:

- dealer-level heterogeneity
- funnel behaviour
- temporal variation
- hidden-to-observed parameter recovery
- right-censoring
- country-level latent-variable imbalance
- transaction-value variation

## Experimental Restriction

Files under `data/research_truth/` are researcher-only.

They must never be:

- loaded into the experimental PostgreSQL database
- exposed to the Text-to-SQL system
- exposed to the natural-language explanation baseline
- exposed to the agentic analytics system

## Freeze Policy

Do not change simulation parameters after this point unless a serious
data defect is discovered.

Any future change requires a new dataset version.