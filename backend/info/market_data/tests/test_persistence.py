from datetime import date
from decimal import Decimal

import pytest

from info.market_data.base import NAVPoint, OHLCVBar
from info.market_data.persistence import load_bars_from_db, persist_bars
from info.models import FundBasicInfo, FundDailyData


@pytest.fixture
def fund(db):
    return FundBasicInfo.objects.create(
        fund_code='164906.SZ',
        fund_name='Test Fund',
        fund_type='ETF',
        currency='CNY',
        listing_exchange='SZ',
        fund_company='Test Co',
        inception_date=date(2020, 1, 1),
    )


@pytest.mark.django_db
class TestPersistBars:
    def test_insert_new_rows_ohlcv_only(self, fund):
        bars = [
            OHLCVBar(
                date=date(2024, 1, 2),
                open=Decimal('10.00'),
                high=Decimal('10.30'),
                low=Decimal('9.95'),
                close=Decimal('10.20'),
                volume=1000,
            ),
            OHLCVBar(
                date=date(2024, 1, 3),
                open=Decimal('10.20'),
                high=Decimal('10.40'),
                low=Decimal('10.10'),
                close=Decimal('10.35'),
                volume=1500,
            ),
        ]
        persist_bars(fund, bars, [])

        rows = FundDailyData.objects.filter(fund=fund).order_by('date')
        assert rows.count() == 2
        assert rows[0].open == Decimal('10.00')
        assert rows[0].close == Decimal('10.20')
        assert rows[0].net_asset_value is None
        assert rows[1].volume == 1500

    def test_insert_new_rows_nav_only(self, fund):
        nav_points = [
            NAVPoint(date=date(2024, 1, 2), nav=Decimal('1.2345')),
            NAVPoint(date=date(2024, 1, 3), nav=Decimal('1.2400')),
        ]
        persist_bars(fund, [], nav_points)

        rows = FundDailyData.objects.filter(fund=fund).order_by('date')
        assert rows.count() == 2
        assert rows[0].net_asset_value == Decimal('1.2345')
        assert rows[0].open is None
        assert rows[1].net_asset_value == Decimal('1.2400')

    def test_merge_ohlcv_and_nav_by_date(self, fund):
        bars = [
            OHLCVBar(date=date(2024, 1, 2), close=Decimal('10.20'), volume=1000),
            OHLCVBar(date=date(2024, 1, 3), close=Decimal('10.35'), volume=1500),
        ]
        nav_points = [
            NAVPoint(date=date(2024, 1, 2), nav=Decimal('1.2345')),
            NAVPoint(date=date(2024, 1, 3), nav=Decimal('1.2400')),
        ]
        persist_bars(fund, bars, nav_points)

        rows = FundDailyData.objects.filter(fund=fund).order_by('date')
        assert rows.count() == 2
        assert rows[0].close == Decimal('10.20')
        assert rows[0].net_asset_value == Decimal('1.2345')
        assert rows[1].close == Decimal('10.35')
        assert rows[1].net_asset_value == Decimal('1.2400')

    def test_dates_unique_to_one_source_are_written(self, fund):
        bars = [OHLCVBar(date=date(2024, 1, 2), close=Decimal('10.20'))]
        nav_points = [NAVPoint(date=date(2024, 1, 3), nav=Decimal('1.2400'))]
        persist_bars(fund, bars, nav_points)

        rows = {r.date: r for r in FundDailyData.objects.filter(fund=fund)}
        assert rows[date(2024, 1, 2)].close == Decimal('10.20')
        assert rows[date(2024, 1, 2)].net_asset_value is None
        assert rows[date(2024, 1, 3)].net_asset_value == Decimal('1.2400')
        assert rows[date(2024, 1, 3)].close is None

    def test_update_existing_row_with_nav(self, fund):
        # Existing OHLCV-only row
        FundDailyData.objects.create(
            fund=fund,
            date=date(2024, 1, 2),
            open=Decimal('10.00'),
            close=Decimal('10.20'),
            volume=1000,
        )
        persist_bars(fund, [], [NAVPoint(date=date(2024, 1, 2), nav=Decimal('1.2345'))])

        row = FundDailyData.objects.get(fund=fund, date=date(2024, 1, 2))
        assert row.close == Decimal('10.20')  # untouched
        assert row.volume == 1000  # untouched
        assert row.net_asset_value == Decimal('1.2345')  # added

    def test_none_does_not_clobber_existing(self, fund):
        # Row has NAV
        FundDailyData.objects.create(
            fund=fund,
            date=date(2024, 1, 2),
            net_asset_value=Decimal('1.2345'),
        )
        # Incoming OHLCV bar has no nav — should not clear the existing NAV
        bars = [OHLCVBar(date=date(2024, 1, 2), close=Decimal('10.20'))]
        persist_bars(fund, bars, [])

        row = FundDailyData.objects.get(fund=fund, date=date(2024, 1, 2))
        assert row.close == Decimal('10.20')
        assert row.net_asset_value == Decimal('1.2345')

    def test_noop_when_nothing_changes(self, fund):
        FundDailyData.objects.create(
            fund=fund,
            date=date(2024, 1, 2),
            close=Decimal('10.20'),
            net_asset_value=Decimal('1.2345'),
        )
        bars = [OHLCVBar(date=date(2024, 1, 2), close=Decimal('10.20'))]
        nav_points = [NAVPoint(date=date(2024, 1, 2), nav=Decimal('1.2345'))]

        # Should not raise, count unchanged
        persist_bars(fund, bars, nav_points)
        assert FundDailyData.objects.filter(fund=fund).count() == 1

    def test_empty_inputs_are_noop(self, fund):
        persist_bars(fund, [], [])
        assert FundDailyData.objects.filter(fund=fund).count() == 0


@pytest.mark.django_db
class TestLoadBarsFromDb:
    def test_roundtrip(self, fund):
        FundDailyData.objects.create(
            fund=fund,
            date=date(2024, 1, 2),
            open=Decimal('10.00'),
            high=Decimal('10.30'),
            low=Decimal('9.95'),
            close=Decimal('10.20'),
            volume=1000,
            net_asset_value=Decimal('1.2345'),
        )
        FundDailyData.objects.create(
            fund=fund,
            date=date(2024, 1, 3),
            close=Decimal('10.35'),
            net_asset_value=Decimal('1.2400'),
        )

        bars = load_bars_from_db(fund, date(2024, 1, 1), date(2024, 1, 31))

        assert len(bars) == 2
        # Ordered ascending
        assert bars[0].date == date(2024, 1, 2)
        assert bars[0].open == Decimal('10.00')
        assert bars[0].close == Decimal('10.20')
        assert bars[0].volume == 1000
        assert bars[0].nav == Decimal('1.2345')
        assert bars[1].date == date(2024, 1, 3)
        assert bars[1].nav == Decimal('1.2400')

    def test_range_filter(self, fund):
        for d in (date(2024, 1, 2), date(2024, 1, 15), date(2024, 2, 1)):
            FundDailyData.objects.create(fund=fund, date=d, close=Decimal('10'))

        bars = load_bars_from_db(fund, date(2024, 1, 1), date(2024, 1, 31))
        assert [b.date for b in bars] == [date(2024, 1, 2), date(2024, 1, 15)]

    def test_empty_returns_empty_list(self, fund):
        bars = load_bars_from_db(fund, date(2024, 1, 1), date(2024, 1, 31))
        assert bars == []
