from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------


def safe_divide(
    numerator: pd.Series | float | int,
    denominator: pd.Series | float | int,
):
    """
    Divide safely while avoiding division-by-zero errors.

    Zero denominators are converted to NaN because a conversion rate
    is undefined when there were no eligible observations.
    """
    return numerator / np.where(
        np.asarray(denominator) == 0,
        np.nan,
        denominator,
    )


def ensure_output_directory(
    output_dir: Path,
) -> None:
    """Create the EDA output directory if it does not exist."""
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )


# ---------------------------------------------------------------------
# DATA PREPARATION
# ---------------------------------------------------------------------


def prepare_dates(
    leads: pd.DataFrame,
    applications: pd.DataFrame,
    sales: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Convert event dates to pandas datetime values.

    We work on copies so the original dataframes are not modified.
    """

    leads = leads.copy()
    applications = applications.copy()
    sales = sales.copy()

    leads["lead_date"] = pd.to_datetime(
        leads["lead_date"]
    )

    applications["application_date"] = pd.to_datetime(
        applications["application_date"]
    )

    sales["sale_date"] = pd.to_datetime(
        sales["sale_date"]
    )

    return (
        leads,
        applications,
        sales,
    )


# ---------------------------------------------------------------------
# DATASET OVERVIEW
# ---------------------------------------------------------------------


def build_dataset_overview(
    dealers: pd.DataFrame,
    leads: pd.DataFrame,
    applications: pd.DataFrame,
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """
    Produce a high-level description of each visible dataset.
    """

    rows = []

    datasets = {
        "dealers": dealers,
        "leads": leads,
        "applications": applications,
        "sales": sales,
    }

    for name, dataframe in datasets.items():

        rows.append(
            {
                "dataset": name,
                "rows": len(dataframe),
                "columns": len(dataframe.columns),
                "missing_values": int(
                    dataframe.isna().sum().sum()
                ),
                "duplicate_rows": int(
                    dataframe.duplicated().sum()
                ),
            }
        )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------
# FUNNEL ANALYSIS
# ---------------------------------------------------------------------


def build_overall_funnel(
    leads: pd.DataFrame,
    applications: pd.DataFrame,
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """
    Calculate overall lead -> application -> approval -> sale metrics.
    """

    lead_count = len(leads)
    application_count = len(applications)

    approved_count = int(
        (
            applications["status"]
            == "approved"
        ).sum()
    )

    rejected_count = int(
        (
            applications["status"]
            == "rejected"
        ).sum()
    )

    sales_count = len(sales)

    total_revenue = float(
        sales["sale_amount_usd"].sum()
    )

    return pd.DataFrame(
        [
            {
                "leads": lead_count,
                "applications": application_count,
                "approved_applications": approved_count,
                "rejected_applications": rejected_count,
                "sales": sales_count,
                "lead_to_application_rate":
                    application_count / lead_count,
                "application_approval_rate":
                    approved_count / application_count,
                "approved_to_sale_rate":
                    sales_count / approved_count,
                "lead_to_sale_rate":
                    sales_count / lead_count,
                "total_revenue_usd":
                    total_revenue,
                "average_sale_value_usd":
                    sales["sale_amount_usd"].mean(),
            }
        ]
    )


# ---------------------------------------------------------------------
# COUNTRY-LEVEL ANALYSIS
# ---------------------------------------------------------------------


def build_country_summary(
    dealers: pd.DataFrame,
    leads: pd.DataFrame,
    applications: pd.DataFrame,
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """
    Summarise dealer activity and conversion rates by country.

    Important:
    Any differences found here are properties of the simulation.
    They must not be interpreted as empirical differences between
    real countries.
    """

    dealer_counts = (
        dealers.groupby("country")
        .size()
        .rename("dealers")
    )

    lead_counts = (
        leads.groupby("country")
        .size()
        .rename("leads")
    )

    application_counts = (
        applications.groupby("country")
        .size()
        .rename("applications")
    )

    approved_counts = (
        applications[
            applications["status"] == "approved"
        ]
        .groupby("country")
        .size()
        .rename("approved_applications")
    )

    sale_counts = (
        sales.groupby("country")
        .size()
        .rename("sales")
    )

    revenue = (
        sales.groupby("country")[
            "sale_amount_usd"
        ]
        .sum()
        .rename("revenue_usd")
    )

    result = pd.concat(
        [
            dealer_counts,
            lead_counts,
            application_counts,
            approved_counts,
            sale_counts,
            revenue,
        ],
        axis=1,
    ).fillna(0)

    result["lead_to_application_rate"] = (
        result["applications"]
        / result["leads"]
    )

    result["application_approval_rate"] = (
        result["approved_applications"]
        / result["applications"]
    )

    result["approved_to_sale_rate"] = (
        result["sales"]
        / result["approved_applications"]
    )

    result["lead_to_sale_rate"] = (
        result["sales"]
        / result["leads"]
    )

    result["leads_per_dealer"] = (
        result["leads"]
        / result["dealers"]
    )

    return (
        result
        .reset_index()
        .sort_values("country")
    )


# ---------------------------------------------------------------------
# DEALER-LEVEL ANALYSIS
# ---------------------------------------------------------------------


def build_dealer_summary(
    dealers: pd.DataFrame,
    leads: pd.DataFrame,
    applications: pd.DataFrame,
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """
    Create observed performance metrics for every dealer.

    These are calculated from visible events rather than from hidden
    simulation parameters.
    """

    result = dealers[
        [
            "dealer_id",
            "dealer_name",
            "country",
            "city",
        ]
    ].copy()

    lead_counts = (
        leads.groupby("dealer_id")
        .size()
        .rename("leads")
    )

    application_counts = (
        applications.groupby("dealer_id")
        .size()
        .rename("applications")
    )

    approved_counts = (
        applications[
            applications["status"] == "approved"
        ]
        .groupby("dealer_id")
        .size()
        .rename("approved_applications")
    )

    sales_summary = (
        sales.groupby("dealer_id")
        .agg(
            sales=("sale_id", "count"),
            revenue_usd=(
                "sale_amount_usd",
                "sum",
            ),
            average_sale_value_usd=(
                "sale_amount_usd",
                "mean",
            ),
        )
    )

    result = (
        result
        .merge(
            lead_counts,
            on="dealer_id",
            how="left",
        )
        .merge(
            application_counts,
            on="dealer_id",
            how="left",
        )
        .merge(
            approved_counts,
            on="dealer_id",
            how="left",
        )
        .merge(
            sales_summary,
            on="dealer_id",
            how="left",
        )
    )

    count_columns = [
        "leads",
        "applications",
        "approved_applications",
        "sales",
    ]

    result[count_columns] = (
        result[count_columns]
        .fillna(0)
        .astype(int)
    )

    result["revenue_usd"] = (
        result["revenue_usd"]
        .fillna(0.0)
    )

    result["application_rate_observed"] = (
        result["applications"]
        / result["leads"].replace(0, np.nan)
    )

    result["approval_rate_observed"] = (
        result["approved_applications"]
        / result["applications"].replace(
            0,
            np.nan,
        )
    )

    result["sale_conversion_rate_observed"] = (
        result["sales"]
        / result[
            "approved_applications"
        ].replace(
            0,
            np.nan,
        )
    )

    result["lead_to_sale_rate"] = (
        result["sales"]
        / result["leads"].replace(
            0,
            np.nan,
        )
    )

    return result


# ---------------------------------------------------------------------
# MONTHLY / TEMPORAL ANALYSIS
# ---------------------------------------------------------------------


def build_monthly_summary(
    leads: pd.DataFrame,
    applications: pd.DataFrame,
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """
    Aggregate funnel activity by calendar month.

    This helps us inspect:
    - seasonality
    - trend
    - month-to-month variation
    - end-of-window effects
    """

    leads = leads.copy()
    applications = applications.copy()
    sales = sales.copy()

    leads["month"] = (
        leads["lead_date"]
        .dt.to_period("M")
        .dt.to_timestamp()
    )

    applications["month"] = (
        applications["application_date"]
        .dt.to_period("M")
        .dt.to_timestamp()
    )

    sales["month"] = (
        sales["sale_date"]
        .dt.to_period("M")
        .dt.to_timestamp()
    )

    monthly_leads = (
        leads.groupby("month")
        .size()
        .rename("leads")
    )

    monthly_apps = (
        applications.groupby("month")
        .size()
        .rename("applications")
    )

    monthly_approved = (
        applications[
            applications["status"]
            == "approved"
        ]
        .groupby("month")
        .size()
        .rename("approved_applications")
    )

    monthly_sales = (
        sales.groupby("month")
        .size()
        .rename("sales")
    )

    monthly_revenue = (
        sales.groupby("month")[
            "sale_amount_usd"
        ]
        .sum()
        .rename("revenue_usd")
    )

    result = pd.concat(
        [
            monthly_leads,
            monthly_apps,
            monthly_approved,
            monthly_sales,
            monthly_revenue,
        ],
        axis=1,
    ).fillna(0)

    result["lead_to_application_rate"] = (
        result["applications"]
        / result["leads"].replace(
            0,
            np.nan,
        )
    )

    result["application_approval_rate"] = (
        result["approved_applications"]
        / result["applications"].replace(
            0,
            np.nan,
        )
    )

    result["approved_to_sale_rate"] = (
        result["sales"]
        / result[
            "approved_applications"
        ].replace(
            0,
            np.nan,
        )
    )

    return result.reset_index()


# ---------------------------------------------------------------------
# HIDDEN-TRUTH AUDIT
# ---------------------------------------------------------------------


def build_truth_comparison(
    dealer_summary: pd.DataFrame,
    dealer_truth: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Compare hidden simulation parameters against observed dealer outcomes.

    This is strictly for research validation.

    The future AI systems must NOT receive these hidden variables.
    """

    comparison = dealer_summary.merge(
        dealer_truth,
        on="dealer_id",
        how="inner",
    )

    columns = [
        "latent_quality",
        "base_monthly_leads",
        "application_rate",
        "approval_rate",
        "sale_conversion_rate",
        "monthly_trend",
        "leads",
        "applications",
        "approved_applications",
        "sales",
        "application_rate_observed",
        "approval_rate_observed",
        "sale_conversion_rate_observed",
        "lead_to_sale_rate",
        "revenue_usd",
    ]

    correlation_matrix = (
        comparison[columns]
        .corr(
            method="pearson"
        )
    )

    return (
        comparison,
        correlation_matrix,
    )


# ---------------------------------------------------------------------
# DISTRIBUTION SUMMARY
# ---------------------------------------------------------------------


def build_dealer_distribution_summary(
    dealer_summary: pd.DataFrame,
) -> pd.DataFrame:
    """
    Summarise dealer-level distributions.

    This helps determine whether dealers show enough overlap and
    heterogeneity for a meaningful research benchmark.
    """

    columns = [
        "leads",
        "applications",
        "approved_applications",
        "sales",
        "revenue_usd",
        "application_rate_observed",
        "approval_rate_observed",
        "sale_conversion_rate_observed",
        "lead_to_sale_rate",
    ]

    return (
        dealer_summary[columns]
        .describe(
            percentiles=[
                0.05,
                0.10,
                0.25,
                0.50,
                0.75,
                0.90,
                0.95,
            ]
        )
        .transpose()
    )


# ---------------------------------------------------------------------
# RIGHT-CENSORING AUDIT
# ---------------------------------------------------------------------


def build_right_censoring_summary(
    leads: pd.DataFrame,
    applications: pd.DataFrame,
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """
    Inspect whether events close to the end of the simulation have lower
    apparent conversion because there is less time for downstream events.

    This matters because the generator prevents applications and sales
    from occurring after the configured end date.
    """

    end_date = leads["lead_date"].max()

    cutoff = (
        end_date
        - pd.Timedelta(days=31)
    )

    early_leads = leads[
        leads["lead_date"]
        <= cutoff
    ]

    final_month_leads = leads[
        leads["lead_date"]
        > cutoff
    ]

    early_apps = applications[
        applications["lead_id"].isin(
            early_leads["lead_id"]
        )
    ]

    final_apps = applications[
        applications["lead_id"].isin(
            final_month_leads["lead_id"]
        )
    ]

    early_sales = sales[
        sales["lead_id"].isin(
            early_leads["lead_id"]
        )
    ]

    final_sales = sales[
        sales["lead_id"].isin(
            final_month_leads["lead_id"]
        )
    ]

    return pd.DataFrame(
        [
            {
                "period": "earlier_period",
                "leads": len(early_leads),
                "applications":
                    len(early_apps),
                "sales":
                    len(early_sales),
                "lead_to_application_rate":
                    len(early_apps)
                    / len(early_leads),
                "lead_to_sale_rate":
                    len(early_sales)
                    / len(early_leads),
            },
            {
                "period": "final_31_days",
                "leads":
                    len(final_month_leads),
                "applications":
                    len(final_apps),
                "sales":
                    len(final_sales),
                "lead_to_application_rate":
                    len(final_apps)
                    / len(final_month_leads),
                "lead_to_sale_rate":
                    len(final_sales)
                    / len(final_month_leads),
            },
        ]
    )


# ---------------------------------------------------------------------
# PLOTS
# ---------------------------------------------------------------------


def plot_monthly_activity(
    monthly_summary: pd.DataFrame,
    output_dir: Path,
) -> None:
    """
    Plot monthly counts for the main funnel stages.
    """

    fig, ax = plt.subplots(
        figsize=(11, 6)
    )

    ax.plot(
        monthly_summary["month"],
        monthly_summary["leads"],
        label="Leads",
    )

    ax.plot(
        monthly_summary["month"],
        monthly_summary["applications"],
        label="Applications",
    )

    ax.plot(
        monthly_summary["month"],
        monthly_summary[
            "approved_applications"
        ],
        label="Approved applications",
    )

    ax.plot(
        monthly_summary["month"],
        monthly_summary["sales"],
        label="Sales",
    )

    ax.set_title(
        "Monthly Synthetic Dealer Funnel Activity"
    )

    ax.set_xlabel("Month")
    ax.set_ylabel("Event count")

    ax.legend()

    fig.autofmt_xdate()
    fig.tight_layout()

    fig.savefig(
        output_dir
        / "monthly_funnel_activity.png",
        dpi=200,
    )

    plt.close(fig)


def plot_dealer_sales_distribution(
    dealer_summary: pd.DataFrame,
    output_dir: Path,
) -> None:
    """
    Inspect how widely dealer sales performance is distributed.
    """

    fig, ax = plt.subplots(
        figsize=(9, 6)
    )

    ax.hist(
        dealer_summary["sales"],
        bins=20,
    )

    ax.set_title(
        "Distribution of Total Sales Across Dealers"
    )

    ax.set_xlabel(
        "Total sales per dealer"
    )

    ax.set_ylabel(
        "Number of dealers"
    )

    fig.tight_layout()

    fig.savefig(
        output_dir
        / "dealer_sales_distribution.png",
        dpi=200,
    )

    plt.close(fig)


def plot_application_conversion_distribution(
    dealer_summary: pd.DataFrame,
    output_dir: Path,
) -> None:
    """
    Inspect variation in lead-to-application performance between dealers.
    """

    values = dealer_summary[
        "application_rate_observed"
    ].dropna()

    fig, ax = plt.subplots(
        figsize=(9, 6)
    )

    ax.hist(
        values,
        bins=20,
    )

    ax.set_title(
        "Observed Lead-to-Application Rate Across Dealers"
    )

    ax.set_xlabel(
        "Lead-to-application rate"
    )

    ax.set_ylabel(
        "Number of dealers"
    )

    fig.tight_layout()

    fig.savefig(
        output_dir
        / "dealer_application_rate_distribution.png",
        dpi=200,
    )

    plt.close(fig)


def plot_hidden_vs_observed_application_rate(
    truth_comparison: pd.DataFrame,
    output_dir: Path,
) -> None:
    """
    Compare each dealer's hidden application probability with its
    observed application conversion rate.

    This plot is for researchers only.
    """

    fig, ax = plt.subplots(
        figsize=(8, 6)
    )

    ax.scatter(
        truth_comparison[
            "application_rate"
        ],
        truth_comparison[
            "application_rate_observed"
        ],
        alpha=0.7,
    )

    ax.set_title(
        "Hidden vs Observed Application Conversion"
    )

    ax.set_xlabel(
        "Hidden application probability"
    )

    ax.set_ylabel(
        "Observed application rate"
    )

    fig.tight_layout()

    fig.savefig(
        output_dir
        / "hidden_vs_observed_application_rate.png",
        dpi=200,
    )

    plt.close(fig)


# ---------------------------------------------------------------------
# MASTER EDA PIPELINE
# ---------------------------------------------------------------------


def run_eda(
    dealers: pd.DataFrame,
    dealer_truth: pd.DataFrame,
    leads: pd.DataFrame,
    applications: pd.DataFrame,
    sales: pd.DataFrame,
    output_dir: Path,
) -> None:
    """
    Run the complete initial EDA and simulation audit.
    """

    ensure_output_directory(
        output_dir
    )

    (
        leads,
        applications,
        sales,
    ) = prepare_dates(
        leads,
        applications,
        sales,
    )

    # ---------------------------------------------------------------
    # TABLES
    # ---------------------------------------------------------------

    overview = build_dataset_overview(
        dealers,
        leads,
        applications,
        sales,
    )

    overall_funnel = build_overall_funnel(
        leads,
        applications,
        sales,
    )

    country_summary = build_country_summary(
        dealers,
        leads,
        applications,
        sales,
    )

    dealer_summary = build_dealer_summary(
        dealers,
        leads,
        applications,
        sales,
    )

    monthly_summary = build_monthly_summary(
        leads,
        applications,
        sales,
    )

    dealer_distribution = (
        build_dealer_distribution_summary(
            dealer_summary
        )
    )

    (
        truth_comparison,
        correlation_matrix,
    ) = build_truth_comparison(
        dealer_summary,
        dealer_truth,
    )

    censoring_summary = (
        build_right_censoring_summary(
            leads,
            applications,
            sales,
        )
    )

    # ---------------------------------------------------------------
    # SAVE TABLES
    # ---------------------------------------------------------------

    overview.to_csv(
        output_dir
        / "dataset_overview.csv",
        index=False,
    )

    overall_funnel.to_csv(
        output_dir
        / "overall_funnel.csv",
        index=False,
    )

    country_summary.to_csv(
        output_dir
        / "country_summary.csv",
        index=False,
    )

    dealer_summary.to_csv(
        output_dir
        / "dealer_summary.csv",
        index=False,
    )

    monthly_summary.to_csv(
        output_dir
        / "monthly_summary.csv",
        index=False,
    )

    dealer_distribution.to_csv(
        output_dir
        / "dealer_distribution_summary.csv"
    )

    correlation_matrix.to_csv(
        output_dir
        / "hidden_truth_correlation_matrix.csv"
    )

    censoring_summary.to_csv(
        output_dir
        / "right_censoring_summary.csv",
        index=False,
    )

    # ---------------------------------------------------------------
    # PLOTS
    # ---------------------------------------------------------------

    plot_monthly_activity(
        monthly_summary,
        output_dir,
    )

    plot_dealer_sales_distribution(
        dealer_summary,
        output_dir,
    )

    plot_application_conversion_distribution(
        dealer_summary,
        output_dir,
    )

    plot_hidden_vs_observed_application_rate(
        truth_comparison,
        output_dir,
    )

    # ---------------------------------------------------------------
    # TERMINAL SUMMARY
    # ---------------------------------------------------------------

    print("\n" + "=" * 70)
    print("RESEARCH EDA COMPLETE")
    print("=" * 70)

    print("\nOVERALL FUNNEL")
    print(
        overall_funnel
        .round(4)
        .to_string(index=False)
    )

    print("\nCOUNTRY SUMMARY")
    print(
        country_summary
        .round(4)
        .to_string(index=False)
    )

    print("\nRIGHT-CENSORING CHECK")
    print(
        censoring_summary
        .round(4)
        .to_string(index=False)
    )

    print(
        f"\nEDA outputs saved to: "
        f"{output_dir}"
    )