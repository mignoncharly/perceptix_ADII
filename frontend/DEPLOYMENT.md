# Production Deployment Guide

## Prerequisites

- Frontend built (`npm run build` completed)
- Nginx installed and running
- SSL certificate configured for cognizant.duckdns.org
- Backend API running on port 8001

## Quick Deployment (Automated)

For a complete automated deployment, run:

```bash
./full-deploy.sh
```

This script will:
1. Copy built files to `/var/www/cognizant`
2. Configure nginx with the production settings
3. Test and reload nginx
4. Display verification commands

Or run the steps individually:
```bash
./deploy.sh              # Step 1: Copy files
./configure-nginx.sh     # Step 2: Configure nginx
```

## Manual Deployment Steps

If you prefer to deploy manually, follow these steps:

### 1. Create Web Directory

```bash
sudo mkdir -p /var/www/cognizant
sudo chown -R $USER:$USER /var/www/cognizant 
```

### 2. Copy Built Files

```bash
# From the frontend directory
cp -r dist/* /var/www/cognizant/
```

Verify files are in place:
```bash
ls -la /var/www/cognizant/
# Should show: index.html, assets/, etc.
```

### 3. Configure Nginx

Create or update nginx configuration at `/etc/nginx/sites-available/cognizant`:

```nginx
# Rate limiting zones
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=health_limit:10m rate=30r/s;

# Upstream backend
upstream cognizant_backend {
    server 127.0.0.1:8000 fail_timeout=10s max_fails=3;
    keepalive 32;
}

# HTTP to HTTPS redirect
server {
    listen 80;
    listen [::]:80;
    server_name cognizant.duckdns.org;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name cognizant.duckdns.org;

    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/cognizant.duckdns.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/cognizant.duckdns.org/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/cognizant.duckdns.org/chain.pem;

    # SSL Security
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_stapling on;
    ssl_stapling_verify on;

    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Logging
    access_log /var/log/nginx/cognizant-access.log;
    error_log /var/log/nginx/cognizant-error.log warn;

    # Frontend root directory
    root /var/www/cognizant;
    index index.html;

    # Max body size
    client_max_body_size 10M;

    # Timeouts
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 120s;

    # API Health check endpoint
    location /health {
        limit_req zone=health_limit burst=10 nodelay;

        proxy_pass http://cognizant_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        access_log off;
    }

    # API endpoints - proxy to backend
    location /api {
        limit_req zone=api_limit burst=20 nodelay;

        proxy_pass http://cognizant_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Metrics endpoint
    location /metrics {
        proxy_pass http://cognizant_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # API Docs
    location ~ ^/(docs|redoc|openapi.json) {
        proxy_pass http://cognizant_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket support
    location /ws {
        proxy_pass http://cognizant_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }

    # Static assets with caching
    location /assets {
        expires 1y;
        add_header Cache-Control "public, immutable";
        try_files $uri =404;
    }

    # Frontend - SPA routing (must be last)
    # All other requests serve index.html for client-side routing
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

### 4. Enable and Test Configuration

```bash
# Enable the site (if using sites-available/sites-enabled)
sudo ln -sf /etc/nginx/sites-available/cognizant /etc/nginx/sites-enabled/

# Test nginx configuration
sudo nginx -t

# If test passes, reload nginx
sudo systemctl reload nginx
```

### 5. Verify Deployment

```bash
# Check frontend is accessible
curl -I https://cognizant.duckdns.org/

# Check API is still working
curl https://cognizant.duckdns.org/health

# Check API endpoints
curl https://cognizant.duckdns.org/api/v1/metrics
```

## Environment Configuration

If your frontend needs to know the API URL at runtime, you may need to:

1. **Use relative URLs** (recommended - already configured in vite.config.ts proxy)
   - Frontend makes requests to `/api/*` which nginx proxies to backend

2. **Or use environment variables at build time**:
   ```bash
   # Create .env.production
   echo "VITE_API_URL=https://cognizant.duckdns.org" > .env.production

   # Rebuild
   npm run build

   # Redeploy
   cp -r dist/* /var/www/cognizant/
   ```

## Updates and Redeployment

When you make changes to the frontend:

```bash
# 1. Rebuild
npm run build

# 2. Redeploy
cp -r dist/* /var/www/cognizant/

# 3. Clear browser cache or do hard refresh (Ctrl+Shift+R)
```

No nginx reload needed for frontend updates (only for config changes).

## Troubleshooting

### 404 on page refresh
- Ensure `try_files $uri $uri/ /index.html;` is in the nginx config
- This allows React Router to handle all routes

### API calls failing
- Check nginx error logs: `sudo tail -f /var/log/nginx/cognizant-error.log`
- Verify backend is running: `curl http://localhost:8000/health`
- Check proxy settings in nginx config

### Static assets not loading
- Verify files exist: `ls -la /var/www/cognizant/assets/`
- Check file permissions: `sudo chown -R www-data:www-data /var/www/cognizant`
- Check nginx error logs

### WebSocket not connecting
- Verify `/ws` location block has `Upgrade` headers
- Check browser console for WebSocket errors
- Test WebSocket: `wscat -c wss://cognizant.duckdns.org/ws/incidents`

## Security Checklist

- [ ] HTTPS enabled with valid SSL certificate
- [ ] HTTP redirects to HTTPS
- [ ] Security headers configured
- [ ] Rate limiting enabled for API endpoints
- [ ] File permissions set correctly (644 for files, 755 for directories)
- [ ] Backend not directly accessible from internet
- [ ] CORS configured properly in backend
- [ ] CSP headers considered (optional but recommended)

## Performance Optimization

The build process already includes:
- Code splitting (separate chunks for React, MUI, Charts)
- Minification
- Tree shaking
- Asset optimization

Nginx configuration includes:
- Gzip compression (if enabled in main nginx.conf)
- Cache headers for static assets (1 year)
- HTTP/2 support
- Keep-alive connections

## Monitoring

Monitor the application:
```bash
# Nginx access logs
sudo tail -f /var/log/nginx/cognizant-access.log

# Nginx error logs
sudo tail -f /var/log/nginx/cognizant-error.log

# Check nginx status
sudo systemctl status nginx

# Check backend status
curl https://cognizant.duckdns.org/health
```
