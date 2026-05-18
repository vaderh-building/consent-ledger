"""Compensation comparison model.

The two-line chart on index.html is computed from this module. The JS in the
page reimplements the same arithmetic for live sliders, but THIS file is the
reference. If the JS and Python ever disagree, the JS is wrong.
"""

from .compensation import (
    EXPLOSIVE,
    MEDIUM,
    SLOW,
    Params,
    green_series,
    most_source_favorable,
    red_series,
)

__all__ = [
    "EXPLOSIVE",
    "MEDIUM",
    "Params",
    "SLOW",
    "green_series",
    "most_source_favorable",
    "red_series",
]
