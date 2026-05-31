from dataclasses import asdict

from django.core.management.base import BaseCommand

from info.market_data.data_api import get_quotes_from_sina_us


class Command(BaseCommand):
    help = 'Fetch live quote(s) from Sina US for the given symbol(s) and print them.'

    def add_arguments(self, parser):
        parser.add_argument(
            'symbols',
            nargs='+',
            help='One or more US symbols (e.g. KWEB AAPL TSLA).',
        )
        parser.add_argument(
            '--json',
            action='store_true',
            help='Emit raw JSON instead of a formatted table.',
        )

    def handle(self, *args, **options):
        symbols = [s.upper() for s in options['symbols']]
        quotes = get_quotes_from_sina_us(symbols)

        if not quotes:
            self.stdout.write(self.style.WARNING(
                f"No quotes returned for {symbols}. The market may be closed or the upstream blocked."
            ))
            return

        if options['json']:
            import json
            self.stdout.write(json.dumps(
                {sym: asdict(q) for sym, q in quotes.items()},
                indent=2,
            ))
            return

        cols = ('symbol', 'name', 'price', 'change', 'open', 'high', 'low', 'volume', 'datetime')
        header = f"{'SYMBOL':<8} {'NAME':<28} {'PRICE':>10} {'CHANGE':>8} {'OPEN':>10} {'HIGH':>10} {'LOW':>10} {'VOLUME':>14}  DATETIME"
        self.stdout.write(header)
        self.stdout.write('-' * len(header))
        for sym in symbols:
            q = quotes.get(sym)
            if q is None:
                self.stdout.write(f"{sym:<8} {'(no data)':<28}")
                continue
            self.stdout.write(
                f"{q.symbol:<8} {q.name[:28]:<28} "
                f"{q.price:>10.4f} {q.change:>8.4f} "
                f"{q.open:>10.4f} {q.high:>10.4f} {q.low:>10.4f} "
                f"{q.volume:>14,d}  {q.datetime}"
            )

        missing = [s for s in symbols if s not in quotes]
        if missing:
            self.stdout.write(self.style.WARNING(f"\nNo data returned for: {', '.join(missing)}"))
