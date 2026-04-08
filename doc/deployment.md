# Production Deployment Guide

Deploy FunD to a VPS using Docker Compose with Nginx reverse proxy and Let's Encrypt SSL.

## Prerequisites

- **Server**: Ubuntu 22.04+ VPS with root/sudo access
- **Docker**: Docker Engine 24+ and Docker Compose v2
- **Domain**: DNS A record pointing to your server's IP address
- **Firewall**: Ports 22 (SSH), 80 (HTTP), 443 (HTTPS) open

### Install Docker (if needed)

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in for group change to take effect
```

### Set up swap (recommended for 1GB VPS)

A 1GB swap file prevents out-of-memory kills during builds and traffic spikes.

```bash
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Memory budget

The production compose sets `mem_limit` per service. Approximate usage at idle:

| Service    | Limit  | Typical |
|------------|--------|---------|
| web        | 300 MB | ~150 MB |
| db         | 256 MB | ~80 MB  |
| redis      | 96 MB  | ~10 MB  |
| nginx      | 64 MB  | ~5 MB   |
| certbot    | 96 MB  | ~0 (sleeps) |
| **Total**  | **812 MB** | **~245 MB** |

With 1GB RAM + 1GB swap this leaves headroom for the OS and Docker overhead.

## Initial Setup

### 1. Clone the repository

```bash
git clone <your-repo-url> /opt/fund
cd /opt/fund
```

### 2. Configure environment

```bash
cp backend/.env.production.example backend/.env
```

Edit `backend/.env` and fill in:

- `DJANGO_SECRET_KEY` — generate with:
  ```bash
  python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
  ```
  Or use: `openssl rand -base64 50`
- `POSTGRES_PASSWORD` — strong random password
- `ALLOWED_HOSTS` — your domain (e.g. `yourdomain.com,www.yourdomain.com`)
- `DOMAIN` — your domain (e.g. `yourdomain.com`)

### 3. Obtain SSL certificate

```bash
./scripts/init-letsencrypt.sh your@email.com
```

This creates a temporary self-signed cert, starts Nginx, then replaces it with a real Let's Encrypt certificate. The email is optional but recommended for renewal notifications.

### 4. Start all services

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### 5. Initialize the database

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
docker compose -f docker-compose.prod.yml exec web python manage.py loaddata initial_data.json
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

Your site should now be live at `https://yourdomain.com`.

## Updating the Application

```bash
cd /opt/fund
git pull origin main
docker compose -f docker-compose.prod.yml up -d --build web
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
```

Only the app containers are rebuilt; db, redis, and nginx continue running.

## SSL Certificate Renewal

The Certbot sidecar container automatically attempts renewal every 12 hours. For manual renewal:

```bash
docker compose -f docker-compose.prod.yml run --rm certbot renew
docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

Optional crontab for automated nginx reload after renewal:

```bash
# Edit crontab: crontab -e
0 3 * * 1 cd /opt/fund && docker compose -f docker-compose.prod.yml run --rm certbot renew && docker compose -f docker-compose.prod.yml exec nginx nginx -s reload >> /var/log/certbot-renew.log 2>&1
```

## PostgreSQL Backups

### Manual backup

```bash
docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U fund_user fund_prod | gzip > backups/fund_$(date +%Y%m%d_%H%M%S).sql.gz
```

### Automated daily backup (crontab)

```bash
mkdir -p /opt/fund/backups

# crontab -e
0 2 * * * cd /opt/fund && docker compose -f docker-compose.prod.yml exec -T db pg_dump -U fund_user fund_prod | gzip > backups/fund_$(date +\%Y\%m\%d_\%H\%M\%S).sql.gz 2>> /var/log/fund-backup.log

# Clean up backups older than 30 days
0 3 * * * find /opt/fund/backups -name "*.sql.gz" -mtime +30 -delete
```

### Restore from backup

```bash
gunzip < backups/fund_20260408_020000.sql.gz | \
  docker compose -f docker-compose.prod.yml exec -T db psql -U fund_user fund_prod
```

## Monitoring and Logs

```bash
# Service status
docker compose -f docker-compose.prod.yml ps

# Follow logs (all services)
docker compose -f docker-compose.prod.yml logs -f

# Follow specific service logs
docker compose -f docker-compose.prod.yml logs -f web
docker compose -f docker-compose.prod.yml logs -f celery
docker compose -f docker-compose.prod.yml logs -f nginx

# Check resource usage
docker stats
```

## Troubleshooting

### 502 Bad Gateway

Nginx is running but cannot reach gunicorn.

```bash
# Check if web container is running
docker compose -f docker-compose.prod.yml ps web
# Check web logs for errors
docker compose -f docker-compose.prod.yml logs web
```

Common causes: web container crashed (check logs), database not ready (check db health).

### SSL certificate errors

```bash
# Check certificate status
docker compose -f docker-compose.prod.yml run --rm certbot certificates
# Re-run the bootstrap script if needed
./scripts/init-letsencrypt.sh your@email.com
```

### Database migration failures

```bash
# Check current migration state
docker compose -f docker-compose.prod.yml exec web python manage.py showmigrations
# Try running migrations with verbosity
docker compose -f docker-compose.prod.yml exec web python manage.py migrate --verbosity 2
```

### Static files not loading (404)

```bash
# Verify static files exist in the container
docker compose -f docker-compose.prod.yml exec web ls staticfiles/
# Re-collect if needed
docker compose -f docker-compose.prod.yml exec web python manage.py collectstatic --noinput
```

## Architecture Overview

```
Internet
  │
  ├── :80  ──→ Nginx ──→ redirect to :443
  └── :443 ──→ Nginx ──┬──→ /static/  (served directly from volume)
                        └──→ /*        (proxy to Gunicorn :8000)
                                          │
                              ┌─────────────────────────┐
                              │                         │
                           PostgreSQL                 Redis
```

All services communicate over an internal Docker network. Only Nginx ports (80, 443) are exposed to the host.
