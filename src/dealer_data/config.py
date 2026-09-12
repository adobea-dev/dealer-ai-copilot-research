from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SimulationConfig:
    """Configuration for the synthetic dealer analytics dataset."""

    seed: int = 42
    generator_version: str = "2.0.0"

    start_date: str = "2024-01-01"
    end_date: str = "2025-12-31"

    dealers_per_country: dict[str, int] = field(
        default_factory=lambda: {
            "GH": 30,
            "NG": 40,
            "KE": 30,
            "UG": 25,
        }
    )

    cities: dict[str, list[str]] = field(
        default_factory=lambda: {
            "GH": ["Accra", "Kumasi", "Tema", "Takoradi"],
            "NG": ["Lagos", "Abuja", "Port Harcourt", "Ibadan"],
            "KE": ["Nairobi", "Mombasa", "Kisumu", "Nakuru"],
            "UG": ["Kampala", "Entebbe", "Jinja", "Mbarara"],
        }
    )

    # Simulation parameters only; not empirical claims about these countries.
    country_demand_factor: dict[str, float] = field(
        default_factory=lambda: {
            "GH": 1.00,
            "NG": 1.08,
            "KE": 1.03,
            "UG": 0.95,
        }
    )

    output_dir: Path = Path("data/generated/v2")
    truth_dir: Path = Path("data/research_truth/v2")
    metadata_dir: Path = Path("metadata")


CONFIG = SimulationConfig()