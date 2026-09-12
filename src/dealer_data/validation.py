from __future__ import annotations

import json
from dataclasses import (
    asdict,
    dataclass,
)
from pathlib import Path

import pandas as pd

from .config import SimulationConfig


# =====================================================================
# VALIDATION RESULT OBJECT
# =====================================================================


@dataclass
class ValidationCheck:
    """
    Result of one dataset-integrity check.

    passed=True means the rule was satisfied.
    """

    name: str
    passed: bool
    details: str


# =====================================================================
# VALIDATION HELPERS
# =====================================================================


def add_check(
    checks: list[ValidationCheck],
    name: str,
    passed: bool,
    details: str,
) -> None:
    """
    Store a validation result.
    """

    checks.append(
        ValidationCheck(
            name=name,
            passed=bool(passed),
            details=details,
        )
    )


def require_columns(
    dataframe: pd.DataFrame,
    required_columns: set[str],
    dataframe_name: str,
    checks: list[ValidationCheck],
) -> None:
    """
    Confirm that a dataframe contains its required schema.
    """

    missing_columns = (
        required_columns
        - set(
            dataframe.columns
        )
    )

    add_check(
        checks=checks,
        name=(
            f"{dataframe_name}"
            f"_required_columns"
        ),
        passed=(
            len(
                missing_columns
            )
            == 0
        ),
        details=(
            f"{dataframe_name}: "
            f"missing columns = "
            f"{sorted(missing_columns)}"
        ),
    )


def check_unique_column(
    dataframe: pd.DataFrame,
    column: str,
    dataframe_name: str,
    checks: list[ValidationCheck],
) -> None:
    """
    Verify that an identifier expected to be unique contains no
    duplicates.
    """

    duplicate_count = int(
        dataframe[
            column
        ]
        .duplicated()
        .sum()
    )

    add_check(
        checks=checks,
        name=(
            f"{dataframe_name}_"
            f"{column}_unique"
        ),
        passed=(
            duplicate_count
            == 0
        ),
        details=(
            f"{dataframe_name}."
            f"{column}: "
            f"{duplicate_count} "
            f"duplicate values"
        ),
    )


def check_required_nulls(
    dataframe: pd.DataFrame,
    required_columns: list[str],
    dataframe_name: str,
    checks: list[ValidationCheck],
) -> None:
    """
    Confirm that mandatory variables do not contain missing values.

    Missing values are NOT automatically replaced.

    In research data:

        missing != zero

    so silently converting one to the other would be methodologically
    unsafe.
    """

    null_counts = (
        dataframe[
            required_columns
        ]
        .isna()
        .sum()
    )

    total_nulls = int(
        null_counts.sum()
    )

    details = {
        column:
            int(count)
        for (
            column,
            count,
        ) in null_counts.items()
        if count > 0
    }

    add_check(
        checks=checks,
        name=(
            f"{dataframe_name}"
            f"_required_nulls"
        ),
        passed=(
            total_nulls
            == 0
        ),
        details=(
            f"{dataframe_name}: "
            f"missing required values = "
            f"{details}"
        ),
    )


# =====================================================================
# MAIN VALIDATION PIPELINE
# =====================================================================


def validate_dataset(
    config: SimulationConfig,
    dealers: pd.DataFrame,
    dealer_truth: pd.DataFrame,
    leads: pd.DataFrame,
    applications: pd.DataFrame,
    sales: pd.DataFrame,
) -> list[ValidationCheck]:
    """
    Validate the complete synthetic dataset.

    Validation tests structural integrity only.

    It does NOT determine whether the simulation is statistically
    realistic. That is handled separately during EDA.
    """

    checks: list[
        ValidationCheck
    ] = []

    # =================================================================
    # 1. REQUIRED COLUMNS
    # =================================================================

    dealer_columns = {
        "dealer_id",
        "dealer_name",
        "country",
        "city",
        "active",
    }

    truth_columns = {
        "dealer_id",
        "latent_quality",
        "base_monthly_leads",
        "application_rate",
        "approval_rate",
        "sale_conversion_rate",
        "monthly_trend",
        "average_sale_value",
    }

    lead_columns = {
        "lead_id",
        "dealer_id",
        "country",
        "lead_date",
        "lead_source",
    }

    application_columns = {
        "application_id",
        "lead_id",
        "dealer_id",
        "country",
        "application_date",
        "application_channel",
        "status",
    }

    sale_columns = {
        "sale_id",
        "application_id",
        "lead_id",
        "dealer_id",
        "country",
        "sale_date",
        "sale_amount_usd",
        "financing_bank",
    }

    require_columns(
        dealers,
        dealer_columns,
        "dealers",
        checks,
    )

    require_columns(
        dealer_truth,
        truth_columns,
        "dealer_truth",
        checks,
    )

    require_columns(
        leads,
        lead_columns,
        "leads",
        checks,
    )

    require_columns(
        applications,
        application_columns,
        "applications",
        checks,
    )

    require_columns(
        sales,
        sale_columns,
        "sales",
        checks,
    )

    # =================================================================
    # 2. UNIQUE IDENTIFIERS
    # =================================================================

    check_unique_column(
        dealers,
        "dealer_id",
        "dealers",
        checks,
    )

    check_unique_column(
        dealer_truth,
        "dealer_id",
        "dealer_truth",
        checks,
    )

    check_unique_column(
        leads,
        "lead_id",
        "leads",
        checks,
    )

    check_unique_column(
        applications,
        "application_id",
        "applications",
        checks,
    )

    check_unique_column(
        sales,
        "sale_id",
        "sales",
        checks,
    )

    # A lead may generate at most one application in our current
    # simulation model.
    check_unique_column(
        applications,
        "lead_id",
        "applications",
        checks,
    )

    # An approved application may generate at most one sale.
    check_unique_column(
        sales,
        "application_id",
        "sales",
        checks,
    )

    # =================================================================
    # 3. REQUIRED VALUES
    # =================================================================

    check_required_nulls(
        dealers,
        [
            "dealer_id",
            "dealer_name",
            "country",
            "city",
            "active",
        ],
        "dealers",
        checks,
    )

    check_required_nulls(
        dealer_truth,
        [
            "dealer_id",
            "latent_quality",
            "base_monthly_leads",
            "application_rate",
            "approval_rate",
            "sale_conversion_rate",
            "monthly_trend",
            "average_sale_value",
        ],
        "dealer_truth",
        checks,
    )

    check_required_nulls(
        leads,
        [
            "lead_id",
            "dealer_id",
            "country",
            "lead_date",
            "lead_source",
        ],
        "leads",
        checks,
    )

    check_required_nulls(
        applications,
        [
            "application_id",
            "lead_id",
            "dealer_id",
            "country",
            "application_date",
            "application_channel",
            "status",
        ],
        "applications",
        checks,
    )

    check_required_nulls(
        sales,
        [
            "sale_id",
            "application_id",
            "lead_id",
            "dealer_id",
            "country",
            "sale_date",
            "sale_amount_usd",
            "financing_bank",
        ],
        "sales",
        checks,
    )

    # =================================================================
    # 4. COUNTRY VALIDITY
    # =================================================================

    valid_countries = set(
        config
        .dealers_per_country
        .keys()
    )

    for (
        name,
        dataframe,
    ) in [
        ("dealers", dealers),
        ("leads", leads),
        ("applications", applications),
        ("sales", sales),
    ]:

        observed = set(
            dataframe[
                "country"
            ]
            .dropna()
            .unique()
        )

        invalid = (
            observed
            - valid_countries
        )

        add_check(
            checks=checks,
            name=(
                f"{name}"
                f"_valid_countries"
            ),
            passed=(
                len(invalid)
                == 0
            ),
            details=(
                f"{name}: "
                f"invalid countries = "
                f"{sorted(invalid)}"
            ),
        )

    # =================================================================
    # 5. DATE WINDOW VALIDITY
    # =================================================================

    start_date = pd.Timestamp(
        config.start_date
    )

    analysis_end_date = pd.Timestamp(
        config.analysis_end_date
    )

    simulation_end_date = pd.Timestamp(
        config.simulation_end_date
    )

    # -------------------------------------------------------------
    # LEADS
    # -------------------------------------------------------------
    #
    # Leads must exist only in the primary analysis window.

    lead_dates = pd.to_datetime(
        leads[
            "lead_date"
        ],
        errors="coerce",
    )

    invalid_lead_dates = int(
        lead_dates
        .isna()
        .sum()
    )

    leads_outside_window = int(
        (
            (
                lead_dates
                < start_date
            )
            |
            (
                lead_dates
                > analysis_end_date
            )
        ).sum()
    )

    add_check(
        checks=checks,
        name="leads_valid_dates",
        passed=(
            invalid_lead_dates
            == 0
            and
            leads_outside_window
            == 0
        ),
        details=(
            "leads.lead_date: "
            f"{invalid_lead_dates} "
            "invalid dates, "
            f"{leads_outside_window} "
            "outside analysis window"
        ),
    )

    # -------------------------------------------------------------
    # APPLICATIONS AND SALES
    # -------------------------------------------------------------
    #
    # These events are allowed to mature during January 2026.

    for (
        name,
        dataframe,
        date_column,
    ) in [
        (
            "applications",
            applications,
            "application_date",
        ),
        (
            "sales",
            sales,
            "sale_date",
        ),
    ]:

        dates = pd.to_datetime(
            dataframe[
                date_column
            ],
            errors="coerce",
        )

        invalid_date_count = int(
            dates
            .isna()
            .sum()
        )

        outside_window = int(
            (
                (
                    dates
                    < start_date
                )
                |
                (
                    dates
                    > simulation_end_date
                )
            ).sum()
        )

        add_check(
            checks=checks,
            name=(
                f"{name}_valid_dates"
            ),
            passed=(
                invalid_date_count
                == 0
                and
                outside_window
                == 0
            ),
            details=(
                f"{name}.{date_column}: "
                f"{invalid_date_count} "
                "invalid dates, "
                f"{outside_window} "
                "outside simulation window"
            ),
        )

    # =================================================================
    # 6. FOREIGN KEY INTEGRITY
    # =================================================================

    dealer_ids = set(
        dealers[
            "dealer_id"
        ]
    )

    lead_ids = set(
        leads[
            "lead_id"
        ]
    )

    application_ids = set(
        applications[
            "application_id"
        ]
    )

    # Leads -> Dealers
    invalid_lead_dealers = int(
        (
            ~leads[
                "dealer_id"
            ]
            .isin(
                dealer_ids
            )
        ).sum()
    )

    add_check(
        checks=checks,
        name=(
            "leads_reference_"
            "existing_dealers"
        ),
        passed=(
            invalid_lead_dealers
            == 0
        ),
        details=(
            f"{invalid_lead_dealers} "
            "leads reference "
            "non-existent dealers"
        ),
    )

    # Applications -> Leads
    orphan_applications = int(
        (
            ~applications[
                "lead_id"
            ]
            .isin(
                lead_ids
            )
        ).sum()
    )

    add_check(
        checks=checks,
        name=(
            "applications_reference_"
            "existing_leads"
        ),
        passed=(
            orphan_applications
            == 0
        ),
        details=(
            f"{orphan_applications} "
            "applications reference "
            "missing leads"
        ),
    )

    # Applications -> Dealers
    invalid_application_dealers = int(
        (
            ~applications[
                "dealer_id"
            ]
            .isin(
                dealer_ids
            )
        ).sum()
    )

    add_check(
        checks=checks,
        name=(
            "applications_reference_"
            "existing_dealers"
        ),
        passed=(
            invalid_application_dealers
            == 0
        ),
        details=(
            f"{invalid_application_dealers} "
            "applications reference "
            "missing dealers"
        ),
    )

    # Sales -> Applications
    orphan_sales = int(
        (
            ~sales[
                "application_id"
            ]
            .isin(
                application_ids
            )
        ).sum()
    )

    add_check(
        checks=checks,
        name=(
            "sales_reference_"
            "existing_applications"
        ),
        passed=(
            orphan_sales
            == 0
        ),
        details=(
            f"{orphan_sales} "
            "sales reference "
            "missing applications"
        ),
    )

    # Sales -> Leads
    invalid_sale_leads = int(
        (
            ~sales[
                "lead_id"
            ]
            .isin(
                lead_ids
            )
        ).sum()
    )

    add_check(
        checks=checks,
        name=(
            "sales_reference_"
            "existing_leads"
        ),
        passed=(
            invalid_sale_leads
            == 0
        ),
        details=(
            f"{invalid_sale_leads} "
            "sales reference "
            "missing leads"
        ),
    )

    # =================================================================
    # 7. APPLICATION STATUS VALIDITY
    # =================================================================

    valid_statuses = {
        "approved",
        "rejected",
    }

    observed_statuses = set(
        applications[
            "status"
        ]
        .dropna()
        .unique()
    )

    invalid_statuses = (
        observed_statuses
        - valid_statuses
    )

    add_check(
        checks=checks,
        name=(
            "application_status_"
            "validity"
        ),
        passed=(
            len(
                invalid_statuses
            )
            == 0
        ),
        details=(
            "Invalid statuses = "
            f"{sorted(invalid_statuses)}"
        ),
    )

    # =================================================================
    # 8. SALES MUST COME FROM APPROVED APPLICATIONS
    # =================================================================

    application_status_lookup = (
        applications
        .set_index(
            "application_id"
        )[
            "status"
        ]
    )

    sale_statuses = (
        sales[
            "application_id"
        ]
        .map(
            application_status_lookup
        )
    )

    sales_from_nonapproved = int(
        (
            sale_statuses
            != "approved"
        ).sum()
    )

    add_check(
        checks=checks,
        name=(
            "sales_only_from_"
            "approved_applications"
        ),
        passed=(
            sales_from_nonapproved
            == 0
        ),
        details=(
            f"{sales_from_nonapproved} "
            "sales came from "
            "non-approved applications"
        ),
    )

    # =================================================================
    # 9. CHRONOLOGICAL CONSISTENCY
    # =================================================================

    lead_date_lookup = (
        leads
        .set_index(
            "lead_id"
        )[
            "lead_date"
        ]
    )

    application_date_lookup = (
        applications
        .set_index(
            "application_id"
        )[
            "application_date"
        ]
    )

    # -------------------------------------------------------------
    # APPLICATION DATE >= LEAD DATE
    # -------------------------------------------------------------

    application_lead_dates = (
        pd.to_datetime(
            applications[
                "lead_id"
            ]
            .map(
                lead_date_lookup
            )
        )
    )

    application_dates = pd.to_datetime(
        applications[
            "application_date"
        ]
    )

    application_before_lead = int(
        (
            application_dates
            < application_lead_dates
        ).sum()
    )

    add_check(
        checks=checks,
        name="application_after_lead",
        passed=(
            application_before_lead
            == 0
        ),
        details=(
            f"{application_before_lead} "
            "applications occur before "
            "their originating lead"
        ),
    )

    # -------------------------------------------------------------
    # SALE DATE >= APPLICATION DATE
    # -------------------------------------------------------------

    sale_application_dates = (
        pd.to_datetime(
            sales[
                "application_id"
            ]
            .map(
                application_date_lookup
            )
        )
    )

    sale_dates = pd.to_datetime(
        sales[
            "sale_date"
        ]
    )

    sale_before_application = int(
        (
            sale_dates
            < sale_application_dates
        ).sum()
    )

    add_check(
        checks=checks,
        name="sale_after_application",
        passed=(
            sale_before_application
            == 0
        ),
        details=(
            f"{sale_before_application} "
            "sales occur before "
            "their applications"
        ),
    )

    # =================================================================
    # 10. DEALER / COUNTRY CONSISTENCY
    # =================================================================

    dealer_country_lookup = (
        dealers
        .set_index(
            "dealer_id"
        )[
            "country"
        ]
    )

    for (
        name,
        dataframe,
    ) in [
        ("leads", leads),
        (
            "applications",
            applications,
        ),
        ("sales", sales),
    ]:

        expected_country = (
            dataframe[
                "dealer_id"
            ]
            .map(
                dealer_country_lookup
            )
        )

        mismatch_count = int(
            (
                dataframe[
                    "country"
                ]
                != expected_country
            ).sum()
        )

        add_check(
            checks=checks,
            name=(
                f"{name}_dealer_"
                "country_consistency"
            ),
            passed=(
                mismatch_count
                == 0
            ),
            details=(
                f"{mismatch_count} "
                f"{name} rows have "
                "a country inconsistent "
                "with their dealer"
            ),
        )

    # =================================================================
    # 11. APPLICATION MUST MATCH ORIGINAL LEAD
    # =================================================================

    lead_dealer_lookup = (
        leads
        .set_index(
            "lead_id"
        )[
            "dealer_id"
        ]
    )

    expected_application_dealer = (
        applications[
            "lead_id"
        ]
        .map(
            lead_dealer_lookup
        )
    )

    application_dealer_mismatch = int(
        (
            applications[
                "dealer_id"
            ]
            != expected_application_dealer
        ).sum()
    )

    add_check(
        checks=checks,
        name=(
            "application_lead_"
            "dealer_consistency"
        ),
        passed=(
            application_dealer_mismatch
            == 0
        ),
        details=(
            f"{application_dealer_mismatch} "
            "applications use a dealer "
            "different from their "
            "originating lead"
        ),
    )

    # =================================================================
    # 12. SALE MUST MATCH APPLICATION
    # =================================================================

    application_lead_lookup = (
        applications
        .set_index(
            "application_id"
        )[
            "lead_id"
        ]
    )

    application_dealer_lookup = (
        applications
        .set_index(
            "application_id"
        )[
            "dealer_id"
        ]
    )

    expected_sale_lead = (
        sales[
            "application_id"
        ]
        .map(
            application_lead_lookup
        )
    )

    expected_sale_dealer = (
        sales[
            "application_id"
        ]
        .map(
            application_dealer_lookup
        )
    )

    sale_lead_mismatch = int(
        (
            sales[
                "lead_id"
            ]
            != expected_sale_lead
        ).sum()
    )

    sale_dealer_mismatch = int(
        (
            sales[
                "dealer_id"
            ]
            != expected_sale_dealer
        ).sum()
    )

    add_check(
        checks=checks,
        name=(
            "sale_application_"
            "lead_consistency"
        ),
        passed=(
            sale_lead_mismatch
            == 0
        ),
        details=(
            f"{sale_lead_mismatch} "
            "sales contain an "
            "incorrect lead_id"
        ),
    )

    add_check(
        checks=checks,
        name=(
            "sale_application_"
            "dealer_consistency"
        ),
        passed=(
            sale_dealer_mismatch
            == 0
        ),
        details=(
            f"{sale_dealer_mismatch} "
            "sales contain an "
            "incorrect dealer_id"
        ),
    )

    # =================================================================
    # 13. GLOBAL FUNNEL LOGIC
    # =================================================================

    number_of_leads = len(
        leads
    )

    number_of_applications = len(
        applications
    )

    number_of_approved = int(
        (
            applications[
                "status"
            ]
            == "approved"
        ).sum()
    )

    number_of_sales = len(
        sales
    )

    funnel_valid = (
        number_of_leads
        >= number_of_applications
        >= number_of_approved
        >= number_of_sales
    )

    add_check(
        checks=checks,
        name="global_funnel_counts",
        passed=funnel_valid,
        details=(
            f"Leads="
            f"{number_of_leads:,}, "
            f"Applications="
            f"{number_of_applications:,}, "
            f"Approved="
            f"{number_of_approved:,}, "
            f"Sales="
            f"{number_of_sales:,}"
        ),
    )

    # =================================================================
    # 14. SALE AMOUNT VALIDITY
    # =================================================================

    invalid_sale_amounts = int(
        (
            sales[
                "sale_amount_usd"
            ]
            <= 0
        ).sum()
    )

    add_check(
        checks=checks,
        name="positive_sale_amounts",
        passed=(
            invalid_sale_amounts
            == 0
        ),
        details=(
            f"{invalid_sale_amounts} "
            "sales contain "
            "non-positive amounts"
        ),
    )

    # =================================================================
    # 15. HIDDEN DEALER TRUTH COVERAGE
    # =================================================================

    visible_dealer_ids = set(
        dealers[
            "dealer_id"
        ]
    )

    truth_dealer_ids = set(
        dealer_truth[
            "dealer_id"
        ]
    )

    missing_truth = (
        visible_dealer_ids
        - truth_dealer_ids
    )

    extra_truth = (
        truth_dealer_ids
        - visible_dealer_ids
    )

    truth_matches = (
        len(
            missing_truth
        )
        == 0
        and
        len(
            extra_truth
        )
        == 0
    )

    add_check(
        checks=checks,
        name=(
            "dealer_truth_"
            "matches_dealers"
        ),
        passed=truth_matches,
        details=(
            "Missing truth records="
            f"{len(missing_truth)}, "
            "extra truth records="
            f"{len(extra_truth)}"
        ),
    )

    # =================================================================
    # 16. HIDDEN PROBABILITY VALIDITY
    # =================================================================

    probability_columns = [
        "application_rate",
        "approval_rate",
        "sale_conversion_rate",
    ]

    invalid_probability_count = 0

    for column in (
        probability_columns
    ):

        invalid_probability_count += int(
            (
                (
                    dealer_truth[
                        column
                    ]
                    < 0
                )
                |
                (
                    dealer_truth[
                        column
                    ]
                    > 1
                )
            ).sum()
        )

    add_check(
        checks=checks,
        name=(
            "hidden_probabilities_"
            "valid"
        ),
        passed=(
            invalid_probability_count
            == 0
        ),
        details=(
            f"{invalid_probability_count} "
            "hidden probabilities "
            "fall outside [0, 1]"
        ),
    )

    # =================================================================
    # 17. HIDDEN POSITIVE PARAMETERS
    # =================================================================

    invalid_base_leads = int(
        (
            dealer_truth[
                "base_monthly_leads"
            ]
            <= 0
        ).sum()
    )

    add_check(
        checks=checks,
        name=(
            "positive_hidden_"
            "base_monthly_leads"
        ),
        passed=(
            invalid_base_leads
            == 0
        ),
        details=(
            f"{invalid_base_leads} "
            "dealers have non-positive "
            "base monthly lead demand"
        ),
    )

    invalid_average_sale_values = int(
        (
            dealer_truth[
                "average_sale_value"
            ]
            <= 0
        ).sum()
    )

    add_check(
        checks=checks,
        name=(
            "positive_hidden_"
            "average_sale_value"
        ),
        passed=(
            invalid_average_sale_values
            == 0
        ),
        details=(
            f"{invalid_average_sale_values} "
            "dealers have non-positive "
            "hidden average sale values"
        ),
    )

    return checks


# =====================================================================
# REPORTING
# =====================================================================


def print_validation_report(
    checks: list[ValidationCheck],
) -> None:
    """
    Print validation results to the terminal.
    """

    print(
        "\n"
        + "=" * 70
    )

    print(
        "DATASET VALIDATION REPORT"
    )

    print(
        "=" * 70
    )

    passed_count = 0

    for check in checks:

        status = (
            "PASS"
            if check.passed
            else "FAIL"
        )

        if check.passed:
            passed_count += 1

        print(
            f"[{status}] "
            f"{check.name}"
        )

        print(
            f"       "
            f"{check.details}"
        )

    total_checks = len(
        checks
    )

    failed_count = (
        total_checks
        - passed_count
    )

    print(
        "\n"
        + "-" * 70
    )

    print(
        f"Passed: "
        f"{passed_count}/"
        f"{total_checks}"
    )

    print(
        f"Failed: "
        f"{failed_count}/"
        f"{total_checks}"
    )

    print(
        "-" * 70
    )

    if failed_count == 0:

        print(
            "STRUCTURAL VALIDATION PASSED."
        )

    else:

        print(
            "STRUCTURAL VALIDATION FAILED."
        )


def save_validation_report(
    checks: list[ValidationCheck],
    output_path: Path,
) -> None:
    """
    Save validation results as JSON.

    Keeping the validation report gives us an auditable record showing
    that the dataset passed structural checks at a specific development
    stage.
    """

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    report = {
        "total_checks":
            len(checks),

        "passed_checks":
            sum(
                check.passed
                for check in checks
            ),

        "failed_checks":
            sum(
                not check.passed
                for check in checks
            ),

        "checks":
            [
                asdict(check)
                for check in checks
            ],
    }

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            report,
            file,
            indent=4,
        )


def assert_validation_passed(
    checks: list[ValidationCheck],
) -> None:
    """
    Prevent the research pipeline from continuing when structural
    validation has failed.
    """

    failed_checks = [
        check
        for check in checks
        if not check.passed
    ]

    if failed_checks:

        failed_names = [
            check.name
            for check in failed_checks
        ]

        raise ValueError(
            "Dataset validation failed. "
            f"Failed checks: "
            f"{failed_names}"
        )