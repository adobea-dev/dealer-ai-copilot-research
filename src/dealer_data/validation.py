from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

import pandas as pd

from .config import SimulationConfig


# ---------------------------------------------------------------------
# VALIDATION RESULT
# ---------------------------------------------------------------------


@dataclass
class ValidationCheck:
    """
    Represents the outcome of one dataset validation rule.

    name:
        Short identifier for the check.

    passed:
        True if the dataset satisfies the rule.

    details:
        Human-readable explanation of what was tested.
    """

    name: str
    passed: bool
    details: str


# ---------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------


def add_check(
    checks: list[ValidationCheck],
    name: str,
    passed: bool,
    details: str,
) -> None:
    """
    Add one validation result to the list.
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
    Verify that a dataframe contains all columns required by the
    research data model.
    """

    missing_columns = (
        required_columns
        - set(dataframe.columns)
    )

    passed = len(missing_columns) == 0

    add_check(
        checks=checks,
        name=f"{dataframe_name}_required_columns",
        passed=passed,
        details=(
            f"{dataframe_name}: "
            f"missing columns = {sorted(missing_columns)}"
        ),
    )


def check_unique_column(
    dataframe: pd.DataFrame,
    column: str,
    dataframe_name: str,
    checks: list[ValidationCheck],
) -> None:
    """
    Verify that an identifier column is unique.
    """

    duplicate_count = int(
        dataframe[column]
        .duplicated()
        .sum()
    )

    add_check(
        checks=checks,
        name=f"{dataframe_name}_{column}_unique",
        passed=duplicate_count == 0,
        details=(
            f"{dataframe_name}.{column}: "
            f"{duplicate_count} duplicate values"
        ),
    )


def check_required_nulls(
    dataframe: pd.DataFrame,
    required_columns: list[str],
    dataframe_name: str,
    checks: list[ValidationCheck],
) -> None:
    """
    Verify that required fields contain no missing values.

    We do NOT replace missing values with zero here.
    Missing and zero have different analytical meanings.
    """

    null_counts = (
        dataframe[required_columns]
        .isna()
        .sum()
    )

    total_nulls = int(
        null_counts.sum()
    )

    details = {
        column: int(count)
        for column, count
        in null_counts.items()
        if count > 0
    }

    add_check(
        checks=checks,
        name=f"{dataframe_name}_required_nulls",
        passed=total_nulls == 0,
        details=(
            f"{dataframe_name}: "
            f"missing required values = {details}"
        ),
    )


# ---------------------------------------------------------------------
# MAIN DATASET VALIDATION
# ---------------------------------------------------------------------


def validate_dataset(
    config: SimulationConfig,
    dealers: pd.DataFrame,
    dealer_truth: pd.DataFrame,
    leads: pd.DataFrame,
    applications: pd.DataFrame,
    sales: pd.DataFrame,
) -> list[ValidationCheck]:
    """
    Validate the complete synthetic dealer analytics dataset.

    The function checks:

    1. required columns
    2. unique identifiers
    3. missing required values
    4. country validity
    5. observation-window validity
    6. foreign-key integrity
    7. chronological consistency
    8. application-status validity
    9. sale eligibility
    10. dealer/country consistency
    11. hidden research-truth coverage

    No data is modified.
    """

    checks: list[ValidationCheck] = []

    # ================================================================
    # 1. REQUIRED COLUMNS
    # ================================================================

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

    # ================================================================
    # 2. UNIQUE PRIMARY IDENTIFIERS
    # ================================================================

    check_unique_column(
        dealers,
        "dealer_id",
        "dealers",
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

    # ================================================================
    # 3. REQUIRED VALUES MUST NOT BE NULL
    # ================================================================

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

    # ================================================================
    # 4. COUNTRY VALIDITY
    # ================================================================

    valid_countries = set(
        config.dealers_per_country.keys()
    )

    for name, dataframe in [
        ("dealers", dealers),
        ("leads", leads),
        ("applications", applications),
        ("sales", sales),
    ]:

        observed = set(
            dataframe["country"]
            .dropna()
            .unique()
        )

        invalid = (
            observed
            - valid_countries
        )

        add_check(
            checks=checks,
            name=f"{name}_valid_countries",
            passed=len(invalid) == 0,
            details=(
                f"{name}: "
                f"invalid countries = {sorted(invalid)}"
            ),
        )

    # ================================================================
    # 5. DATE WINDOW VALIDITY
    # ================================================================

    start_date = pd.Timestamp(
        config.start_date
    )

    end_date = pd.Timestamp(
        config.end_date
    )

    date_checks = [
        (
            "leads",
            leads,
            "lead_date",
        ),
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
    ]

    for name, dataframe, date_column in date_checks:

        dates = pd.to_datetime(
            dataframe[date_column],
            errors="coerce",
        )

        invalid_date_count = int(
            dates.isna().sum()
        )

        outside_window = int(
            (
                (dates < start_date)
                | (dates > end_date)
            ).sum()
        )

        add_check(
            checks=checks,
            name=f"{name}_valid_dates",
            passed=(
                invalid_date_count == 0
                and outside_window == 0
            ),
            details=(
                f"{name}.{date_column}: "
                f"{invalid_date_count} invalid dates, "
                f"{outside_window} outside research window"
            ),
        )

    # ================================================================
    # 6. FOREIGN-KEY INTEGRITY
    # ================================================================

    dealer_ids = set(
        dealers["dealer_id"]
    )

    lead_ids = set(
        leads["lead_id"]
    )

    application_ids = set(
        applications["application_id"]
    )

    # Every lead must belong to a valid dealer.
    invalid_lead_dealers = int(
        (~leads["dealer_id"].isin(dealer_ids))
        .sum()
    )

    add_check(
        checks=checks,
        name="leads_reference_existing_dealers",
        passed=invalid_lead_dealers == 0,
        details=(
            f"{invalid_lead_dealers} leads reference "
            f"non-existent dealers"
        ),
    )

    # Every application must reference an existing lead.
    orphan_applications = int(
        (
            ~applications["lead_id"]
            .isin(lead_ids)
        ).sum()
    )

    add_check(
        checks=checks,
        name="applications_reference_existing_leads",
        passed=orphan_applications == 0,
        details=(
            f"{orphan_applications} applications "
            f"reference missing leads"
        ),
    )

    # Every application must belong to a valid dealer.
    invalid_application_dealers = int(
        (
            ~applications["dealer_id"]
            .isin(dealer_ids)
        ).sum()
    )

    add_check(
        checks=checks,
        name="applications_reference_existing_dealers",
        passed=invalid_application_dealers == 0,
        details=(
            f"{invalid_application_dealers} applications "
            f"reference missing dealers"
        ),
    )

    # Every sale must reference an existing application.
    orphan_sales = int(
        (
            ~sales["application_id"]
            .isin(application_ids)
        ).sum()
    )

    add_check(
        checks=checks,
        name="sales_reference_existing_applications",
        passed=orphan_sales == 0,
        details=(
            f"{orphan_sales} sales reference "
            f"missing applications"
        ),
    )

    # Every sale must reference an existing lead.
    invalid_sale_leads = int(
        (
            ~sales["lead_id"]
            .isin(lead_ids)
        ).sum()
    )

    add_check(
        checks=checks,
        name="sales_reference_existing_leads",
        passed=invalid_sale_leads == 0,
        details=(
            f"{invalid_sale_leads} sales reference "
            f"missing leads"
        ),
    )

    # ================================================================
    # 7. APPLICATION STATUS VALIDITY
    # ================================================================

    valid_statuses = {
        "approved",
        "rejected",
    }

    observed_statuses = set(
        applications["status"]
        .dropna()
        .unique()
    )

    invalid_statuses = (
        observed_statuses
        - valid_statuses
    )

    add_check(
        checks=checks,
        name="application_status_validity",
        passed=len(invalid_statuses) == 0,
        details=(
            "Invalid statuses = "
            f"{sorted(invalid_statuses)}"
        ),
    )

    # ================================================================
    # 8. SALES MUST COME FROM APPROVED APPLICATIONS
    # ================================================================

    application_status_lookup = (
        applications
        .set_index("application_id")[
            "status"
        ]
    )

    sale_statuses = (
        sales["application_id"]
        .map(application_status_lookup)
    )

    sales_from_nonapproved = int(
        (
            sale_statuses != "approved"
        ).sum()
    )

    add_check(
        checks=checks,
        name="sales_only_from_approved_applications",
        passed=sales_from_nonapproved == 0,
        details=(
            f"{sales_from_nonapproved} sales came from "
            f"non-approved applications"
        ),
    )

    # ================================================================
    # 9. CHRONOLOGICAL CONSISTENCY
    # ================================================================

    # Build lookup tables.
    lead_date_lookup = (
        leads
        .set_index("lead_id")[
            "lead_date"
        ]
    )

    application_date_lookup = (
        applications
        .set_index("application_id")[
            "application_date"
        ]
    )

    # ---------------------------------------------------------------
    # Applications must occur on or after their associated lead.
    # ---------------------------------------------------------------

    app_lead_dates = pd.to_datetime(
        applications["lead_id"]
        .map(lead_date_lookup)
    )

    app_dates = pd.to_datetime(
        applications["application_date"]
    )

    application_before_lead = int(
        (
            app_dates < app_lead_dates
        ).sum()
    )

    add_check(
        checks=checks,
        name="application_after_lead",
        passed=application_before_lead == 0,
        details=(
            f"{application_before_lead} applications "
            f"occur before their associated lead"
        ),
    )

    # ---------------------------------------------------------------
    # Sales must occur on or after their associated application.
    # ---------------------------------------------------------------

    sale_application_dates = pd.to_datetime(
        sales["application_id"]
        .map(application_date_lookup)
    )

    sale_dates = pd.to_datetime(
        sales["sale_date"]
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
        passed=sale_before_application == 0,
        details=(
            f"{sale_before_application} sales "
            f"occur before their application"
        ),
    )

    # ================================================================
    # 10. DEALER AND COUNTRY CONSISTENCY
    # ================================================================

    dealer_country_lookup = (
        dealers
        .set_index("dealer_id")[
            "country"
        ]
    )

    for name, dataframe in [
        ("leads", leads),
        ("applications", applications),
        ("sales", sales),
    ]:

        expected_country = (
            dataframe["dealer_id"]
            .map(dealer_country_lookup)
        )

        mismatch_count = int(
            (
                dataframe["country"]
                != expected_country
            ).sum()
        )

        add_check(
            checks=checks,
            name=f"{name}_dealer_country_consistency",
            passed=mismatch_count == 0,
            details=(
                f"{mismatch_count} {name} rows have "
                f"a country inconsistent with the dealer"
            ),
        )

    # ================================================================
    # 11. APPLICATION MUST MATCH ITS ORIGINAL LEAD
    # ================================================================

    lead_dealer_lookup = (
        leads
        .set_index("lead_id")[
            "dealer_id"
        ]
    )

    expected_application_dealer = (
        applications["lead_id"]
        .map(lead_dealer_lookup)
    )

    application_dealer_mismatch = int(
        (
            applications["dealer_id"]
            != expected_application_dealer
        ).sum()
    )

    add_check(
        checks=checks,
        name="application_lead_dealer_consistency",
        passed=application_dealer_mismatch == 0,
        details=(
            f"{application_dealer_mismatch} applications "
            f"are assigned to a different dealer than "
            f"their originating lead"
        ),
    )

    # ================================================================
    # 12. SALES MUST MATCH THEIR APPLICATION AND LEAD
    # ================================================================

    app_lead_lookup = (
        applications
        .set_index("application_id")[
            "lead_id"
        ]
    )

    app_dealer_lookup = (
        applications
        .set_index("application_id")[
            "dealer_id"
        ]
    )

    expected_sale_lead = (
        sales["application_id"]
        .map(app_lead_lookup)
    )

    expected_sale_dealer = (
        sales["application_id"]
        .map(app_dealer_lookup)
    )

    sale_lead_mismatch = int(
        (
            sales["lead_id"]
            != expected_sale_lead
        ).sum()
    )

    sale_dealer_mismatch = int(
        (
            sales["dealer_id"]
            != expected_sale_dealer
        ).sum()
    )

    add_check(
        checks=checks,
        name="sale_application_lead_consistency",
        passed=sale_lead_mismatch == 0,
        details=(
            f"{sale_lead_mismatch} sales contain "
            f"an incorrect lead_id"
        ),
    )

    add_check(
        checks=checks,
        name="sale_application_dealer_consistency",
        passed=sale_dealer_mismatch == 0,
        details=(
            f"{sale_dealer_mismatch} sales contain "
            f"an incorrect dealer_id"
        ),
    )

    # ================================================================
    # 13. FUNNEL COUNT LOGIC
    # ================================================================

    number_of_leads = len(
        leads
    )

    number_of_applications = len(
        applications
    )

    number_of_approved = int(
        (
            applications["status"]
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
            f"Leads={number_of_leads:,}, "
            f"Applications={number_of_applications:,}, "
            f"Approved={number_of_approved:,}, "
            f"Sales={number_of_sales:,}"
        ),
    )

    # ================================================================
    # 14. SALE AMOUNT VALIDITY
    # ================================================================

    invalid_sale_amounts = int(
        (
            sales["sale_amount_usd"]
            <= 0
        ).sum()
    )

    add_check(
        checks=checks,
        name="positive_sale_amounts",
        passed=invalid_sale_amounts == 0,
        details=(
            f"{invalid_sale_amounts} sales "
            f"have non-positive amounts"
        ),
    )

    # ================================================================
    # 15. HIDDEN DEALER TRUTH COVERAGE
    # ================================================================

    visible_dealer_ids = set(
        dealers["dealer_id"]
    )

    truth_dealer_ids = set(
        dealer_truth["dealer_id"]
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
        len(missing_truth) == 0
        and len(extra_truth) == 0
    )

    add_check(
        checks=checks,
        name="dealer_truth_matches_dealers",
        passed=truth_matches,
        details=(
            f"Missing truth records={len(missing_truth)}, "
            f"extra truth records={len(extra_truth)}"
        ),
    )

    # ================================================================
    # 16. HIDDEN PROBABILITY PARAMETER VALIDITY
    # ================================================================

    probability_columns = [
        "application_rate",
        "approval_rate",
        "sale_conversion_rate",
    ]

    invalid_probability_count = 0

    for column in probability_columns:

        invalid_probability_count += int(
            (
                (dealer_truth[column] < 0)
                | (dealer_truth[column] > 1)
            ).sum()
        )

    add_check(
        checks=checks,
        name="hidden_probabilities_valid",
        passed=invalid_probability_count == 0,
        details=(
            f"{invalid_probability_count} hidden "
            f"probability values fall outside [0, 1]"
        ),
    )

    return checks


# ---------------------------------------------------------------------
# REPORTING
# ---------------------------------------------------------------------


def print_validation_report(
    checks: list[ValidationCheck],
) -> None:
    """
    Print validation results in a readable terminal format.
    """

    print("\n" + "=" * 70)
    print("DATASET VALIDATION REPORT")
    print("=" * 70)

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
            f"[{status}] {check.name}"
        )

        print(
            f"       {check.details}"
        )

    total_checks = len(checks)

    failed_count = (
        total_checks
        - passed_count
    )

    print("\n" + "-" * 70)

    print(
        f"Passed: {passed_count}/{total_checks}"
    )

    print(
        f"Failed: {failed_count}/{total_checks}"
    )

    print("-" * 70)

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

    This creates an auditable record of dataset validation.
    """

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    report = {
        "total_checks": len(checks),
        "passed_checks": sum(
            check.passed
            for check in checks
        ),
        "failed_checks": sum(
            not check.passed
            for check in checks
        ),
        "checks": [
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
    Raise an exception if any validation rule fails.

    This prevents later parts of the research pipeline from accidentally
    continuing with structurally invalid data.
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
            f"Failed checks: {failed_names}"
        )