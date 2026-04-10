import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import transaction

from info.market_data.base import NAVPoint, OHLCVBar
from info.models import FundBasicInfo, FundDailyData

logger = logging.getLogger(__name__)


_OHLCV_FIELDS = ('open', 'high', 'low', 'close', 'volume')
_ALL_FIELDS = _OHLCV_FIELDS + ('net_asset_value',)


@dataclass
class _MergedRow:
    """Fields for one (fund, date) row, merged from OHLCV bars and NAV points."""
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    volume: int | None = None
    net_asset_value: Decimal | None = None


def load_bars_from_db(
    fund: FundBasicInfo,
    start_date: date,
    end_date: date,
) -> list[OHLCVBar]:
    """Read FundDailyData rows in [start_date, end_date] as OHLCVBars.

    Maps DB column `net_asset_value` → `OHLCVBar.nav`. Rows ordered by date ascending.
    """
    rows = FundDailyData.objects.filter(
        fund=fund,
        date__gte=start_date,
        date__lte=end_date,
    ).order_by('date')

    return [
        OHLCVBar(
            date=row.date,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
            nav=row.net_asset_value,
        )
        for row in rows
    ]


def _merge_sources(
    bars: list[OHLCVBar],
    nav_points: list[NAVPoint],
) -> dict[date, _MergedRow]:
    """Union bars + nav_points by date, preferring explicit NAVPoint over OHLCVBar.nav."""
    merged: dict[date, _MergedRow] = {}
    for bar in bars:
        row = merged.setdefault(bar.date, _MergedRow())
        row.open = bar.open
        row.high = bar.high
        row.low = bar.low
        row.close = bar.close
        row.volume = bar.volume
        if bar.nav is not None:
            row.net_asset_value = bar.nav
    for point in nav_points:
        row = merged.setdefault(point.date, _MergedRow())
        row.net_asset_value = point.nav
    return merged


def persist_bars(
    fund: FundBasicInfo,
    bars: list[OHLCVBar],
    nav_points: list[NAVPoint] | None = None,
) -> None:
    """Upsert OHLCV + NAV rows into FundDailyData for a single fund.

    Union of bars' dates and nav_points' dates is written in one transaction.
    Existing rows are updated only for fields that actually changed; missing
    rows are bulk-inserted. Dates present in only one source are still written
    (the other fields remain NULL).
    """
    nav_points = nav_points or []
    if not bars and not nav_points:
        return

    merged = _merge_sources(bars, nav_points)
    if not merged:
        return

    dates = list(merged.keys())
    existing: dict[date, FundDailyData] = {
        row.date: row
        for row in FundDailyData.objects.filter(fund=fund, date__in=dates)
    }

    to_create: list[FundDailyData] = []
    to_update: list[FundDailyData] = []

    for d, merged_row in merged.items():
        existing_row = existing.get(d)
        if existing_row is None:
            to_create.append(FundDailyData(
                fund=fund,
                date=d,
                open=merged_row.open,
                high=merged_row.high,
                low=merged_row.low,
                close=merged_row.close,
                volume=merged_row.volume,
                net_asset_value=merged_row.net_asset_value,
            ))
            continue

        changed = False
        for field in _ALL_FIELDS:
            new_value = getattr(merged_row, field)
            if new_value is None:
                continue  # don't clobber existing data with None
            if getattr(existing_row, field) != new_value:
                setattr(existing_row, field, new_value)
                changed = True
        if changed:
            to_update.append(existing_row)

    with transaction.atomic():
        if to_create:
            FundDailyData.objects.bulk_create(to_create, ignore_conflicts=True)
        if to_update:
            FundDailyData.objects.bulk_update(to_update, list(_ALL_FIELDS))

    logger.debug(
        "persist_bars: fund=%s created=%d updated=%d",
        fund.fund_code, len(to_create), len(to_update),
    )
