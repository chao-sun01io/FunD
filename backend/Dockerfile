FROM python:3.10-slim

WORKDIR /usr/src/app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV UV_SYSTEM_PYTHON=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
RUN uv pip install gunicorn

COPY . /usr/src/app

RUN DJANGO_SECRET_KEY=build-placeholder DJANGO_DEBUG=False \
    python manage.py collectstatic --noinput

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2", "--max-requests", "1000", "--max-requests-jitter", "50", "--timeout", "120"]
