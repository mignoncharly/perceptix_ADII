# Perceptix Production Deployment Files

This directory contains all the necessary configuration files and scripts for deploying Perceptix to a production IONOS VPS running Ubuntu.

## Directory Structure

```
deploy/
├── README.md                          # This file
├── gunicorn_config.py                 # Gunicorn WSGI server configuration
├── nginx/
│   └── perceptix.conf                 # Nginx reverse proxy configuration
├── systemd/
│   └── perceptix-api.service         # systemd service file
└── scripts/
    ├── backup-database.sh            # Automated database backup script
    ├── health-check.sh               # Health monitoring script
    └── deploy.sh                     # Automated deployment script
```

## File Descriptions

### Configuration Files

#### `gunicorn_config.py`
Production-ready Gunicorn configuration with:
- Auto-calculated worker count based on CPU cores
- Uvicorn worker class for ASGI support
- Logging to `/var/log/gemini/`
- Process management and timeouts
- Security settings

**Deployment location:** `/home/mignon/gemini/gunicorn_config.py`

#### `nginx/perceptix.conf`
Complete Nginx configuration with:
- HTTP to HTTPS redirect
- SSL/TLS configuration (Let's Encrypt)
- Security headers (HSTS, CSP, X-Frame-Options, etc.)
- Rate limiting for API endpoints
- WebSocket support
- Static file serving with caching
- Gzip compression

**Deployment location:** `/etc/nginx/sites-available/perceptix`

#### `systemd/perceptix-api.service`
systemd service unit for:
- Automatic service startup on boot
- Auto-restart on failure
- Resource limits (memory, CPU, file descriptors)
- Security hardening (filesystem protection, private tmp)
- Environment variable loading from `.env`
- Logging to journald and files

**Deployment location:** `/etc/systemd/system/perceptix-api.service`

### Maintenance Scripts

#### `scripts/backup-database.sh`
Automated backup script that:
- Backs up all SQLite databases
- Compresses backups with gzip
- Automatically removes backups older than 30 days
- Logs all operations
- Verifies backup integrity

**Usage:**
```bash
# Manual backup
sudo /usr/local/bin/backup-perceptix-db.sh

# Schedule daily backups at 2 AM
sudo crontab -u perceptix -e
0 2 * * * /usr/local/bin/backup-perceptix-db.sh
```

#### `scripts/health-check.sh`
Comprehensive health monitoring that checks:
- API health and readiness endpoints
- systemd service status
- Disk space usage
- Database integrity
- Recent error logs
- Response times
- Optional Slack alerting

**Usage:**
```bash
# Manual health check
/usr/local/bin/perceptix-health-check.sh

# Schedule health checks every 5 minutes
sudo crontab -e
*/5 * * * * /usr/local/bin/perceptix-health-check.sh
```

#### `scripts/deploy.sh`
Automated deployment script that:
- Pulls latest code from Git
- Updates Python dependencies
- Builds frontend
- Runs database migrations
- Restarts services
- Verifies deployment
- Creates pre-deployment backups

**Usage:**
```bash
# Standard deployment
sudo -u perceptix /home/mignon/gemini/deploy/scripts/deploy.sh

# Deploy specific branch
sudo -u perceptix /home/mignon/gemini/deploy/scripts/deploy.sh --branch development

# Skip frontend build
sudo -u perceptix /home/mignon/gemini/deploy/scripts/deploy.sh --skip-frontend

# Skip service restart (for testing)
sudo -u perceptix /home/mignon/gemini/deploy/scripts/deploy.sh --skip-restart
```

## Quick Deployment Steps

### 1. Copy Configuration Files

```bash
# As root or with sudo
cd /home/mignon/gemini

# Copy Gunicorn config
cp deploy/gunicorn_config.py .
chown perceptix:perceptix gunicorn_config.py

# Copy systemd service
cp deploy/systemd/perceptix-api.service /etc/systemd/system/
systemctl daemon-reload

# Copy Nginx config
cp deploy/nginx/perceptix.conf /etc/nginx/sites-available/perceptix
ln -s /etc/nginx/sites-available/perceptix /etc/nginx/sites-enabled/

# Copy scripts
cp deploy/scripts/*.sh /usr/local/bin/
chmod +x /usr/local/bin/*.sh
```

### 2. Edit Domain Names

Update the following files with your actual domain:

```bash
# Nginx configuration
nano /etc/nginx/sites-available/perceptix
# Replace: perceptix.yourdomain.com

# Health check script
nano /usr/local/bin/perceptix-health-check.sh
# Set: PERCEPTIX_URL=https://your-actual-domain.com
```

### 3. Configure Environment Variables

```bash
# Edit .env file
nano /home/mignon/gemini/.env

# Set required variables:
# - GEMINI_API_KEY
# - SECRET_KEY
# - CORS_ORIGINS
# - SLACK_WEBHOOK_URL (optional)
```

### 4. Start Services

```bash
# Enable and start Perceptix API
systemctl enable perceptix-api.service
systemctl start perceptix-api.service

# Check status
systemctl status perceptix-api.service

# Test Nginx configuration
nginx -t

# Restart Nginx
systemctl restart nginx
```

### 5. Verify Deployment

```bash
# Check health endpoint
curl https://your-domain.com/health

# Run health check script
/usr/local/bin/perceptix-health-check.sh

# View logs
journalctl -u perceptix-api.service -f
```

## Environment Variables Required

Before deployment, ensure these environment variables are set in `/home/mignon/gemini/.env`:

### Critical (Required)
- `PERCEPTIX_MODE=PRODUCTION`
- `GEMINI_API_KEY=your_key_here`
- `SECRET_KEY=generate_with_openssl_rand_hex_32`

### Recommended
- `CORS_ORIGINS=https://your-domain.com`
- `SLACK_WEBHOOK_URL=https://hooks.slack.com/...` (for notifications)
- `PERCEPTIX_LOG_LEVEL=INFO`

### Optional
- `EMAIL_FROM=...`
- `EMAIL_PASSWORD=...`
- `DB_TYPE=postgresql`
- `DB_NAME=perceptix_db`
- `DB_USER=perceptix_user`

## Security Checklist

Before going live, verify:

- [ ] `.env` file permissions set to `600`
- [ ] UFW firewall enabled and configured
- [ ] SSH key-based authentication enabled
- [ ] Root login disabled
- [ ] SSL certificate installed (Let's Encrypt)
- [ ] Nginx security headers configured
- [ ] Rate limiting enabled
- [ ] Database file permissions restricted
- [ ] Log rotation configured
- [ ] Backups scheduled
- [ ] Health checks configured
- [ ] Fail2ban installed and configured

## Maintenance Commands

### View Logs
```bash
# Application logs
journalctl -u perceptix-api.service -f

# Nginx access logs
tail -f /var/log/nginx/perceptix_access.log

# Nginx error logs
tail -f /var/log/nginx/perceptix_error.log

# Application error logs
tail -f /var/log/gemini/error.log
```

### Restart Services
```bash
# Restart API
systemctl restart perceptix-api.service

# Reload Nginx (no downtime)
nginx -t && systemctl reload nginx

# Full restart
systemctl restart perceptix-api.service nginx
```

### Update Application
```bash
# Use deployment script
sudo -u perceptix /home/mignon/gemini/deploy/scripts/deploy.sh

# Or manual update
cd /home/mignon/gemini
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
systemctl restart perceptix-api.service
```

## Troubleshooting

### Service won't start
```bash
# Check status
systemctl status perceptix-api.service

# View recent logs
journalctl -xe -u perceptix-api.service

# Check configuration
/home/mignon/gemini/venv/bin/gunicorn --check-config api:app
```

### Nginx 502 Bad Gateway
```bash
# Check if backend is running
curl http://127.0.0.1:8000/health

# Check Nginx error log
tail -f /var/log/nginx/perceptix_error.log

# Verify port is listening
netstat -tlnp | grep 8000
```

### Database issues
```bash
# Check integrity
sqlite3 /home/mignon/gemini/data/perceptix_memory.db "PRAGMA integrity_check;"

# Check permissions
ls -la /home/mignon/gemini/data/

# Restore from backup
gunzip -c /home/mignon/gemini/backups/perceptix_memory_20240101_020000.db.gz > /home/mignon/gemini/data/perceptix_memory.db
```

## Performance Tuning

### Adjust Worker Count

Edit `/home/mignon/gemini/gunicorn_config.py`:
```python
# For 2 CPU cores
workers = 5  # (2 * 2) + 1

# For 4 CPU cores
workers = 9  # (4 * 2) + 1
```

Then restart:
```bash
systemctl restart perceptix-api.service
```

### Nginx Caching

For high-traffic deployments, consider adding Nginx caching:
```nginx
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m max_size=100m;

location /api/ {
    proxy_cache api_cache;
    proxy_cache_valid 200 5m;
    proxy_cache_use_stale error timeout updating;
}
```

## Support

For issues or questions:
1. Check the main documentation: `/home/mignon/gemini/PRODUCTION_DEPLOYMENT_GUIDE.md`
2. Review application logs: `journalctl -u perceptix-api.service`
3. Run health checks: `/usr/local/bin/perceptix-health-check.sh`
4. Check DEPLOYMENT.md for application-specific guidance

## License

These deployment scripts are part of the Perceptix project.
