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
    worker_concurrency=2,  # Number of worker processes
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks
    worker_prefetch_multiplier=1,  # Don't prefetch tasks
)

# TODO: use django-celery-beat to manage the schedule in database
app.conf.beat_schedule = {
    'poll-live-quotes-every-15s': {
        'task': 'info.tasks.poll_live_quotes',
        'schedule': 15.0,
    },
}

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
