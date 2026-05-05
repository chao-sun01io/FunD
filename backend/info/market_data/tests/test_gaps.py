from datetime import date
from decimal import Decimal

from info.market_data.base import OHLCVBar
from info.market_data.service import (
    _collapse_dates,
    _compute_gaps,
    _incomplete_dates,
)


RANGE_START = date(2024, 1, 1)
RANGE_END = date(2024, 1, 31)


def _complete_bar(d: date) -> OHLCVBar:
    """A bar with all fields populated."""
    return OHLCVBar(
        date=d,
        open=Decimal('10'),
        high=Decimal('11'),
        low=Decimal('9'),
        close=Decimal('10.5'),
        volume=1000,
        nav=Decimal('1.05'),
    )


def _bars(*dates: date) -> list[OHLCVBar]:
    return [_complete_bar(d) for d in dates]


# --- _compute_gaps: edge gaps -------------------------------------------------

def test_empty_db_returns_full_range():
    gaps = _compute_gaps([], RANGE_START, RANGE_END, back_gap_allowed=True)
    assert gaps == [(RANGE_START, RANGE_END)]


def test_empty_db_ignores_freshness():
    # Even if fresh, an empty DB must be fully populated.
    gaps = _compute_gaps([], RANGE_START, RANGE_END, back_gap_allowed=False)
    assert gaps == [(RANGE_START, RANGE_END)]


def test_full_coverage_no_gaps():
    bars = _bars(date(2024, 1, 1), date(2024, 1, 15), date(2024, 1, 31))
    gaps = _compute_gaps(bars, RANGE_START, RANGE_END, back_gap_allowed=True)
    assert gaps == []


def test_front_gap_only():
    bars = _bars(date(2024, 1, 10), date(2024, 1, 31))
    gaps = _compute_gaps(bars, RANGE_START, RANGE_END, back_gap_allowed=True)
    assert gaps == [(date(2024, 1, 1), date(2024, 1, 9))]


def test_back_gap_only_when_allowed():
    bars = _bars(date(2024, 1, 1), date(2024, 1, 20))
    gaps = _compute_gaps(bars, RANGE_START, RANGE_END, back_gap_allowed=True)
    assert gaps == [(date(2024, 1, 21), date(2024, 1, 31))]


def test_back_gap_suppressed_when_fresh():
    bars = _bars(date(2024, 1, 1), date(2024, 1, 20))
    gaps = _compute_gaps(bars, RANGE_START, RANGE_END, back_gap_allowed=False)
    assert gaps == []


def test_both_front_and_back_gaps():
    bars = _bars(date(2024, 1, 10), date(2024, 1, 20))
    gaps = _compute_gaps(bars, RANGE_START, RANGE_END, back_gap_allowed=True)
    assert gaps == [
        (date(2024, 1, 1), date(2024, 1, 9)),
        (date(2024, 1, 21), date(2024, 1, 31)),
    ]


def test_front_gap_still_filled_when_fresh():
    # Freshness only gates back-gap and incomplete rows; front gap (historical
    # backfill) is always attempted.
    bars = _bars(date(2024, 1, 10), date(2024, 1, 31))
    gaps = _compute_gaps(bars, RANGE_START, RANGE_END, back_gap_allowed=False)
    assert gaps == [(date(2024, 1, 1), date(2024, 1, 9))]


def test_middle_dates_with_complete_bars_are_not_gaps():
    # Dates between db_min and db_max with complete data → not a gap.
    bars = _bars(date(2024, 1, 1), date(2024, 1, 31))
    gaps = _compute_gaps(bars, RANGE_START, RANGE_END, back_gap_allowed=True)
    assert gaps == []


# --- _compute_gaps: incomplete rows -------------------------------------------

def test_incomplete_row_inside_range_becomes_gap():
    bars = [
        _complete_bar(date(2024, 1, 1)),
        OHLCVBar(date=date(2024, 1, 15), open=Decimal('10'), close=None,
                 high=Decimal('11'), low=Decimal('9'), volume=1000, nav=Decimal('1.0')),
        _complete_bar(date(2024, 1, 31)),
    ]
    gaps = _compute_gaps(bars, RANGE_START, RANGE_END, back_gap_allowed=True)
    assert gaps == [(date(2024, 1, 15), date(2024, 1, 15))]


def test_incomplete_row_suppressed_when_fresh():
    # Incomplete rows are gated on freshness, same as back gap.
    bars = [
        _complete_bar(date(2024, 1, 1)),
        OHLCVBar(date=date(2024, 1, 15), nav=None, open=Decimal('10'),
                 close=Decimal('10'), high=Decimal('11'), low=Decimal('9'), volume=1000),
        _complete_bar(date(2024, 1, 31)),
    ]
    gaps = _compute_gaps(bars, RANGE_START, RANGE_END, back_gap_allowed=False)
    assert gaps == []


def test_consecutive_incomplete_rows_collapse_into_one_range():
    bars = [
        _complete_bar(date(2024, 1, 1)),
        OHLCVBar(date=date(2024, 1, 10), nav=None),
        OHLCVBar(date=date(2024, 1, 11), nav=None),
        OHLCVBar(date=date(2024, 1, 12), nav=None),
        _complete_bar(date(2024, 1, 31)),
    ]
    gaps = _compute_gaps(bars, RANGE_START, RANGE_END, back_gap_allowed=True)
    assert gaps == [(date(2024, 1, 10), date(2024, 1, 12))]


def test_far_apart_incomplete_rows_stay_separate():
    bars = [
        _complete_bar(date(2024, 1, 1)),
        OHLCVBar(date=date(2024, 1, 10), nav=None),
        OHLCVBar(date=date(2024, 1, 25), volume=None),
        _complete_bar(date(2024, 1, 31)),
    ]
    gaps = _compute_gaps(bars, RANGE_START, RANGE_END, back_gap_allowed=True)
    assert gaps == [
        (date(2024, 1, 10), date(2024, 1, 10)),
        (date(2024, 1, 25), date(2024, 1, 25)),
    ]


def test_incomplete_rows_combined_with_edge_gaps():
    bars = [
        OHLCVBar(date=date(2024, 1, 10), close=None),  # incomplete
        _complete_bar(date(2024, 1, 20)),
    ]
    gaps = _compute_gaps(bars, RANGE_START, RANGE_END, back_gap_allowed=True)
    # Front gap + incomplete + back gap
    assert gaps == [
        (date(2024, 1, 1), date(2024, 1, 9)),
        (date(2024, 1, 10), date(2024, 1, 10)),
        (date(2024, 1, 21), date(2024, 1, 31)),
    ]


# --- _incomplete_dates --------------------------------------------------------

def test_incomplete_dates_empty_for_complete_bars():
    bars = _bars(date(2024, 1, 1), date(2024, 1, 2))
    assert _incomplete_dates(bars) == []


def test_incomplete_dates_detects_each_field():
    fields = ['open', 'high', 'low', 'close', 'volume', 'nav']
    for f in fields:
        bar = _complete_bar(date(2024, 1, 1))
        setattr(bar, f, None)
        assert _incomplete_dates([bar]) == [date(2024, 1, 1)], f"failed for field={f}"


# --- _collapse_dates ----------------------------------------------------------

def test_collapse_dates_empty():
    assert _collapse_dates([]) == []


def test_collapse_dates_single():
    assert _collapse_dates([date(2024, 1, 5)]) == [(date(2024, 1, 5), date(2024, 1, 5))]


def test_collapse_dates_within_tolerance_merges():
    # Default tolerance is 5 days — bridges weekends.
    dates = [date(2024, 1, 1), date(2024, 1, 5), date(2024, 1, 10)]
    assert _collapse_dates(dates) == [(date(2024, 1, 1), date(2024, 1, 10))]


def test_collapse_dates_beyond_tolerance_splits():
    dates = [date(2024, 1, 1), date(2024, 1, 10)]  # 9-day gap > 5
    assert _collapse_dates(dates) == [
        (date(2024, 1, 1), date(2024, 1, 1)),
        (date(2024, 1, 10), date(2024, 1, 10)),
    ]


def test_collapse_dates_custom_tolerance():
    dates = [date(2024, 1, 1), date(2024, 1, 3)]
    assert _collapse_dates(dates, tolerance_days=1) == [
        (date(2024, 1, 1), date(2024, 1, 1)),
        (date(2024, 1, 3), date(2024, 1, 3)),
    ]
