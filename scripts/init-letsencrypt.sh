#!/bin/bash
# Obtain the initial SSL certificate from Let's Encrypt.
# Run once on initial server setup.
#
# Usage: ./scripts/init-letsencrypt.sh [email]
#   email - optional, for Let's Encrypt renewal notifications

set -e

COMPOSE="docker compose -f docker-compose.prod.yml"

# Load DOMAIN from .env
if [ -f backend/.env ]; then
    export $(grep -E '^DOMAIN=' backend/.env | xargs)
fi

if [ -z "$DOMAIN" ]; then
    echo "Error: DOMAIN not set. Check backend/.env"
    exit 1
fi

EMAIL="${1:-}"

echo "==> Obtaining SSL certificate for $DOMAIN"

# Step 1: Create dummy certificate so nginx can start
echo "==> Creating temporary self-signed certificate..."
$COMPOSE run --rm --entrypoint "\
  sh -c \"mkdir -p /etc/letsencrypt/live/$DOMAIN && \
  openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
    -keyout /etc/letsencrypt/live/$DOMAIN/privkey.pem \
    -out /etc/letsencrypt/live/$DOMAIN/fullchain.pem \
    -subj '/CN=localhost'\"" certbot

# Step 2: Start nginx with dummy certificate
echo "==> Starting nginx..."
$COMPOSE up -d nginx

# Step 3: Remove dummy certificate
echo "==> Removing temporary certificate..."
$COMPOSE run --rm --entrypoint "\
  sh -c \"rm -rf /etc/letsencrypt/live/$DOMAIN && \
  rm -rf /etc/letsencrypt/archive/$DOMAIN && \
  rm -rf /etc/letsencrypt/renewal/$DOMAIN.conf\"" certbot

# Step 4: Request real certificate
echo "==> Requesting certificate from Let's Encrypt..."
if [ -z "$EMAIL" ]; then
    EMAIL_ARG="--register-unsafely-without-email"
else
    EMAIL_ARG="--email $EMAIL"
fi

$COMPOSE run --rm --entrypoint "\
  certbot certonly --webroot -w /var/www/certbot \
    $EMAIL_ARG \
    -d $DOMAIN \
    --agree-tos \
    --no-eff-email \
    --force-renewal" certbot

# Step 5: Reload nginx with real certificate
echo "==> Reloading nginx..."
$COMPOSE exec nginx nginx -s reload

echo "==> Done! SSL certificate obtained for $DOMAIN."
