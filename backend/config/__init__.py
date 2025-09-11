# This will ensure that the Celery app is correctly initialized
# and can be imported from other modules in the project.
from .celery import app as celery_app

__all__ = ('celery_app',)