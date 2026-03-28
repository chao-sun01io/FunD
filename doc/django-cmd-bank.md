## Start a Django Project

```bash
django-admin startproject config # Create a new Django project named 'config', the main project directory
python manage.py startapp info # Create a new Django app named 'info' within the current project
```

## Develop the Django App

```bash
python manage.py makemigrations info # Create migrations for the 'info' app
python manage.py migrate # Apply the migrations to the database
python manage.py runserver # Start the Django development server
python manage.py createsuperuser # Create a superuser for the admin interface
python manage.py sqlmigrate info 0001 # Show the SQL for the first migration of the 'info' app
python manage.py shell # Open the Django shell for interactive use
python mnanage.py check # Check the project for any issues
```

## Test env

- run celery worker

```bash
celery -A config worker --loglevel=info # Start a Celery worker for the Django project with logging set to info level
```

- test the celery task from the Django shell

```bash
python manage.py shell # Open the Django shell
```

```python
```