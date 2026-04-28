from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from info.market_data.base import ProviderError
from info.market_data.persistence import persist_bars
from info.market_data.registry import fetch_nav_from_chain, fetch_ohlcv_from_chain
from info.models import FundBasicInfo, FundDailyData


class Command(BaseCommand):
    help = 'Find FundDailyData rows with NULL fields and attempt to fill them from providers'

    def add_arguments(self, parser):
        parser.add_argument('fund_code', nargs='?', type=str, help='Fund code (optional — fills all funds if omitted)')
        parser.add_argument('--dry-run', action='store_true', help='Only report missing data, do not fetch')
        parser.add_argument('--fields', type=str, default='all',
                            help='Comma-separated fields to check: open,high,low,close,volume,nav (default: all)')

    def handle(self, *args, **options):
        funds = self._resolve_funds(options['fund_code'])
        field_filter = self._build_field_filter(options['fields'])
        dry_run = options['dry_run']

        total_found = 0
        total_filled = 0

        for fund in funds:
            rows = FundDailyData.objects.filter(fund=fund).filter(field_filter).order_by('date')
            count = rows.count()
            if count == 0:
                continue

            total_found += count
            dates = list(rows.values_list('date', flat=True))
            self.stdout.write(f"\n{fund.fund_code}: {count} rows with missing data "
                             f"({dates[0]} to {dates[-1]})")

            if dry_run:
                self._print_summary(rows)
                continue

            filled = self._fill_fund(fund, dates)
            total_filled += filled

        self.stdout.write('')
        if dry_run:
            self.stdout.write(self.style.WARNING(f"Dry run: {total_found} rows with gaps across {len(funds)} fund(s)"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Done. {total_filled} rows updated out of {total_found} with gaps."))

    def _resolve_funds(self, fund_code):
        if fund_code:
            fund_code = fund_code.upper()
            try:
                return [FundBasicInfo.objects.get(fund_code=fund_code)]
            except FundBasicInfo.DoesNotExist:
                raise CommandError(f"Fund '{fund_code}' not found")
        return list(FundBasicInfo.objects.all())

    def _build_field_filter(self, fields_str):
        """Build a Q filter that matches rows where any specified field is NULL."""
        field_map = {
            'open': 'open',
            'high': 'high',
            'low': 'low',
            'close': 'close',
            'volume': 'volume',
            'nav': 'net_asset_value',
        }
        if fields_str == 'all':
            keys = field_map.keys()
        else:
            keys = [f.strip() for f in fields_str.split(',')]
            invalid = set(keys) - set(field_map.keys())
            if invalid:
                raise CommandError(f"Unknown fields: {invalid}. Valid: {list(field_map.keys())}")

        q = Q()
        for key in keys:
            q |= Q(**{f'{field_map[key]}__isnull': True})
        return q

    def _print_summary(self, rows):
        """Print per-field NULL counts for dry-run."""
        fields = ['open', 'high', 'low', 'close', 'volume', 'net_asset_value']
        for field in fields:
            null_count = rows.filter(**{f'{field}__isnull': True}).count()
            if null_count:
                label = 'nav' if field == 'net_asset_value' else field
                self.stdout.write(f"  {label}: {null_count} missing")

    def _fill_fund(self, fund, dates):
        """Fetch data for date ranges covering the missing dates and upsert."""
        ranges = self._collapse_dates(dates)
        before_nulls = self._count_nulls(fund)

        for start, end in ranges:
            self.stdout.write(f"  Fetching {fund.fund_code} [{start}, {end}]...")
            bars = []
            nav_points = []
            try:
                bars = fetch_ohlcv_from_chain(fund.fund_code, start, end)
            except ProviderError as exc:
                self.stdout.write(self.style.WARNING(f"    OHLCV failed: {exc}"))
            try:
                nav_points = fetch_nav_from_chain(fund.fund_code, start, end)
            except ProviderError as exc:
                self.stdout.write(self.style.WARNING(f"    NAV failed: {exc}"))

            if bars or nav_points:
                persist_bars(fund, bars, nav_points)

        after_nulls = self._count_nulls(fund)
        filled = before_nulls - after_nulls
        if filled > 0:
            self.stdout.write(self.style.SUCCESS(f"  Filled {filled} NULL fields"))
        else:
            self.stdout.write("  No new data available from providers")
        return filled

    def _count_nulls(self, fund):
        """Count total NULL field occurrences across all rows for a fund."""
        fields = ['open', 'high', 'low', 'close', 'volume', 'net_asset_value']
        total = 0
        for field in fields:
            total += FundDailyData.objects.filter(fund=fund, **{f'{field}__isnull': True}).count()
        return total

    def _collapse_dates(self, dates):
        """Collapse a sorted list of dates into contiguous ranges (with 5-day tolerance)."""
        if not dates:
            return []
        ranges = []
        start = dates[0]
        prev = dates[0]
        for d in dates[1:]:
            if (d - prev).days <= 5:
                prev = d
            else:
                ranges.append((start, prev))
                start = d
                prev = d
        ranges.append((start, prev))
        return ranges
