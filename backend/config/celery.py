import os
from celery import Celery
# Set the default Django settings module for the 'celery' program.
# This is necessary for Celery to find the Django settings.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')


app = Celery('FunD')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix in the config.settings.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks() 

# Worker Configuration
app.conf.update(
    worker_concurrency=4,  # Number of worker processes
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks
    worker_prefetch_multiplier=1,  # Don't prefetch tasks
)

# TODO: use django-celery-beat to manage the schedule in database
app.conf.beat_schedule = {
    'fetch-kweb-price-every-15-seconds': {
        'task': 'info.tasks.fetch_kweb_price',
        'schedule': 15.0,  # Run every 15 seconds
    },
}

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
