from datetime import date

from info.market_data.service import _compute_gaps


RANGE_START = date(2024, 1, 1)
RANGE_END = date(2024, 1, 31)


def test_empty_db_returns_full_range():
    gaps = _compute_gaps(set(), RANGE_START, RANGE_END, back_gap_allowed=True)
    assert gaps == [(RANGE_START, RANGE_END)]


def test_empty_db_ignores_freshness():
    # Even if fresh, an empty DB must be fully populated.
    gaps = _compute_gaps(set(), RANGE_START, RANGE_END, back_gap_allowed=False)
    assert gaps == [(RANGE_START, RANGE_END)]


def test_full_coverage_no_gaps():
    existing = {date(2024, 1, 1), date(2024, 1, 15), date(2024, 1, 31)}
    gaps = _compute_gaps(existing, RANGE_START, RANGE_END, back_gap_allowed=True)
    assert gaps == []


def test_front_gap_only():
    existing = {date(2024, 1, 10), date(2024, 1, 31)}
    gaps = _compute_gaps(existing, RANGE_START, RANGE_END, back_gap_allowed=True)
    assert gaps == [(date(2024, 1, 1), date(2024, 1, 9))]


def test_back_gap_only_when_allowed():
    existing = {date(2024, 1, 1), date(2024, 1, 20)}
    gaps = _compute_gaps(existing, RANGE_START, RANGE_END, back_gap_allowed=True)
    assert gaps == [(date(2024, 1, 21), date(2024, 1, 31))]


def test_back_gap_suppressed_when_fresh():
    existing = {date(2024, 1, 1), date(2024, 1, 20)}
    gaps = _compute_gaps(existing, RANGE_START, RANGE_END, back_gap_allowed=False)
    assert gaps == []


def test_both_front_and_back_gaps():
    existing = {date(2024, 1, 10), date(2024, 1, 20)}
    gaps = _compute_gaps(existing, RANGE_START, RANGE_END, back_gap_allowed=True)
    assert gaps == [
        (date(2024, 1, 1), date(2024, 1, 9)),
        (date(2024, 1, 21), date(2024, 1, 31)),
    ]


def test_front_gap_still_filled_when_fresh():
    # Freshness only gates back-gap; front-gap (historical data) is always attempted.
    existing = {date(2024, 1, 10), date(2024, 1, 31)}
    gaps = _compute_gaps(existing, RANGE_START, RANGE_END, back_gap_allowed=False)
    assert gaps == [(date(2024, 1, 1), date(2024, 1, 9))]


def test_middle_gaps_not_filled():
    # The implementation treats DB contents as contiguous between min and max —
    # missing weekends/holidays in the middle are NOT treated as gaps.
    existing = {date(2024, 1, 1), date(2024, 1, 31)}
    gaps = _compute_gaps(existing, RANGE_START, RANGE_END, back_gap_allowed=True)
    assert gaps == []
