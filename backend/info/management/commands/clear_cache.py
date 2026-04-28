from django.core.management.base import BaseCommand

from info.utils.redis_conn import get_redis_conn


class Command(BaseCommand):
    help = 'Clear all keys from the Redis cache'

    def add_arguments(self, parser):
        parser.add_argument('--yes', action='store_true', help='Skip confirmation prompt')

    def handle(self, *args, **options):
        r = get_redis_conn()
        key_count = r.dbsize()

        if key_count == 0:
            self.stdout.write("Redis DB is already empty.")
            return

        if not options['yes']:
            self.stdout.write(f"This will delete all {key_count} keys from Redis.")
            confirm = input("Are you sure? [y/N] ")
            if confirm.lower() != 'y':
                self.stdout.write("Aborted.")
                return

        r.flushdb()
        self.stdout.write(self.style.SUCCESS(f"Cleared {key_count} keys from Redis."))
