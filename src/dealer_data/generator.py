from __future__ import annotations

import math
import uuid

import numpy as np
import pandas as pd

from .config import SimulationConfig


NAMESPACE = uuid.UUID("2c4a3854-aead-4df1-881e-cfa6576a321b")


def deterministic_uuid(value: str) -> str:
    """Generate reproducible UUIDs from a stable input string."""
    return str(uuid.uuid5(NAMESPACE, value))


def sigmoid(x: float) -> float:
    """Convert a real-valued score into a probability between 0 and 1."""
    return 1.0 / (1.0 + math.exp(-x))

def generate_dealers(
    config: SimulationConfig,
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Generate visible dealer records and hidden dealer-level simulation truth.

    Returns
    -------
    dealers:
        Dealer attributes available to the experimental systems.

    dealer_truth:
        Hidden latent parameters used only for simulation and research validation.
        These values must not be loaded into the experimental database.
    """

    dealer_rows: list[dict] = []
    truth_rows: list[dict] = []

    for country, n_dealers in config.dealers_per_country.items():
        for index in range(n_dealers):
            dealer_id = deterministic_uuid(
                f"dealer:{country}:{index:03d}"
            )

            city = rng.choice(config.cities[country])

            # Latent dealer capability. This is hidden from the AI systems.
            quality = float(rng.normal(0.0, 1.0))

            # Independent noise prevents dealer performance from becoming
            # a perfectly ordered reflection of latent quality.
            lead_noise = float(rng.normal(0.0, 0.30))
            app_noise = float(rng.normal(0.0, 0.35))
            approval_noise = float(rng.normal(0.0, 0.30))
            sales_noise = float(rng.normal(0.0, 0.35))

            base_monthly_leads = float(
                np.exp(
                    math.log(25)
                    + 0.35 * quality
                    + lead_noise
                )
            )

            application_rate = sigmoid(
                -0.95
                + 0.30 * quality
                + app_noise
            )

            approval_rate = sigmoid(
                0.60
                + 0.25 * quality
                + approval_noise
            )

            sale_conversion_rate = sigmoid(
                0.15
                + 0.30 * quality
                + sales_noise
            )

            monthly_trend = float(
                rng.normal(0.0, 0.006)
            )

            dealer_rows.append(
                {
                    "dealer_id": dealer_id,
                    "dealer_name": f"{country}-Dealer-{index + 1:03d}",
                    "country": country,
                    "city": city,
                    "active": True,
                }
            )

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

if __name__ == "__main__":
    from .config import CONFIG

    rng = np.random.default_rng(CONFIG.seed)

    dealers, dealer_truth = generate_dealers(
        config=CONFIG,
        rng=rng,
    )

    print(dealers.head())
    print()
    print(dealer_truth.head())
    print()
    print(f"Dealers: {len(dealers)}")