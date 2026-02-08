#!/bin/bash
# Configure nginx for Cognizant frontend + backend

set -e

echo "🔧 Configuring Nginx for Cognizant"
echo "===================================="

# Check if running as root or can sudo
if ! sudo -n true 2>/dev/null; then
    echo "This script requires sudo access. You may be prompted for your password."
fi

# Backup existing config if it exists
if [ -f /etc/nginx/sites-available/cognizant ]; then
    echo "📦 Backing up existing nginx config..."
    sudo cp /etc/nginx/sites-available/cognizant /etc/nginx/sites-available/cognizant.backup.$(date +%Y%m%d_%H%M%S)
fi

# Create nginx configuration
echo "📝 Creating nginx configuration..."
sudo tee /etc/nginx/sites-available/cognizant > /dev/null <<'EOF'
# Rate limiting zones
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=health_limit:10m rate=30r/s;

# Upstream backend
upstream cognizant_backend {
    server 127.0.0.1:8001 fail_timeout=10s max_fails=3;
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
EOF

echo "✅ Nginx configuration created"

# Enable the site
echo "🔗 Enabling site..."
sudo ln -sf /etc/nginx/sites-available/cognizant /etc/nginx/sites-enabled/cognizant

# Remove default site if it exists and is enabled
if [ -f /etc/nginx/sites-enabled/default ]; then
    echo "🗑️  Removing default site..."
    sudo rm /etc/nginx/sites-enabled/default
fi

# Test nginx configuration
echo "🧪 Testing nginx configuration..."
if sudo nginx -t; then
    echo "✅ Nginx configuration is valid"

    # Reload nginx
    echo "🔄 Reloading nginx..."
    sudo systemctl reload nginx
    echo "✅ Nginx reloaded successfully"

    echo ""
    echo "🎉 Deployment Complete!"
    echo "======================"
    echo ""
    echo "Your application is now live at:"
    echo "  🌐 https://cognizant.duckdns.org/"
    echo ""
    echo "API endpoints:"
    echo "  📊 API Docs: https://cognizant.duckdns.org/docs"
    echo "  ❤️  Health:  https://cognizant.duckdns.org/health"
    echo "  📈 Metrics:  https://cognizant.duckdns.org/api/v1/metrics"
    echo ""
    echo "To verify:"
    echo "  curl -I https://cognizant.duckdns.org/"
    echo "  curl https://cognizant.duckdns.org/health"
    echo ""
    echo "To view logs:"
    echo "  sudo tail -f /var/log/nginx/cognizant-access.log"
    echo "  sudo tail -f /var/log/nginx/cognizant-error.log"

else
    echo "❌ Nginx configuration test failed!"
    echo "Please check the error messages above and fix the configuration."
    echo "Config file location: /etc/nginx/sites-available/cognizant"
    exit 1
fi
