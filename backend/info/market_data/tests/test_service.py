from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from info.market_data import service as service_module
from info.market_data.base import NAVPoint, OHLCVBar, ProviderError
from info.market_data.service import (
    HistoricalDataService,
    IncompleteReport,
    _bar_to_dict,
    _merge_nav,
)


def _make_bars() -> list[OHLCVBar]:
    return [
        OHLCVBar(date=date(2024, 1, 2), open=Decimal('10.00'), close=Decimal('10.10'),
                 high=Decimal('10.20'), low=Decimal('9.95'), volume=1000),
        OHLCVBar(date=date(2024, 1, 3), open=Decimal('10.10'), close=Decimal('10.25'),
                 high=Decimal('10.30'), low=Decimal('10.05'), volume=1200),
    ]


class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value

    def exists(self, key):
        return 1 if key in self.store else 0


# ---------- Pure-function tests (no DB, no mocks) ----------


def test_merge_nav_attaches_by_date():
    bars = _make_bars()
    nav_points = [
        NAVPoint(date=date(2024, 1, 2), nav=Decimal('1.2345')),
        NAVPoint(date=date(2024, 1, 3), nav=Decimal('1.2400')),
    ]
    _merge_nav(bars, nav_points)
    assert bars[0].nav == Decimal('1.2345')
    assert bars[1].nav == Decimal('1.2400')


def test_merge_nav_partial_coverage():
    bars = _make_bars()
    nav_points = [NAVPoint(date=date(2024, 1, 3), nav=Decimal('1.2400'))]
    _merge_nav(bars, nav_points)
    assert bars[0].nav is None
    assert bars[1].nav == Decimal('1.2400')


def test_merge_nav_empty_is_noop():
    bars = _make_bars()
    _merge_nav(bars, [])
    assert all(bar.nav is None for bar in bars)


def test_bar_to_dict_includes_nav():
    bar = OHLCVBar(date=date(2024, 1, 2), close=Decimal('10.10'), nav=Decimal('1.2345'))
    d = _bar_to_dict(bar)
    assert d['nav'] == 1.2345
    assert d['close'] == 10.10


def test_bar_to_dict_null_nav():
    bar = OHLCVBar(date=date(2024, 1, 2), close=Decimal('10.10'))
    d = _bar_to_dict(bar)
    assert d['nav'] is None


# ---------- HistoricalDataService.get_history ----------
#
# The service flow looks up FundBasicInfo directly. To keep these as pure unit
# tests (no DB), we patch the lazy import target `info.models.FundBasicInfo.objects`.


def _patch_fund_lookup(fund_obj):
    """Return a context manager that makes FundBasicInfo lookup return `fund_obj`."""
    mock_manager = MagicMock()
    mock_manager.filter.return_value.first.return_value = fund_obj
    return patch('info.models.FundBasicInfo.objects', mock_manager)


@patch.object(service_module, 'get_redis_conn')
@patch.object(service_module, 'persist_bars')
@patch.object(service_module, 'load_bars_from_db')
@patch.object(service_module, 'fetch_nav_from_chain')
@patch.object(service_module, 'fetch_ohlcv_from_chain')
def test_redis_hit_short_circuits_everything(
    mock_ohlcv, mock_nav, mock_load, mock_persist, mock_redis,
):
    fake = FakeRedis()
    # Pre-seed cache
    cached_response = '[{"time": "2024-01-02", "close": 10.10, "nav": 1.2345}]'
    # get_history uses a key that depends on start/end dates computed from today.
    # Just accept any key and return our cached payload by making get() return it
    # on the first call.
    class HitRedis(FakeRedis):
        def get(self, key):
            return cached_response
    mock_redis.return_value = HitRedis()

    svc = HistoricalDataService()
    result = svc.get_history('164906.SZ', range_key='1M')

    assert result == [{'time': '2024-01-02', 'close': 10.10, 'nav': 1.2345}]
    mock_load.assert_not_called()
    mock_ohlcv.assert_not_called()
    mock_nav.assert_not_called()
    mock_persist.assert_not_called()


@patch.object(service_module, 'get_redis_conn')
@patch.object(service_module, 'persist_bars')
@patch.object(service_module, 'load_bars_from_db')
@patch.object(service_module, 'fetch_nav_from_chain')
@patch.object(service_module, 'fetch_ohlcv_from_chain')
def test_fund_not_in_db_returns_none(
    mock_ohlcv, mock_nav, mock_load, mock_persist, mock_redis,
):
    mock_redis.return_value = FakeRedis()

    with _patch_fund_lookup(None):
        svc = HistoricalDataService()
        result = svc.get_history('SPY', range_key='1M')

    assert result is None
    mock_load.assert_not_called()
    mock_ohlcv.assert_not_called()
    mock_nav.assert_not_called()
    mock_persist.assert_not_called()


@patch.object(service_module, 'get_redis_conn')
@patch.object(service_module, 'persist_bars')
@patch.object(service_module, 'load_bars_from_db')
@patch.object(service_module, 'fetch_nav_from_chain')
@patch.object(service_module, 'fetch_ohlcv_from_chain')
def test_stale_triggers_full_fetch_and_persist(
    mock_ohlcv, mock_nav, mock_load, mock_persist, mock_redis,
):
    mock_redis.return_value = FakeRedis()
    # After provider fetch + persist, DB read returns the rows
    persisted_bars = _make_bars()
    persisted_bars[0].nav = Decimal('1.2345')
    mock_load.return_value = persisted_bars
    mock_ohlcv.return_value = _make_bars()
    mock_nav.return_value = [NAVPoint(date=date(2024, 1, 2), nav=Decimal('1.2345'))]

    fund = MagicMock()
    with _patch_fund_lookup(fund):
        svc = HistoricalDataService()
        result = svc.get_history('164906.SZ', range_key='1M')

    assert len(result) == 2
    assert result[0]['nav'] == 1.2345
    mock_ohlcv.assert_called_once()
    mock_nav.assert_called_once()
    mock_persist.assert_called_once()
    mock_load.assert_called_once()


@patch.object(service_module, 'get_redis_conn')
@patch.object(service_module, 'persist_bars')
@patch.object(service_module, 'load_bars_from_db')
@patch.object(service_module, 'fetch_nav_from_chain')
@patch.object(service_module, 'fetch_ohlcv_from_chain')
def test_fresh_stamp_skips_provider_fetch(
    mock_ohlcv, mock_nav, mock_load, mock_persist, mock_redis,
):
    fake = FakeRedis()
    # Pre-set freshness stamp — data is fresh
    fake.setex('mktdata:164906.SZ:last_check_at', 3600, '1')
    mock_redis.return_value = fake

    mock_load.return_value = _make_bars()

    fund = MagicMock()
    with _patch_fund_lookup(fund):
        svc = HistoricalDataService()
        svc.get_history('164906.SZ', range_key='1M')

    # When fresh, providers are not called — serve directly from DB
    mock_ohlcv.assert_not_called()
    mock_nav.assert_not_called()
    mock_persist.assert_not_called()
    mock_load.assert_called_once()
    # Response cache still written
    assert any(':v1:' in k for k in fake.store.keys())


@patch.object(service_module, 'get_redis_conn')
@patch.object(service_module, 'persist_bars')
@patch.object(service_module, 'load_bars_from_db')
@patch.object(service_module, 'fetch_nav_from_chain')
@patch.object(service_module, 'fetch_ohlcv_from_chain')
def test_provider_failure_does_not_break_response(
    mock_ohlcv, mock_nav, mock_load, mock_persist, mock_redis,
):
    mock_redis.return_value = FakeRedis()
    mock_load.return_value = []  # DB read after failed fetch
    mock_ohlcv.side_effect = ProviderError("down")
    mock_nav.side_effect = ProviderError("down")

    fund = MagicMock()
    with _patch_fund_lookup(fund):
        svc = HistoricalDataService()
        result = svc.get_history('164906.SZ', range_key='1M')

    assert result == []


@patch.object(service_module, 'get_redis_conn')
@patch.object(service_module, 'persist_bars')
@patch.object(service_module, 'load_bars_from_db')
@patch.object(service_module, 'fetch_nav_from_chain')
@patch.object(service_module, 'fetch_ohlcv_from_chain')
def test_second_call_served_from_response_cache(
    mock_ohlcv, mock_nav, mock_load, mock_persist, mock_redis,
):
    fake = FakeRedis()
    mock_redis.return_value = fake
    mock_load.return_value = _make_bars()
    mock_ohlcv.return_value = _make_bars()
    mock_nav.return_value = []

    fund = MagicMock()
    with _patch_fund_lookup(fund):
        svc = HistoricalDataService()
        first = svc.get_history('164906.SZ', range_key='1M')
        second = svc.get_history('164906.SZ', range_key='1M')

    assert first == second
    # Second call short-circuits at Redis → providers only called once
    assert mock_ohlcv.call_count == 1
    assert mock_nav.call_count == 1


@patch.object(service_module, 'get_redis_conn')
@patch.object(service_module, 'persist_bars')
@patch.object(service_module, 'load_bars_from_db')
@patch.object(service_module, 'fetch_nav_from_chain')
@patch.object(service_module, 'fetch_ohlcv_from_chain')
def test_freshness_stamp_set_after_fetch(
    mock_ohlcv, mock_nav, mock_load, mock_persist, mock_redis,
):
    fake = FakeRedis()
    mock_redis.return_value = fake
    mock_load.return_value = _make_bars()
    mock_ohlcv.return_value = _make_bars()
    mock_nav.return_value = []

    fund = MagicMock()
    with _patch_fund_lookup(fund):
        svc = HistoricalDataService()
        svc.get_history('164906.SZ', range_key='1M')

    assert 'mktdata:164906.SZ:last_check_at' in fake.store


# ---------- HistoricalDataService.find_incomplete ----------


def _bar(d: date, **overrides) -> OHLCVBar:
    """A complete bar by default; pass field=None to make it incomplete."""
    defaults = dict(
        open=Decimal('10'), high=Decimal('11'), low=Decimal('9'),
        close=Decimal('10.5'), volume=1000, nav=Decimal('1.05'),
    )
    defaults.update(overrides)
    return OHLCVBar(date=d, **defaults)


def test_find_incomplete_fund_not_in_db_returns_empty_report():
    with _patch_fund_lookup(None):
        svc = HistoricalDataService()
        report = svc.find_incomplete('GHOST')

    assert report == IncompleteReport(fund_code='GHOST')
    assert report.is_complete  # incomplete_rows == 0


@patch.object(service_module, 'load_bars_from_db')
def test_find_incomplete_all_complete(mock_load):
    mock_load.return_value = [
        _bar(date(2024, 1, 2)),
        _bar(date(2024, 1, 3)),
    ]
    with _patch_fund_lookup(MagicMock()):
        svc = HistoricalDataService()
        report = svc.find_incomplete('164906.SZ')

    assert report.total_rows == 2
    assert report.incomplete_rows == 0
    assert report.field_nulls == {}
    assert report.ranges == []
    assert report.is_complete


@patch.object(service_module, 'load_bars_from_db')
def test_find_incomplete_per_field_counts(mock_load):
    mock_load.return_value = [
        _bar(date(2024, 1, 2), nav=None),
        _bar(date(2024, 1, 3), nav=None, volume=None),
        _bar(date(2024, 1, 4)),
    ]
    with _patch_fund_lookup(MagicMock()):
        svc = HistoricalDataService()
        report = svc.find_incomplete('164906.SZ')

    assert report.total_rows == 3
    assert report.incomplete_rows == 2
    assert report.field_nulls == {'nav': 2, 'volume': 1}
    assert report.ranges == [(date(2024, 1, 2), date(2024, 1, 3))]
    assert not report.is_complete


@patch.object(service_module, 'load_bars_from_db')
def test_find_incomplete_field_filter_excludes_others(mock_load):
    # Row has volume=None, but we only check 'nav' — so it counts as complete.
    mock_load.return_value = [
        _bar(date(2024, 1, 2), volume=None),
    ]
    with _patch_fund_lookup(MagicMock()):
        svc = HistoricalDataService()
        report = svc.find_incomplete('164906.SZ', fields=['nav'])

    assert report.incomplete_rows == 0
    assert report.field_nulls == {}


@patch.object(service_module, 'load_bars_from_db')
def test_find_incomplete_invalid_field_raises(mock_load):
    mock_load.return_value = []
    with _patch_fund_lookup(MagicMock()):
        svc = HistoricalDataService()
        with pytest.raises(ValueError, match="Unknown fields"):
            svc.find_incomplete('164906.SZ', fields=['bogus'])


@patch.object(service_module, 'load_bars_from_db')
def test_find_incomplete_uppercases_symbol(mock_load):
    mock_load.return_value = []
    with _patch_fund_lookup(MagicMock()):
        svc = HistoricalDataService()
        report = svc.find_incomplete('164906.sz')

    assert report.fund_code == '164906.SZ'


@patch.object(service_module, 'load_bars_from_db')
def test_find_incomplete_single_db_query(mock_load):
    """Refactor invariant: only one DB read for all the analysis."""
    mock_load.return_value = [_bar(date(2024, 1, 2), nav=None)]
    with _patch_fund_lookup(MagicMock()):
        svc = HistoricalDataService()
        svc.find_incomplete('164906.SZ')

    assert mock_load.call_count == 1


# ---------- NAV skip when OHLCV already provides NAV ----------


@patch.object(service_module, 'get_redis_conn')
@patch.object(service_module, 'persist_bars')
@patch.object(service_module, 'load_bars_from_db')
@patch.object(service_module, 'fetch_nav_from_chain')
@patch.object(service_module, 'fetch_ohlcv_from_chain')
def test_nav_fetch_skipped_when_ohlcv_bars_carry_nav(
    mock_ohlcv, mock_nav, mock_load, mock_persist, mock_redis,
):
    """When OHLCV provider already populates nav (e.g. US ETFs), skip NAV chain."""
    mock_redis.return_value = FakeRedis()
    # OHLCV bars already have nav set (simulates YFinance nav=close for US ETFs)
    bars_with_nav = [
        OHLCVBar(date=date(2024, 1, 2), open=Decimal('28.00'), close=Decimal('28.50'),
                 high=Decimal('29.00'), low=Decimal('27.80'), volume=5000,
                 nav=Decimal('28.50')),
        OHLCVBar(date=date(2024, 1, 3), open=Decimal('28.50'), close=Decimal('28.80'),
                 high=Decimal('29.10'), low=Decimal('28.30'), volume=4500,
                 nav=Decimal('28.80')),
    ]
    mock_load.return_value = bars_with_nav
    mock_ohlcv.return_value = bars_with_nav

    fund = MagicMock()
    with _patch_fund_lookup(fund):
        svc = HistoricalDataService()
        result = svc.get_history('KWEB', range_key='1M')

    # OHLCV was fetched
    mock_ohlcv.assert_called_once()
    # NAV chain was NOT called because bars already have nav
    mock_nav.assert_not_called()
    # Data still persisted and returned
    mock_persist.assert_called_once()
    assert len(result) == 2
    assert result[0]['nav'] == 28.50


@patch.object(service_module, 'get_redis_conn')
@patch.object(service_module, 'persist_bars')
@patch.object(service_module, 'load_bars_from_db')
@patch.object(service_module, 'fetch_nav_from_chain')
@patch.object(service_module, 'fetch_ohlcv_from_chain')
def test_nav_fetch_called_when_ohlcv_bars_missing_nav(
    mock_ohlcv, mock_nav, mock_load, mock_persist, mock_redis,
):
    """When OHLCV bars don't carry nav (e.g. CN ETFs), NAV chain is called."""
    mock_redis.return_value = FakeRedis()
    # OHLCV bars without nav (simulates AkShare for CN ETFs)
    mock_load.return_value = _make_bars()
    mock_ohlcv.return_value = _make_bars()  # nav=None by default
    mock_nav.return_value = [
        NAVPoint(date=date(2024, 1, 2), nav=Decimal('1.2345')),
    ]

    fund = MagicMock()
    with _patch_fund_lookup(fund):
        svc = HistoricalDataService()
        svc.get_history('164906.SZ', range_key='1M')

    # Both OHLCV and NAV chains called
    mock_ohlcv.assert_called_once()
    mock_nav.assert_called_once()
