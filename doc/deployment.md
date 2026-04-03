To depoly the app, we use docker-compose to manage multiple services including the Django backend, PostgreSQL database, and Redis server.

Make sure replace the password in the `.env` file with a very strong password before deployment.

## Import fixtures to populate the database with initial data (fund list, etc.):

```bash
uv run python manage.py loaddata initial_data.json
```