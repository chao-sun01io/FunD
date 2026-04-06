from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError

from info.market_data.base import ProviderError
from info.market_data.service import HistoricalDataService
from info.models import FundBasicInfo


class Command(BaseCommand):
    help = 'Backfill historical OHLCV data for a fund from external providers'

    def add_arguments(self, parser):
        parser.add_argument('fund_code', type=str, help='Fund code (e.g. KWEB, 164906.SZ)')
        parser.add_argument('--years', type=int, default=2, help='Number of years to backfill (default: 2)')
        parser.add_argument('--start-date', type=str, help='Start date (YYYY-MM-DD), overrides --years')

    def handle(self, *args, **options):
        fund_code = options['fund_code'].upper()

        try:
            FundBasicInfo.objects.get(fund_code=fund_code)
        except FundBasicInfo.DoesNotExist:
            raise CommandError(f"Fund '{fund_code}' not found in database")

        if options['start_date']:
            start = date.fromisoformat(options['start_date'])
        else:
            start = date.today() - timedelta(days=options['years'] * 365)

        self.stdout.write(f"Backfilling {fund_code} from {start}...")

        service = HistoricalDataService()
        try:
            count = service.backfill(fund_code, start)
        except ProviderError as exc:
            raise CommandError(f"Provider error: {exc}")

        self.stdout.write(self.style.SUCCESS(f"Done. {count} rows upserted for {fund_code}."))
