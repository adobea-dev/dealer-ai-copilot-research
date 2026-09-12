from __future__ import annotations

import pandas as pd

from src.dealer_data.config import CONFIG
from src.dealer_data.eda import run_eda


def main() -> None:
    """
    Load the generated synthetic dataset and run the research EDA.

    This script performs two jobs:

    1. Runs the normal exploratory data analysis defined in eda.py.
    2. Produces a researcher-only audit of hidden dealer characteristics
       by country.

    IMPORTANT:
    Hidden truth is used only to verify the synthetic data-generating
    process. It must never be exposed to the experimental AI systems.
    """

    # -----------------------------------------------------------------
    # LOAD VISIBLE RESEARCH DATA
    # -----------------------------------------------------------------
    #
    # These are the tables that will eventually be available to the
    # Text-to-SQL and agentic analytics systems.

    dealers = pd.read_csv(
        CONFIG.output_dir
        / "dealers.csv"
    )

    leads = pd.read_csv(
        CONFIG.output_dir
        / "leads.csv"
    )

    applications = pd.read_csv(
        CONFIG.output_dir
        / "applications.csv"
    )

    sales = pd.read_csv(
        CONFIG.output_dir
        / "sales.csv"
    )

    # -----------------------------------------------------------------
    # LOAD HIDDEN RESEARCH TRUTH
    # -----------------------------------------------------------------
    #
    # These variables describe the synthetic mechanisms used to generate
    # dealer behaviour.
    #
    # They are available only to us as researchers.
    #
    # They must NOT be loaded into PostgreSQL later and must NOT be
    # available to any evaluated AI system.

    dealer_truth = pd.read_csv(
        CONFIG.truth_dir
        / "dealer_latent_truth.csv"
    )

    # -----------------------------------------------------------------
    # DEFINE EDA OUTPUT DIRECTORY
    # -----------------------------------------------------------------

    output_dir = (
        CONFIG.output_dir
        .parent
        .parent
        / "reports"
        / "eda"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # -----------------------------------------------------------------
    # RUN MAIN EDA
    # -----------------------------------------------------------------
    #
    # This produces:
    #
    # - overall funnel metrics
    # - country-level summaries
    # - dealer-level distributions
    # - monthly trends
    # - right-censoring analysis
    # - hidden/observed correlation analysis
    # - plots
    #
    # The implementation lives in src/dealer_data/eda.py.

    run_eda(
        dealers=dealers,
        dealer_truth=dealer_truth,
        leads=leads,
        applications=applications,
        sales=sales,
        output_dir=output_dir,
    )

    # -----------------------------------------------------------------
    # HIDDEN DEALER CHARACTERISTICS BY COUNTRY
    # -----------------------------------------------------------------
    #
    # We noticed that countries can have noticeably different average
    # lead volumes even though our explicit country demand multipliers
    # differ only mildly.
    #
    # This audit tells us whether those differences are simply caused by
    # the random dealer population generated under seed 42.
    #
    # For example, one country's dealers may happen to have a somewhat
    # higher average base_monthly_leads value.
    #
    # That is not automatically a problem. We simply want to understand
    # where the simulated differences come from before freezing the data.

    truth_with_country = (
        dealers[
            [
                "dealer_id",
                "country",
            ]
        ]
        .merge(
            dealer_truth,
            on="dealer_id",
            how="inner",
            validate="one_to_one",
        )
    )

    truth_by_country = (
        truth_with_country
        .groupby(
            "country"
        )
        .agg(
            # Number of dealers included in each country.
            dealers=(
                "dealer_id",
                "count",
            ),

            # Average hidden overall dealer quality.
            mean_latent_quality=(
                "latent_quality",
                "mean",
            ),

            # Typical underlying monthly lead-generation capacity.
            mean_base_monthly_leads=(
                "base_monthly_leads",
                "mean",
            ),

            # Hidden lead -> application conversion probability.
            mean_application_rate=(
                "application_rate",
                "mean",
            ),

            # Hidden application -> approval probability.
            mean_approval_rate=(
                "approval_rate",
                "mean",
            ),

            # Hidden approved application -> sale probability.
            mean_sale_conversion_rate=(
                "sale_conversion_rate",
                "mean",
            ),

            # Average long-term dealer growth/decline parameter.
            mean_monthly_trend=(
                "monthly_trend",
                "mean",
            ),

            # Typical transaction value generated for each dealer.
            mean_average_sale_value=(
                "average_sale_value",
                "mean",
            ),
        )
        .reset_index()
        .sort_values(
            "country"
        )
    )

    # Save the researcher-only diagnostic table.
    truth_by_country.to_csv(
        output_dir
        / "hidden_truth_by_country.csv",
        index=False,
    )

    # -----------------------------------------------------------------
    # PRINT HIDDEN COUNTRY AUDIT
    # -----------------------------------------------------------------

    print(
        "\n"
        + "=" * 70
    )

    print(
        "HIDDEN DEALER CHARACTERISTICS BY COUNTRY"
    )

    print(
        "=" * 70
    )

    print(
        truth_by_country
        .round(4)
        .to_string(
            index=False
        )
    )

    print(
        "\nResearcher-only diagnostic saved to:"
    )

    print(
        output_dir
        / "hidden_truth_by_country.csv"
    )

    # -----------------------------------------------------------------
    # SIMPLE DATASET SIZE SUMMARY
    # -----------------------------------------------------------------

    print(
        "\n"
        + "=" * 70
    )

    print(
        "VISIBLE DATASET SIZE"
    )

    print(
        "=" * 70
    )

    print(
        f"Dealers:      {len(dealers):,}"
    )

    print(
        f"Leads:        {len(leads):,}"
    )

    print(
        f"Applications: {len(applications):,}"
    )

    print(
        f"Sales:        {len(sales):,}"
    )

    print(
        "\nEDA and simulation audit completed."
    )


if __name__ == "__main__":
    main()