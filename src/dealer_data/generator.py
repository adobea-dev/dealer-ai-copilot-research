from __future__ import annotations

import json
import math
import uuid

import numpy as np
import pandas as pd

from .config import SimulationConfig


# =====================================================================
# GLOBAL CONSTANTS
# =====================================================================

# Namespace used by UUID5 to create deterministic identifiers.
#
# UUID5 is preferable here to random UUID4 because the same input string
# always produces the same ID. This improves experiment reproducibility.
NAMESPACE = uuid.UUID(
    "2c4a3854-aead-4df1-881e-cfa6576a321b"
)


# Synthetic lead acquisition channels.
LEAD_SOURCES = [
    "organic_web",
    "paid_search",
    "social",
    "referral",
    "marketplace",
]


# Synthetic channels through which applications may be submitted.
APPLICATION_CHANNELS = [
    "online",
    "dealer_branch",
    "bank_partner",
]


# Synthetic financing institutions.
#
# We intentionally avoid real bank names because the generated data is
# not intended to make claims about actual institutions.
FINANCING_BANKS = [
    "Bank_A",
    "Bank_B",
    "Bank_C",
    "Bank_D",
]


# Maximum number of days between a lead and an application.
MAX_APPLICATION_DELAY_DAYS = 10

# Maximum number of days between an approved application and a sale.
MAX_SALE_DELAY_DAYS = 21


# =====================================================================
# UTILITY FUNCTIONS
# =====================================================================


def deterministic_uuid(
    value: str,
) -> str:
    """
    Generate a reproducible UUID from a stable text value.

    Example
    -------
    deterministic_uuid("dealer:GH:001")

    will always produce the same UUID.
    """

    return str(
        uuid.uuid5(
            NAMESPACE,
            value,
        )
    )


def sigmoid(
    x: float,
) -> float:
    """
    Convert an unrestricted numerical value into a probability.

    The resulting value is always between 0 and 1.

    This is used when converting hidden dealer characteristics into
    probabilities such as application conversion or sale conversion.
    """

    return 1.0 / (
        1.0
        + math.exp(-x)
    )


def seasonal_factor(
    month: int,
) -> float:
    """
    Create mild yearly seasonality in lead demand.

    The factor varies approximately between 0.88 and 1.12.

    IMPORTANT:
    This is a synthetic temporal pattern and is NOT intended to represent
    observed automotive seasonality in Ghana, Nigeria, Kenya, or Uganda.
    """

    angle = (
        2
        * math.pi
        * (month - 1)
        / 12
    )

    return (
        1.0
        + 0.12
        * math.sin(
            angle - 0.5
        )
    )


def generate_month_periods(
    config: SimulationConfig,
) -> pd.DatetimeIndex:
    """
    Generate months during which new leads may be created.

    New leads exist only inside the primary analysis window:

        2024-01 through 2025-12

    The additional simulation period in January 2026 is NOT used to
    generate new leads. It exists only to allow existing leads to mature.
    """

    return pd.date_range(
        start=config.start_date,
        end=config.analysis_end_date,
        freq="MS",
    )


# =====================================================================
# DEALER GENERATION
# =====================================================================


def generate_dealers(
    config: SimulationConfig,
    rng: np.random.Generator,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Generate the dealer population.

    Returns two tables:

    dealers
        Visible dealer information that can eventually be loaded into
        the experimental PostgreSQL database.

    dealer_truth
        Hidden parameters used by the data-generating process.

    The hidden truth must NEVER be exposed to the Text-to-SQL baseline
    or the agentic analytics system.
    """

    dealer_rows: list[dict] = []
    truth_rows: list[dict] = []

    for (
        country,
        n_dealers,
    ) in config.dealers_per_country.items():

        for index in range(
            n_dealers
        ):

            # ---------------------------------------------------------
            # IDENTIFIER AND LOCATION
            # ---------------------------------------------------------

            dealer_id = (
                deterministic_uuid(
                    f"dealer:{country}:{index:03d}"
                )
            )

            city = str(
                rng.choice(
                    config.cities[
                        country
                    ]
                )
            )

            # ---------------------------------------------------------
            # LATENT OVERALL DEALER QUALITY
            # ---------------------------------------------------------
            #
            # This is not visible to the AI systems.
            #
            # Quality influences several parts of the funnel, but its
            # effect is deliberately limited so that one variable does
            # not determine all dealer performance.
            quality = float(
                rng.normal(
                    loc=0.0,
                    scale=1.0,
                )
            )

            # ---------------------------------------------------------
            # STAGE-SPECIFIC RANDOM VARIATION
            # ---------------------------------------------------------
            #
            # Independent noise helps create dealers with different
            # strengths and weaknesses.
            #
            # Example:
            #
            # Dealer A:
            #   high lead volume
            #   weak application conversion
            #
            # Dealer B:
            #   moderate lead volume
            #   strong application conversion
            #
            # Dealer C:
            #   good approvals
            #   weak final sale conversion
            #
            # This is more useful for analytics than simple performance
            # tiers where the same dealers dominate every metric.

            lead_noise = float(
                rng.normal(
                    0.0,
                    0.30,
                )
            )

            app_noise = float(
                rng.normal(
                    0.0,
                    0.45,
                )
            )

            approval_noise = float(
                rng.normal(
                    0.0,
                    0.40,
                )
            )

            sales_noise = float(
                rng.normal(
                    0.0,
                    0.45,
                )
            )

            # Variation in typical transaction value.
            value_noise = float(
                rng.normal(
                    0.0,
                    0.20,
                )
            )

            # ---------------------------------------------------------
            # LEAD VOLUME
            # ---------------------------------------------------------

            # Expected monthly lead volume.
            #
            # np.exp() guarantees that lead demand remains positive.
            base_monthly_leads = float(
                np.exp(
                    math.log(25)
                    + 0.35 * quality
                    + lead_noise
                )
            )

            # ---------------------------------------------------------
            # FUNNEL CONVERSION PROBABILITIES
            # ---------------------------------------------------------
            #
            # Overall quality has some influence, but stage-specific
            # variation now has greater importance than in the first
            # generator version.

            application_rate = sigmoid(
                -0.95
                + 0.18 * quality
                + app_noise
            )

            approval_rate = sigmoid(
                0.60
                + 0.15 * quality
                + approval_noise
            )

            sale_conversion_rate = sigmoid(
                0.15
                + 0.18 * quality
                + sales_noise
            )

            # ---------------------------------------------------------
            # LONG-TERM DEALER TREND
            # ---------------------------------------------------------
            #
            # Small positive values indicate gradual growth.
            # Small negative values indicate gradual decline.

            monthly_trend = float(
                rng.normal(
                    loc=0.0,
                    scale=0.006,
                )
            )

            # ---------------------------------------------------------
            # DEALER-SPECIFIC TRANSACTION VALUE
            # ---------------------------------------------------------
            #
            # Previously every dealer used essentially the same price
            # distribution. This caused:
            #
            #     sales count <-> revenue correlation ~= 1.0
            #
            # Giving dealers different average transaction values makes
            # revenue a distinct analytical metric rather than simply
            # another representation of sales volume.

            average_sale_value = float(
                np.exp(
                    math.log(14_000)
                    + 0.08 * quality
                    + value_noise
                )
            )

            # ---------------------------------------------------------
            # VISIBLE DEALER TABLE
            # ---------------------------------------------------------

            dealer_rows.append(
                {
                    "dealer_id":
                        dealer_id,

                    "dealer_name":
                        (
                            f"{country}-Dealer-"
                            f"{index + 1:03d}"
                        ),

                    "country":
                        country,

                    "city":
                        city,

                    "active":
                        True,
                }
            )

            # ---------------------------------------------------------
            # HIDDEN RESEARCH TRUTH
            # ---------------------------------------------------------

            truth_rows.append(
                {
                    "dealer_id":
                        dealer_id,

                    "latent_quality":
                        quality,

                    "base_monthly_leads":
                        base_monthly_leads,

                    "application_rate":
                        application_rate,

                    "approval_rate":
                        approval_rate,

                    "sale_conversion_rate":
                        sale_conversion_rate,

                    "monthly_trend":
                        monthly_trend,

                    "average_sale_value":
                        average_sale_value,
                }
            )

    dealers = pd.DataFrame(
        dealer_rows
    )

    dealer_truth = pd.DataFrame(
        truth_rows
    )

    return (
        dealers,
        dealer_truth,
    )


# =====================================================================
# LEAD GENERATION
# =====================================================================


def generate_leads(
    config: SimulationConfig,
    dealers: pd.DataFrame,
    dealer_truth: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    Generate individual lead events.

    Lead volume depends on:

    1. dealer-specific baseline demand
    2. dealer-specific long-term trend
    3. mild seasonal variation
    4. country-level simulation multiplier
    5. random Poisson variation

    New leads are created only during the primary analysis window.
    """

    lead_rows: list[dict] = []

    periods = (
        generate_month_periods(
            config
        )
    )

    truth_lookup = (
        dealer_truth
        .set_index(
            "dealer_id"
        )
    )

    lead_counter = 0

    for (
        month_index,
        period_start,
    ) in enumerate(periods):

        period_end = (
            period_start
            + pd.offsets.MonthEnd(1)
        )

        for dealer in dealers.itertuples(
            index=False
        ):

            truth = truth_lookup.loc[
                dealer.dealer_id
            ]

            # ---------------------------------------------------------
            # DEALER TREND
            # ---------------------------------------------------------

            trend_factor = max(
                0.65,
                (
                    1.0
                    + float(
                        truth[
                            "monthly_trend"
                        ]
                    )
                    * month_index
                ),
            )

            # ---------------------------------------------------------
            # SEASONAL EFFECT
            # ---------------------------------------------------------

            month_seasonality = (
                seasonal_factor(
                    period_start.month
                )
            )

            # ---------------------------------------------------------
            # COUNTRY EFFECT
            # ---------------------------------------------------------

            country_factor = (
                config
                .country_demand_factor[
                    dealer.country
                ]
            )

            # ---------------------------------------------------------
            # EXPECTED MONTHLY LEAD VOLUME
            # ---------------------------------------------------------

            expected_leads = (
                float(
                    truth[
                        "base_monthly_leads"
                    ]
                )
                * trend_factor
                * month_seasonality
                * country_factor
            )

            # Poisson lambda must always be positive.
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
                period_end
                - period_start
            ).days + 1

            # ---------------------------------------------------------
            # CREATE INDIVIDUAL LEADS
            # ---------------------------------------------------------

            for _ in range(
                number_of_leads
            ):

                lead_counter += 1

                lead_id = (
                    deterministic_uuid(
                        f"lead:{lead_counter}"
                    )
                )

                # Random day within the current month.
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
                        "lead_id":
                            lead_id,

                        "dealer_id":
                            dealer.dealer_id,

                        "country":
                            dealer.country,

                        "lead_date":
                            lead_date.date(),

                        "lead_source":
                            str(
                                rng.choice(
                                    LEAD_SOURCES
                                )
                            ),
                    }
                )

    return pd.DataFrame(
        lead_rows
    )


# =====================================================================
# APPLICATION GENERATION
# =====================================================================


def generate_applications(
    config: SimulationConfig,
    leads: pd.DataFrame,
    dealer_truth: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    Convert a subset of leads into applications.

    Every application references a real lead.

    Therefore the data contains an actual relationship:

        Dealer
          -> Lead
              -> Application

    Late-December leads may generate applications during January 2026
    because the simulation contains a maturation buffer.
    """

    application_rows: list[dict] = []

    truth_lookup = (
        dealer_truth
        .set_index(
            "dealer_id"
        )
    )

    # Downstream events may occur during the maturation buffer.
    simulation_end = pd.Timestamp(
        config.simulation_end_date
    )

    application_counter = 0

    for lead in leads.itertuples(
        index=False
    ):

        truth = truth_lookup.loc[
            lead.dealer_id
        ]

        application_probability = float(
            truth[
                "application_rate"
            ]
        )

        # -------------------------------------------------------------
        # DOES THIS LEAD APPLY?
        # -------------------------------------------------------------

        if (
            rng.random()
            >= application_probability
        ):
            continue

        lead_date = pd.Timestamp(
            lead.lead_date
        )

        # Application may happen on the same day or up to 10 days later.
        delay_days = int(
            rng.integers(
                low=0,
                high=(
                    MAX_APPLICATION_DELAY_DAYS
                    + 1
                ),
            )
        )

        application_date = (
            lead_date
            + pd.Timedelta(
                days=delay_days
            )
        )

        # The buffer is large enough for valid applications generated
        # from leads inside the analysis window.
        if (
            application_date
            > simulation_end
        ):
            continue

        application_counter += 1

        application_id = (
            deterministic_uuid(
                f"application:"
                f"{application_counter}"
            )
        )

        # -------------------------------------------------------------
        # APPROVAL DECISION
        # -------------------------------------------------------------

        approved = (
            rng.random()
            < float(
                truth[
                    "approval_rate"
                ]
            )
        )

        application_rows.append(
            {
                "application_id":
                    application_id,

                "lead_id":
                    lead.lead_id,

                "dealer_id":
                    lead.dealer_id,

                "country":
                    lead.country,

                "application_date":
                    application_date.date(),

                "application_channel":
                    str(
                        rng.choice(
                            APPLICATION_CHANNELS
                        )
                    ),

                "status":
                    (
                        "approved"
                        if approved
                        else "rejected"
                    ),
            }
        )

    return pd.DataFrame(
        application_rows
    )


# =====================================================================
# SALES GENERATION
# =====================================================================


def generate_sales(
    config: SimulationConfig,
    applications: pd.DataFrame,
    dealer_truth: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    Generate sales from approved applications.

    Only approved applications can produce sales.

    Every sale keeps references to:

        application_id
        lead_id
        dealer_id

    giving us the complete observable funnel:

        Dealer
          -> Lead
              -> Application
                  -> Approval
                      -> Sale
    """

    sale_rows: list[dict] = []

    truth_lookup = (
        dealer_truth
        .set_index(
            "dealer_id"
        )
    )

    simulation_end = pd.Timestamp(
        config.simulation_end_date
    )

    sale_counter = 0

    # Only approved applications can become sales.
    approved_apps = applications[
        applications["status"]
        == "approved"
    ].copy()

    for application in (
        approved_apps.itertuples(
            index=False
        )
    ):

        truth = truth_lookup.loc[
            application.dealer_id
        ]

        sale_probability = float(
            truth[
                "sale_conversion_rate"
            ]
        )

        # -------------------------------------------------------------
        # DOES THE APPROVED APPLICATION CONVERT?
        # -------------------------------------------------------------

        if (
            rng.random()
            >= sale_probability
        ):
            continue

        application_date = pd.Timestamp(
            application.application_date
        )

        sale_delay_days = int(
            rng.integers(
                low=0,
                high=(
                    MAX_SALE_DELAY_DAYS
                    + 1
                ),
            )
        )

        sale_date = (
            application_date
            + pd.Timedelta(
                days=sale_delay_days
            )
        )

        if sale_date > simulation_end:
            continue

        sale_counter += 1

        sale_id = (
            deterministic_uuid(
                f"sale:{sale_counter}"
            )
        )

        # -------------------------------------------------------------
        # SALE VALUE
        # -------------------------------------------------------------
        #
        # Each dealer has its own hidden typical transaction value.
        #
        # Individual transactions then vary around that dealer-specific
        # average using a log-normal distribution.

        dealer_average_sale_value = float(
            truth[
                "average_sale_value"
            ]
        )

        sale_amount_usd = float(
            np.clip(
                rng.lognormal(
                    mean=math.log(
                        dealer_average_sale_value
                    ),
                    sigma=0.25,
                ),
                4_000,
                60_000,
            )
        )

        sale_rows.append(
            {
                "sale_id":
                    sale_id,

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

                "financing_bank":
                    str(
                        rng.choice(
                            FINANCING_BANKS
                        )
                    ),
            }
        )

    return pd.DataFrame(
        sale_rows
    )


# =====================================================================
# SAVE DATASET
# =====================================================================


def save_dataset(
    config: SimulationConfig,
    dealers: pd.DataFrame,
    dealer_truth: pd.DataFrame,
    leads: pd.DataFrame,
    applications: pd.DataFrame,
    sales: pd.DataFrame,
) -> None:
    """
    Save visible datasets, hidden truth, and metadata.

    Visible experimental data:
        data/generated/v2/

    Hidden researcher-only truth:
        data/research_truth/v2/

    Metadata:
        metadata/
    """

    # Create directories when they do not already exist.
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

    # -------------------------------------------------------------
    # VISIBLE DATA
    # -------------------------------------------------------------

    visible_datasets = {
        "dealers":
            dealers,

        "leads":
            leads,

        "applications":
            applications,

        "sales":
            sales,
    }

    for (
        dataset_name,
        dataframe,
    ) in visible_datasets.items():

        output_path = (
            config.output_dir
            / f"{dataset_name}.csv"
        )

        dataframe.to_csv(
            output_path,
            index=False,
        )

    # -------------------------------------------------------------
    # HIDDEN RESEARCH TRUTH
    # -------------------------------------------------------------

    dealer_truth.to_csv(
        (
            config.truth_dir
            / "dealer_latent_truth.csv"
        ),
        index=False,
    )

    # -------------------------------------------------------------
    # METADATA
    # -------------------------------------------------------------

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

    metadata = {
        "generator_version":
            config.generator_version,

        "random_seed":
            config.seed,

        "start_date":
            config.start_date,

        "analysis_end_date":
            config.analysis_end_date,

        "simulation_end_date":
            config.simulation_end_date,

        "countries":
            list(
                config
                .dealers_per_country
                .keys()
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
            approved_count,

        "rejected_application_count":
            rejected_count,

        "sale_count":
            int(
                len(sales)
            ),

        "note": (
            "This dataset is fully synthetic. "
            "Country demand multipliers, dealer characteristics, "
            "conversion probabilities, transaction values, and temporal "
            "relationships are simulation parameters and must not be "
            "interpreted as empirical claims about real automotive "
            "markets."
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


# =====================================================================
# MASTER GENERATION PIPELINE
# =====================================================================


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
    Run the complete synthetic-data generation process.

    Pipeline
    --------

        Dealers
            |
            v
         Leads
            |
            v
      Applications
            |
            v
        Approvals
            |
            v
         Sales

    The same seed and generator version should reproduce the same data.
    """

    # Use a single controlled RNG for the complete simulation.
    rng = np.random.default_rng(
        config.seed
    )

    # -------------------------------------------------------------
    # 1. DEALERS
    # -------------------------------------------------------------

    (
        dealers,
        dealer_truth,
    ) = generate_dealers(
        config=config,
        rng=rng,
    )

    # -------------------------------------------------------------
    # 2. LEADS
    # -------------------------------------------------------------

    leads = generate_leads(
        config=config,
        dealers=dealers,
        dealer_truth=dealer_truth,
        rng=rng,
    )

    # -------------------------------------------------------------
    # 3. APPLICATIONS
    # -------------------------------------------------------------

    applications = generate_applications(
        config=config,
        leads=leads,
        dealer_truth=dealer_truth,
        rng=rng,
    )

    # -------------------------------------------------------------
    # 4. SALES
    # -------------------------------------------------------------

    sales = generate_sales(
        config=config,
        applications=applications,
        dealer_truth=dealer_truth,
        rng=rng,
    )

    # -------------------------------------------------------------
    # 5. SAVE
    # -------------------------------------------------------------

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


# =====================================================================
# DEVELOPMENT SUMMARY
# =====================================================================


def print_dataset_summary(
    dealers: pd.DataFrame,
    dealer_truth: pd.DataFrame,
    leads: pd.DataFrame,
    applications: pd.DataFrame,
    sales: pd.DataFrame,
) -> None:
    """
    Print basic information after data generation.

    These are convenience checks only.

    Formal integrity checking belongs in validation.py.
    """

    print(
        "\n"
        + "=" * 70
    )

    print(
        "SYNTHETIC DEALER ANALYTICS DATASET"
    )

    print(
        "=" * 70
    )

    print(
        "\nSample dealers:"
    )
    print(
        dealers.head()
    )

    print(
        "\nSample hidden dealer truth:"
    )
    print(
        dealer_truth.head()
    )

    print(
        "\nSample leads:"
    )
    print(
        leads.head()
    )

    print(
        "\nSample applications:"
    )
    print(
        applications.head()
    )

    print(
        "\nSample sales:"
    )
    print(
        sales.head()
    )

    print(
        "\n"
        + "-" * 70
    )

    print(
        "DATASET COUNTS"
    )

    print(
        "-" * 70
    )

    print(
        f"Dealers:      "
        f"{len(dealers):,}"
    )

    print(
        f"Leads:        "
        f"{len(leads):,}"
    )

    print(
        f"Applications: "
        f"{len(applications):,}"
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
        f"Approved:     "
        f"{approved_count:,}"
    )

    print(
        f"Rejected:     "
        f"{rejected_count:,}"
    )

    print(
        f"Sales:        "
        f"{len(sales):,}"
    )

    print(
        "\n"
        + "-" * 70
    )

    print(
        "DATE RANGE"
    )

    print(
        "-" * 70
    )

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
        sales[
            "sale_date"
        ].min(),
        "to",
        sales[
            "sale_date"
        ].max(),
    )

    print(
        "\n"
        + "-" * 70
    )

    print(
        "LEADS BY COUNTRY"
    )

    print(
        "-" * 70
    )

    print(
        leads
        .groupby(
            "country"
        )
        .size()
        .sort_values(
            ascending=False
        )
    )

    print(
        "\n"
        + "-" * 70
    )

    print(
        "DUPLICATE IDENTIFIER CHECK"
    )

    print(
        "-" * 70
    )

    print(
        "Duplicate dealer IDs:",
        dealers[
            "dealer_id"
        ]
        .duplicated()
        .sum(),
    )

    print(
        "Duplicate lead IDs:",
        leads[
            "lead_id"
        ]
        .duplicated()
        .sum(),
    )

    print(
        "Duplicate application IDs:",
        applications[
            "application_id"
        ]
        .duplicated()
        .sum(),
    )

    print(
        "Duplicate sale IDs:",
        sales[
            "sale_id"
        ]
        .duplicated()
        .sum(),
    )

    print(
        "\nGeneration completed."
    )


# =====================================================================
# MODULE ENTRY POINT
# =====================================================================

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