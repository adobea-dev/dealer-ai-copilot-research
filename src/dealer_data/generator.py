from __future__ import annotations

import json
import math
import uuid

import numpy as np
import pandas as pd

from .config import SimulationConfig


# ---------------------------------------------------------------------
# GLOBAL CONSTANTS
# ---------------------------------------------------------------------

# UUID namespace used to create deterministic/reproducible UUID values.
#
# Using uuid5 rather than uuid4 means that if we rerun the generator
# using the same seed and inputs, the IDs remain reproducible.
NAMESPACE = uuid.UUID("2c4a3854-aead-4df1-881e-cfa6576a321b")


# Lead acquisition channels visible to the analytics system.
LEAD_SOURCES = [
    "organic_web",
    "paid_search",
    "social",
    "referral",
    "marketplace",
]


# Channels through which a lead may submit an application.
APPLICATION_CHANNELS = [
    "online",
    "dealer_branch",
    "bank_partner",
]


# Financing institutions are synthetic.
#
# We deliberately avoid using real bank names because this dataset
# represents a simulated business environment rather than empirical
# observations about specific institutions.
FINANCING_BANKS = [
    "Bank_A",
    "Bank_B",
    "Bank_C",
    "Bank_D",
]


# Maximum delays between funnel stages.
#
# These introduce temporal realism while ensuring that:
#
# lead_date <= application_date <= sale_date
#
MAX_APPLICATION_DELAY_DAYS = 10
MAX_SALE_DELAY_DAYS = 21


# ---------------------------------------------------------------------
# UTILITY FUNCTIONS
# ---------------------------------------------------------------------


def deterministic_uuid(value: str) -> str:
    """
    Generate a reproducible UUID from a stable input string.

    Example
    -------
    deterministic_uuid("dealer:GH:001")

    will always generate the same UUID.
    """
    return str(uuid.uuid5(NAMESPACE, value))


def sigmoid(x: float) -> float:
    """
    Convert a real-valued score into a probability between 0 and 1.

    This is useful for transforming latent dealer characteristics into
    realistic probabilities such as:

    - application conversion probability
    - approval probability
    - sale conversion probability
    """
    return 1.0 / (1.0 + math.exp(-x))


def seasonal_factor(month: int) -> float:
    """
    Return a mild seasonal demand multiplier for a calendar month.

    The purpose is to create realistic temporal variation without making
    seasonality dominate dealer-level performance.

    The factor varies approximately between:

        0.88 and 1.12

    This pattern is synthetic and should NOT be interpreted as evidence
    of real automotive seasonality in any included country.
    """
    angle = 2 * math.pi * (month - 1) / 12

    return 1.0 + 0.12 * math.sin(angle - 0.5)


def generate_month_periods(
    config: SimulationConfig,
) -> pd.DatetimeIndex:
    """
    Generate one timestamp for the beginning of each simulation month.

    Example
    -------
    For:

        start_date = 2024-01-01
        end_date   = 2025-12-31

    this returns 24 monthly periods.
    """
    return pd.date_range(
        start=config.start_date,
        end=config.end_date,
        freq="MS",
    )


# ---------------------------------------------------------------------
# DEALER GENERATION
# ---------------------------------------------------------------------


def generate_dealers(
    config: SimulationConfig,
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Generate dealer records and hidden dealer-level simulation parameters.

    Two datasets are returned.

    dealers
    -------
    Contains information that WILL eventually be available to the
    experimental systems.

    dealer_truth
    ------------
    Contains hidden parameters used to generate behaviour.

    dealer_truth must NOT be loaded into PostgreSQL or exposed to the
    Text-to-SQL or agentic systems.

    This separation helps prevent information leakage during evaluation.
    """

    dealer_rows: list[dict] = []
    truth_rows: list[dict] = []

    for country, n_dealers in config.dealers_per_country.items():

        for index in range(n_dealers):

            dealer_id = deterministic_uuid(
                f"dealer:{country}:{index:03d}"
            )

            city = str(
                rng.choice(
                    config.cities[country]
                )
            )

            # ---------------------------------------------------------
            # LATENT DEALER QUALITY
            # ---------------------------------------------------------
            #
            # This represents an unobserved dealer characteristic.
            #
            # Higher-quality dealers tend to:
            # - generate more leads
            # - convert more leads into applications
            # - receive more approvals
            # - convert more approvals into sales
            #
            # However, independent noise is added below so that quality
            # does NOT create a perfectly ordered ranking.
            quality = float(
                rng.normal(
                    loc=0.0,
                    scale=1.0,
                )
            )

            # Independent noise introduces overlap between dealers.
            #
            # This prevents the dataset from behaving like our previous
            # Bronze/Silver/Gold/Platinum tier system where dealer
            # performance was almost predetermined.
            lead_noise = float(
                rng.normal(0.0, 0.30)
            )

            app_noise = float(
                rng.normal(0.0, 0.35)
            )

            approval_noise = float(
                rng.normal(0.0, 0.30)
            )

            sales_noise = float(
                rng.normal(0.0, 0.35)
            )

            # Typical number of monthly leads.
            #
            # np.exp() ensures this remains positive.
            base_monthly_leads = float(
                np.exp(
                    math.log(25)
                    + 0.35 * quality
                    + lead_noise
                )
            )

            # Probability that a lead becomes an application.
            application_rate = sigmoid(
                -0.95
                + 0.30 * quality
                + app_noise
            )

            # Probability that an application is approved.
            approval_rate = sigmoid(
                0.60
                + 0.25 * quality
                + approval_noise
            )

            # Probability that an approved application results in a sale.
            sale_conversion_rate = sigmoid(
                0.15
                + 0.30 * quality
                + sales_noise
            )

            # Dealer-specific long-term monthly trend.
            #
            # Positive values represent gradual growth.
            # Negative values represent gradual decline.
            #
            # Most values are intentionally small.
            monthly_trend = float(
                rng.normal(
                    loc=0.0,
                    scale=0.006,
                )
            )

            # ---------------------------------------------------------
            # VISIBLE DEALER RECORD
            # ---------------------------------------------------------

            dealer_rows.append(
                {
                    "dealer_id": dealer_id,
                    "dealer_name": (
                        f"{country}-Dealer-{index + 1:03d}"
                    ),
                    "country": country,
                    "city": city,
                    "active": True,
                }
            )

            # ---------------------------------------------------------
            # HIDDEN RESEARCH TRUTH
            # ---------------------------------------------------------

            truth_rows.append(
                {
                    "dealer_id": dealer_id,
                    "latent_quality": quality,
                    "base_monthly_leads": base_monthly_leads,
                    "application_rate": application_rate,
                    "approval_rate": approval_rate,
                    "sale_conversion_rate": sale_conversion_rate,
                    "monthly_trend": monthly_trend,
                }
            )

    dealers = pd.DataFrame(dealer_rows)
    dealer_truth = pd.DataFrame(truth_rows)

    return dealers, dealer_truth


# ---------------------------------------------------------------------
# LEAD GENERATION
# ---------------------------------------------------------------------


def generate_leads(
    config: SimulationConfig,
    dealers: pd.DataFrame,
    dealer_truth: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    Generate synthetic lead events.

    Monthly lead volume is influenced by:

    1. dealer-specific baseline demand
    2. dealer-specific growth/decline trend
    3. mild yearly seasonality
    4. country-level simulation multiplier
    5. random Poisson variation

    This gives us temporal and dealer-level heterogeneity while retaining
    a known underlying data-generating process.
    """

    lead_rows: list[dict] = []

    periods = generate_month_periods(
        config
    )

    # Makes dealer parameter lookup efficient.
    truth_lookup = dealer_truth.set_index(
        "dealer_id"
    )

    lead_counter = 0

    for month_index, period_start in enumerate(periods):

        period_end = (
            period_start
            + pd.offsets.MonthEnd(1)
        )

        for dealer in dealers.itertuples(index=False):

            truth = truth_lookup.loc[
                dealer.dealer_id
            ]

            # Dealer-specific gradual change over time.
            trend_factor = max(
                0.65,
                1.0
                + float(
                    truth["monthly_trend"]
                )
                * month_index,
            )

            month_seasonality = seasonal_factor(
                period_start.month
            )

            country_factor = (
                config.country_demand_factor[
                    dealer.country
                ]
            )

            expected_leads = (
                float(
                    truth["base_monthly_leads"]
                )
                * trend_factor
                * month_seasonality
                * country_factor
            )

            # Poisson lambda must remain positive.
            expected_leads = max(
                expected_leads,
                1.0,
            )

            number_of_leads = int(
                rng.poisson(
                    expected_leads
                )
            )

            days_in_month = (
                period_end - period_start
            ).days + 1

            for _ in range(number_of_leads):

                lead_counter += 1

                lead_id = deterministic_uuid(
                    f"lead:{lead_counter}"
                )

                # Choose a random day within the month.
                day_offset = int(
                    rng.integers(
                        low=0,
                        high=days_in_month,
                    )
                )

                lead_date = (
                    period_start
                    + pd.Timedelta(
                        days=day_offset
                    )
                )

                lead_rows.append(
                    {
                        "lead_id": lead_id,
                        "dealer_id": dealer.dealer_id,
                        "country": dealer.country,
                        "lead_date": lead_date.date(),
                        "lead_source": str(
                            rng.choice(
                                LEAD_SOURCES
                            )
                        ),
                    }
                )

    return pd.DataFrame(
        lead_rows
    )


# ---------------------------------------------------------------------
# APPLICATION GENERATION
# ---------------------------------------------------------------------


def generate_applications(
    config: SimulationConfig,
    leads: pd.DataFrame,
    dealer_truth: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    Convert a subset of leads into loan/application events.

    Important improvement over the previous project:
    every application references an actual lead_id.

    Therefore we now have a real relationship:

        Lead -> Application

    The application conversion probability comes from the hidden dealer
    parameters rather than being independently generated.
    """

    application_rows: list[dict] = []

    truth_lookup = dealer_truth.set_index(
        "dealer_id"
    )

    dataset_end = pd.Timestamp(
        config.end_date
    )

    application_counter = 0

    for lead in leads.itertuples(index=False):

        truth = truth_lookup.loc[
            lead.dealer_id
        ]

        application_probability = float(
            truth["application_rate"]
        )

        # Determine whether this lead becomes an application.
        if rng.random() >= application_probability:
            continue

        lead_date = pd.Timestamp(
            lead.lead_date
        )

        # Applications may occur several days after initial lead capture.
        delay_days = int(
            rng.integers(
                0,
                MAX_APPLICATION_DELAY_DAYS + 1,
            )
        )

        application_date = (
            lead_date
            + pd.Timedelta(
                days=delay_days
            )
        )

        # Prevent events outside the defined research observation window.
        #
        # This creates a small amount of right-censoring near the final
        # dataset date. We will explicitly examine this during EDA.
        if application_date > dataset_end:
            continue

        application_counter += 1

        application_id = deterministic_uuid(
            f"application:{application_counter}"
        )

        # Determine whether the application is approved.
        approved = (
            rng.random()
            < float(
                truth["approval_rate"]
            )
        )

        application_rows.append(
            {
                "application_id": application_id,
                "lead_id": lead.lead_id,
                "dealer_id": lead.dealer_id,
                "country": lead.country,
                "application_date":
                    application_date.date(),
                "application_channel": str(
                    rng.choice(
                        APPLICATION_CHANNELS
                    )
                ),
                "status": (
                    "approved"
                    if approved
                    else "rejected"
                ),
            }
        )

    return pd.DataFrame(
        application_rows
    )


# ---------------------------------------------------------------------
# SALES GENERATION
# ---------------------------------------------------------------------


def generate_sales(
    config: SimulationConfig,
    applications: pd.DataFrame,
    dealer_truth: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    Generate vehicle sales from approved applications.

    Every generated sale references:

        application_id
        lead_id
        dealer_id

    giving us a complete traceable funnel:

        Lead
          -> Application
              -> Approved Application
                  -> Sale

    Only approved applications are eligible to produce sales.
    """

    sale_rows: list[dict] = []

    truth_lookup = dealer_truth.set_index(
        "dealer_id"
    )

    dataset_end = pd.Timestamp(
        config.end_date
    )

    sale_counter = 0

    approved_apps = applications[
        applications["status"]
        == "approved"
    ].copy()

    for application in approved_apps.itertuples(
        index=False
    ):

        truth = truth_lookup.loc[
            application.dealer_id
        ]

        sale_probability = float(
            truth[
                "sale_conversion_rate"
            ]
        )

        # Determine whether the approved application becomes a sale.
        if rng.random() >= sale_probability:
            continue

        application_date = pd.Timestamp(
            application.application_date
        )

        sale_delay_days = int(
            rng.integers(
                0,
                MAX_SALE_DELAY_DAYS + 1,
            )
        )

        sale_date = (
            application_date
            + pd.Timedelta(
                days=sale_delay_days
            )
        )

        # Prevent sales outside the research observation window.
        if sale_date > dataset_end:
            continue

        sale_counter += 1

        sale_id = deterministic_uuid(
            f"sale:{sale_counter}"
        )

        # Vehicle sale value follows a log-normal distribution.
        #
        # Log-normal values are useful here because prices are positive
        # and naturally right-skewed rather than normally distributed.
        sale_amount_usd = float(
            np.clip(
                rng.lognormal(
                    mean=math.log(14_000),
                    sigma=0.35,
                ),
                4_000,
                60_000,
            )
        )

        sale_rows.append(
            {
                "sale_id": sale_id,
                "application_id":
                    application.application_id,
                "lead_id":
                    application.lead_id,
                "dealer_id":
                    application.dealer_id,
                "country":
                    application.country,
                "sale_date":
                    sale_date.date(),
                "sale_amount_usd":
                    round(
                        sale_amount_usd,
                        2,
                    ),
                "financing_bank": str(
                    rng.choice(
                        FINANCING_BANKS
                    )
                ),
            }
        )

    return pd.DataFrame(
        sale_rows
    )


# ---------------------------------------------------------------------
# DATASET SAVING
# ---------------------------------------------------------------------


def save_dataset(
    config: SimulationConfig,
    dealers: pd.DataFrame,
    dealer_truth: pd.DataFrame,
    leads: pd.DataFrame,
    applications: pd.DataFrame,
    sales: pd.DataFrame,
) -> None:
    """
    Save visible research data, hidden simulation truth, and metadata.

    Visible datasets
    ----------------
    Saved in:

        data/generated/

    These datasets may eventually be loaded into PostgreSQL.

    Hidden truth
    ------------
    Saved in:

        data/research_truth/

    This information is for researchers only and must NOT be exposed to
    either experimental system.
    """

    # Create directories if they do not yet exist.
    config.output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    config.truth_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    config.metadata_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ---------------------------------------------------------
    # SAVE VISIBLE DATA
    # ---------------------------------------------------------

    visible_datasets = {
        "dealers": dealers,
        "leads": leads,
        "applications": applications,
        "sales": sales,
    }

    for dataset_name, dataframe in visible_datasets.items():

        output_path = (
            config.output_dir
            / f"{dataset_name}.csv"
        )

        dataframe.to_csv(
            output_path,
            index=False,
        )

    # ---------------------------------------------------------
    # SAVE HIDDEN SIMULATION TRUTH
    # ---------------------------------------------------------

    dealer_truth.to_csv(
        config.truth_dir
        / "dealer_latent_truth.csv",
        index=False,
    )

    # ---------------------------------------------------------
    # SAVE DATASET METADATA
    # ---------------------------------------------------------

    metadata = {
        "generator_version":
            config.generator_version,

        "random_seed":
            config.seed,

        "start_date":
            config.start_date,

        "end_date":
            config.end_date,

        "countries":
            list(
                config.dealers_per_country.keys()
            ),

        "dealer_count":
            int(
                len(dealers)
            ),

        "lead_count":
            int(
                len(leads)
            ),

        "application_count":
            int(
                len(applications)
            ),

        "approved_application_count":
            int(
                (
                    applications["status"]
                    == "approved"
                ).sum()
            ),

        "rejected_application_count":
            int(
                (
                    applications["status"]
                    == "rejected"
                ).sum()
            ),

        "sale_count":
            int(
                len(sales)
            ),

        # Explicit methodological note.
        "note": (
            "This dataset is synthetic. "
            "Country-level demand multipliers and behavioural "
            "relationships are simulation parameters and are not "
            "empirical claims about real automotive markets."
        ),
    }

    metadata_path = (
        config.metadata_dir
        / "dataset_v2_metadata.json"
    )

    with metadata_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            metadata,
            file,
            indent=4,
        )


# ---------------------------------------------------------------------
# MASTER GENERATION PIPELINE
# ---------------------------------------------------------------------


def generate_dataset(
    config: SimulationConfig,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Run the complete synthetic dataset generation pipeline.

    Pipeline
    --------

        Dealer population
                |
                v
             Leads
                |
                v
          Applications
                |
                v
         Approved Apps
                |
                v
             Sales

    The same random seed will reproduce the same dataset.
    """

    # One random number generator is passed through the complete
    # simulation. This keeps the full experiment reproducible.
    rng = np.random.default_rng(
        config.seed
    )

    # 1. Generate dealers and hidden dealer characteristics.
    dealers, dealer_truth = generate_dealers(
        config=config,
        rng=rng,
    )

    # 2. Generate customer leads.
    leads = generate_leads(
        config=config,
        dealers=dealers,
        dealer_truth=dealer_truth,
        rng=rng,
    )

    # 3. Convert a subset of leads into applications.
    applications = generate_applications(
        config=config,
        leads=leads,
        dealer_truth=dealer_truth,
        rng=rng,
    )

    # 4. Convert approved applications into sales.
    sales = generate_sales(
        config=config,
        applications=applications,
        dealer_truth=dealer_truth,
        rng=rng,
    )

    # 5. Save all visible and hidden datasets.
    save_dataset(
        config=config,
        dealers=dealers,
        dealer_truth=dealer_truth,
        leads=leads,
        applications=applications,
        sales=sales,
    )

    return (
        dealers,
        dealer_truth,
        leads,
        applications,
        sales,
    )


# ---------------------------------------------------------------------
# TEMPORARY DEVELOPMENT OUTPUT
# ---------------------------------------------------------------------


def print_dataset_summary(
    dealers: pd.DataFrame,
    dealer_truth: pd.DataFrame,
    leads: pd.DataFrame,
    applications: pd.DataFrame,
    sales: pd.DataFrame,
) -> None:
    """
    Print basic information while developing the generator.

    These checks are NOT our final research validation.
    A separate validation module will perform rigorous checks later.
    """

    print("\n" + "=" * 60)
    print("SYNTHETIC DEALER ANALYTICS DATASET")
    print("=" * 60)

    print("\nSample dealers:")
    print(
        dealers.head()
    )

    print("\nSample hidden dealer truth:")
    print(
        dealer_truth.head()
    )

    print("\nSample leads:")
    print(
        leads.head()
    )

    print("\nSample applications:")
    print(
        applications.head()
    )

    print("\nSample sales:")
    print(
        sales.head()
    )

    print("\n" + "-" * 60)
    print("DATASET COUNTS")
    print("-" * 60)

    print(
        f"Dealers:      {len(dealers):,}"
    )

    print(
        f"Leads:        {len(leads):,}"
    )

    print(
        f"Applications: {len(applications):,}"
    )

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

    print(
        f"Approved:     {approved_count:,}"
    )

    print(
        f"Rejected:     {rejected_count:,}"
    )

    print(
        f"Sales:        {len(sales):,}"
    )

    print("\n" + "-" * 60)
    print("DATE RANGE")
    print("-" * 60)

    print(
        "Lead dates:",
        leads["lead_date"].min(),
        "to",
        leads["lead_date"].max(),
    )

    print(
        "Application dates:",
        applications[
            "application_date"
        ].min(),
        "to",
        applications[
            "application_date"
        ].max(),
    )

    print(
        "Sale dates:",
        sales["sale_date"].min(),
        "to",
        sales["sale_date"].max(),
    )

    print("\n" + "-" * 60)
    print("LEADS BY COUNTRY")
    print("-" * 60)

    print(
        leads
        .groupby("country")
        .size()
        .sort_values(
            ascending=False
        )
    )

    print("\n" + "-" * 60)
    print("BASIC DUPLICATE CHECK")
    print("-" * 60)

    print(
        "Duplicate dealer IDs:",
        dealers[
            "dealer_id"
        ].duplicated().sum(),
    )

    print(
        "Duplicate lead IDs:",
        leads[
            "lead_id"
        ].duplicated().sum(),
    )

    print(
        "Duplicate application IDs:",
        applications[
            "application_id"
        ].duplicated().sum(),
    )

    print(
        "Duplicate sale IDs:",
        sales[
            "sale_id"
        ].duplicated().sum(),
    )

    print("\nGeneration completed.")


# ---------------------------------------------------------------------
# RUN THIS FILE DIRECTLY AS A MODULE
# ---------------------------------------------------------------------

if __name__ == "__main__":

    from .config import CONFIG

    (
        dealers,
        dealer_truth,
        leads,
        applications,
        sales,
    ) = generate_dataset(
        config=CONFIG
    )

    print_dataset_summary(
        dealers=dealers,
        dealer_truth=dealer_truth,
        leads=leads,
        applications=applications,
        sales=sales,
    )