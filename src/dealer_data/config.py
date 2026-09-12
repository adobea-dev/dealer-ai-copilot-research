from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SimulationConfig:
    """
    Central configuration for the Dealer AI Copilot synthetic dataset.

    Keeping simulation parameters in one location makes the experiment
    easier to reproduce, document, and modify systematically.
    """

    # -----------------------------------------------------------------
    # REPRODUCIBILITY
    # -----------------------------------------------------------------

    # Fixed seed ensures that running the generator with the same code
    # and configuration produces the same synthetic dataset.
    seed: int = 42

    # Internal version of the data-generating process.
    generator_version: str = "2.1.0"

    # -----------------------------------------------------------------
    # TEMPORAL DESIGN
    # -----------------------------------------------------------------

    # Beginning of the main research observation period.
    start_date: str = "2024-01-01"

    # End of the period that users and AI systems are primarily expected
    # to analyse.
    #
    # New leads are generated only up to this date.
    analysis_end_date: str = "2025-12-31"

    # Additional observation period used only to allow late-December
    # leads to mature into applications and sales.
    #
    # For example:
    #
    # Lead:        2025-12-29
    # Application: 2026-01-05
    # Sale:        2026-01-20
    #
    # Without this buffer, late-December leads would appear artificially
    # less successful because downstream events would be discarded.
    simulation_end_date: str = "2026-01-31"

    # -----------------------------------------------------------------
    # DEALER POPULATION
    # -----------------------------------------------------------------

    dealers_per_country: dict[str, int] = field(
        default_factory=lambda: {
            "GH": 30,
            "NG": 40,
            "KE": 30,
            "UG": 25,
        }
    )

    # Synthetic dealer locations.
    cities: dict[str, list[str]] = field(
        default_factory=lambda: {
            "GH": [
                "Accra",
                "Kumasi",
                "Tema",
                "Takoradi",
            ],
            "NG": [
                "Lagos",
                "Abuja",
                "Port Harcourt",
                "Ibadan",
            ],
            "KE": [
                "Nairobi",
                "Mombasa",
                "Kisumu",
                "Nakuru",
            ],
            "UG": [
                "Kampala",
                "Entebbe",
                "Jinja",
                "Mbarara",
            ],
        }
    )

    # -----------------------------------------------------------------
    # COUNTRY-LEVEL SIMULATION PARAMETERS
    # -----------------------------------------------------------------

    # These values are SIMULATION CONTROLS ONLY.
    #
    # They are not empirical claims about automotive demand in these
    # countries.
    #
    # Their purpose is simply to create mild geographic heterogeneity.
    country_demand_factor: dict[str, float] = field(
        default_factory=lambda: {
            "GH": 1.00,
            "NG": 1.08,
            "KE": 1.03,
            "UG": 0.95,
        }
    )

    # -----------------------------------------------------------------
    # OUTPUT LOCATIONS
    # -----------------------------------------------------------------

    # Visible data that may eventually be loaded into PostgreSQL.
    output_dir: Path = Path(
        "data/generated/v2"
    )

    # Hidden simulation parameters available only to the researcher.
    truth_dir: Path = Path(
        "data/research_truth/v2"
    )

    # Metadata describing how the dataset was generated.
    metadata_dir: Path = Path(
        "metadata"
    )


# Shared configuration instance used throughout the project.
CONFIG = SimulationConfig()