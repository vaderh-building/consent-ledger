"""Tests for the compensation model that drives the chart in index.html.

The mandatory property test is
``test_red_collapses_below_25pct_at_most_source_favorable_corner`` —
the spec requires that even when every slider is set to its most
source-favorable value, the red (current-model) curve falls under 25%
of its starting value by month 12.
"""

from __future__ import annotations

import math

import pytest

from model import (
    EXPLOSIVE,
    MEDIUM,
    SLOW,
    Params,
    green_series,
    most_source_favorable,
    red_series,
)


@pytest.fixture
def default_params() -> Params:
    return Params(
        supply_growth=MEDIUM,
        blend_width=4,
        source_take_pct=0.20,
        monthly_pool_k=100.0,
    )


# ---------- shape and bounds ----------


def test_both_series_start_at_pool(default_params: Params) -> None:
    red = red_series(default_params)
    green = green_series(default_params)
    assert math.isclose(red[0], default_params.monthly_pool_k, rel_tol=1e-9)
    assert math.isclose(green[0], default_params.monthly_pool_k, rel_tol=1e-9)


def test_red_is_monotonically_non_increasing(default_params: Params) -> None:
    red = red_series(default_params)
    for earlier, later in zip(red, red[1:], strict=False):
        assert later <= earlier + 1e-9


def test_green_is_monotonically_non_increasing(default_params: Params) -> None:
    green = green_series(default_params)
    for earlier, later in zip(green, green[1:], strict=False):
        assert later <= earlier + 1e-9


def test_green_does_not_fall_below_its_floor(default_params: Params) -> None:
    green = green_series(default_params, months=24)
    floor = 0.80 * default_params.monthly_pool_k
    for v in green:
        assert v >= floor - 1e-9


def test_length_of_series_matches_months_arg(default_params: Params) -> None:
    assert len(red_series(default_params, months=7)) == 7
    assert len(green_series(default_params, months=7)) == 7
    assert len(red_series(default_params, months=18)) == 18


# ---------- the load-bearing property ----------


def test_red_collapses_below_25pct_at_most_source_favorable_corner() -> None:
    """The chart's promise. Even at the corner most favorable to the source,
    the per-consumption regime drops below 25% of its starting value within
    12 months. This MUST hold; if it ever fails, the chart's argument is
    false and the page is misleading."""
    params = most_source_favorable()
    red = red_series(params)
    starting = red[0]
    final = red[-1]
    assert starting > 0
    assert final / starting < 0.25, (
        f"red final/starting = {final / starting:.4f}; spec requires < 0.25 even at "
        f"the most source-favorable corner (slow growth, blend=1, source_take=0.50)."
    )


def test_red_is_steeper_at_higher_supply_growth() -> None:
    base = Params(
        supply_growth=SLOW, blend_width=4, source_take_pct=0.20, monthly_pool_k=100.0
    )
    hot = Params(
        supply_growth=EXPLOSIVE, blend_width=4, source_take_pct=0.20, monthly_pool_k=100.0
    )
    slow_red = red_series(base)
    fast_red = red_series(hot)
    assert fast_red[-1] < slow_red[-1]


# ---------- green is supply-insensitive (its whole point) ----------


def test_green_is_insensitive_to_supply_growth() -> None:
    """A point of the inverted model is that the stamp's economics do not
    move with AI supply. We don't require strict equality across growth
    rates (we may want to add taste-churn coupling later) but we do
    require near-equality of the present implementation."""
    args = dict(blend_width=4, source_take_pct=0.20, monthly_pool_k=100.0)
    slow = green_series(Params(supply_growth=SLOW, **args))
    fast = green_series(Params(supply_growth=EXPLOSIVE, **args))
    for a, b in zip(slow, fast, strict=True):
        assert math.isclose(a, b, rel_tol=1e-9)


def test_green_is_insensitive_to_blend_and_source_take() -> None:
    args = dict(supply_growth=MEDIUM, monthly_pool_k=100.0)
    narrow = green_series(Params(blend_width=1, source_take_pct=0.50, **args))
    wide = green_series(Params(blend_width=20, source_take_pct=0.05, **args))
    for a, b in zip(narrow, wide, strict=True):
        assert math.isclose(a, b, rel_tol=1e-9)


# ---------- pool scaling ----------


def test_pool_scales_both_curves_linearly() -> None:
    p100 = Params(
        supply_growth=MEDIUM, blend_width=4, source_take_pct=0.20, monthly_pool_k=100.0
    )
    p200 = Params(
        supply_growth=MEDIUM, blend_width=4, source_take_pct=0.20, monthly_pool_k=200.0
    )
    for r1, r2 in zip(red_series(p100), red_series(p200), strict=True):
        assert math.isclose(r2, 2 * r1, rel_tol=1e-9)
    for g1, g2 in zip(green_series(p100), green_series(p200), strict=True):
        assert math.isclose(g2, 2 * g1, rel_tol=1e-9)


# ---------- validation ----------


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(supply_growth=-0.1, blend_width=1, source_take_pct=0.2, monthly_pool_k=100.0),
        dict(supply_growth=0.1, blend_width=0, source_take_pct=0.2, monthly_pool_k=100.0),
        dict(supply_growth=0.1, blend_width=1, source_take_pct=-0.1, monthly_pool_k=100.0),
        dict(supply_growth=0.1, blend_width=1, source_take_pct=1.5, monthly_pool_k=100.0),
        dict(supply_growth=0.1, blend_width=1, source_take_pct=0.2, monthly_pool_k=-1.0),
    ],
)
def test_params_validates_inputs(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        Params(**kwargs)
