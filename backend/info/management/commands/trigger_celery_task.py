from django.core.management.base import BaseCommand
from info.tasks import fetch_pcf_kweb, fetch_kweb_price

class Command(BaseCommand):
    help = 'Manually triggers Celery tasks for testing.'

    def handle(self, *args, **options):
        self.stdout.write("Triggering 'fetch_pcf_kweb' task...")
        res1 = fetch_pcf_kweb.delay()
        
        self.stdout.write("Triggering 'fetch_kweb_quote' task...")
        fetch_kweb_price.delay()

        self.stdout.write("Tasks have been triggered.")
        
