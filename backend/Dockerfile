FROM python:3.10-slim

WORKDIR /usr/src/app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN pip install --upgrade pip
COPY requirements.txt /usr/src/app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . /usr/src/app