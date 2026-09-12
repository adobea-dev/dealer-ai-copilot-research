from __future__ import annotations

import pandas as pd

from src.dealer_data.config import CONFIG
from src.dealer_data.validation import (
    assert_validation_passed,
    print_validation_report,
    save_validation_report,
    validate_dataset,
)


def main() -> None:
    """
    Load the generated dataset and run all structural validation checks.
    """

    # ---------------------------------------------------------------
    # LOAD VISIBLE DATA
    # ---------------------------------------------------------------

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

    # ---------------------------------------------------------------
    # LOAD HIDDEN RESEARCH TRUTH
    # ---------------------------------------------------------------

    dealer_truth = pd.read_csv(
        CONFIG.truth_dir
        / "dealer_latent_truth.csv"
    )

    # ---------------------------------------------------------------
    # RUN VALIDATION
    # ---------------------------------------------------------------

    checks = validate_dataset(
        config=CONFIG,
        dealers=dealers,
        dealer_truth=dealer_truth,
        leads=leads,
        applications=applications,
        sales=sales,
    )

    # Show results in terminal.
    print_validation_report(
        checks
    )

    # Save the results so we have an auditable validation artifact.
    save_validation_report(
        checks=checks,
        output_path=(
            CONFIG.output_dir.parent.parent
            / "reports"
            / "dataset_v2_validation.json"
        ),
    )

    # Stop execution if anything failed.
    assert_validation_passed(
        checks
    )


if __name__ == "__main__":
    main()