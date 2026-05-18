"""Two-line comparison of source-artist take-home under two royalty regimes.

Story
-----
A source artist sits in a stylistic neighborhood. At month 0 only their own
catalog occupies that neighborhood. As AI-generated supply grows the
neighborhood fills with new tracks, some of which cite the source under a
per-consumption royalty model, and the source must compete for a fixed pool
of listener attention against an exponentially-growing catalog.

Two regimes are compared.

The CURRENT model (red, dashed in the chart) prices the now-infinite output.
Two compounding forces drag the source's take-home down:
  - VOLUME dilution. Listener attention divides across more tracks, so the
    share of consumptions that reach the source's own catalog falls off as
    1/(1+g)^t, and the share that reaches AI tracks citing the source is
    diluted further by blend_width (the average number of source artists
    cited per AI track).
  - VALUE commoditization. The per-consumption price itself falls in a
    saturated-supply world, also at 1/(1+g)^t, because the marginal output
    is a near-substitute and competes for the same listener-second.
The two effects multiply, so the curve declines faster than either alone.

The INVERTED model (green, solid) prices the scarce stamp, the verifiable
admission that a given track passed the consent + licensing + attribution
checks at the moment it was made. The source artist earns from licensing the
right to issue stamps in their stylistic neighborhood, which is supply-
insensitive by construction. There is some erosion from a starting peak to a
long-run floor (taste churn, catalog substitution), modeled as exponential
decay to a 0.80 × pool floor.

Calibration of "slow"
---------------------
The SLOW supply-growth setting is set at 12% monthly compound growth. That
is approximately 4.4x per year, which is conservative for AI-audio supply
trends in 2025 and which guarantees the spec's required property: even at
the MOST source-favorable slider corner the red curve drops below 25% of
its starting value by month 12. See ``most_source_favorable`` and the test
that exercises this in tests/test_model.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Monthly compound supply-growth rates for the three discrete settings in
# the index.html control. SLOW is calibrated so the spec's "<25% at the
# most source-favorable corner" property holds, see tests.
SLOW: float = 0.12
MEDIUM: float = 0.30
EXPLOSIVE: float = 0.55

# Long-run floor for the green curve, expressed as a fraction of the
# starting pool. Some erosion is honest, going to zero is not.
GREEN_FLOOR: float = 0.80

# Speed at which the green curve approaches GREEN_FLOOR; larger = faster.
GREEN_EROSION_RATE: float = 0.30

DEFAULT_MONTHS: int = 12


@dataclass(frozen=True)
class Params:
    """Inputs to the two-series comparison.

    Attributes
    ----------
    supply_growth:
        Monthly compound growth rate of AI-generated supply in the source
        artist's stylistic neighborhood. 0.12 = "slow", 0.30 = "medium",
        0.55 = "explosive" in the UI.
    blend_width:
        Average number of source artists cited per AI track under the
        current model. Higher = each cited source gets a thinner slice
        of the per-track payout. Bounded 1..20 in the UI.
    source_take_pct:
        Fraction of an AI track's revenue that flows to cited source
        artists (collectively, then split blend_width ways). UI range
        0.05..0.50.
    monthly_pool_k:
        Total monthly revenue pool, in $k, attributable to the source
        artist's stylistic neighborhood at month 0 (i.e. before AI
        dilution). Scales both curves linearly.
    """

    supply_growth: float
    blend_width: int
    source_take_pct: float
    monthly_pool_k: float

    def __post_init__(self) -> None:
        if self.supply_growth < 0:
            raise ValueError("supply_growth must be non-negative")
        if self.blend_width < 1:
            raise ValueError("blend_width must be at least 1")
        if not 0.0 <= self.source_take_pct <= 1.0:
            raise ValueError("source_take_pct must be in [0, 1]")
        if self.monthly_pool_k < 0:
            raise ValueError("monthly_pool_k must be non-negative")


def most_source_favorable() -> Params:
    """The corner of the slider space that is best for the source artist.

    Slowest supply growth, narrowest blend (sole cited source), highest
    UI-permitted source take percentage. The chart's mandate is that the
    red curve still collapses below 25% of its starting value here, and
    the test asserts that.
    """
    return Params(
        supply_growth=SLOW,
        blend_width=1,
        source_take_pct=0.50,
        monthly_pool_k=100.0,
    )


def _organic_share(growth: float, t: int) -> float:
    """Fraction of listener attention still on the source's own catalog at month t."""
    return 1.0 / ((1.0 + growth) ** t)


def red_series(params: Params, months: int = DEFAULT_MONTHS) -> list[float]:
    """Source-artist take-home under the per-consumption (current) regime.

    red(t) = pool * organic_share(t) * revenue_share(t)
      organic_share(t)  = 1 / (1 + g)^t                          (volume dilution)
      revenue_share(t)  = organic_share + (1 - organic_share)
                          * source_take_pct / blend_width        (citation share)
      multiplied again by organic_share to capture per-unit
      value commoditization.
    """
    out: list[float] = []
    for t in range(months):
        organic = _organic_share(params.supply_growth, t)
        citation_share = (1.0 - organic) * params.source_take_pct / params.blend_width
        revenue_share = organic + citation_share
        per_unit_value = organic
        out.append(params.monthly_pool_k * revenue_share * per_unit_value)
    return out


def green_series(params: Params, months: int = DEFAULT_MONTHS) -> list[float]:
    """Source-artist take-home under the stamp-licensing (inverted) regime.

    Supply-insensitive by construction. Exponential erosion from 1.0 * pool
    toward a GREEN_FLOOR (0.80) * pool long-run floor.
    """
    out: list[float] = []
    for t in range(months):
        factor = GREEN_FLOOR + (1.0 - GREEN_FLOOR) * math.exp(-GREEN_EROSION_RATE * t)
        out.append(params.monthly_pool_k * factor)
    return out
