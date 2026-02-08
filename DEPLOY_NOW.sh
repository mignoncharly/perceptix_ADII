#!/bin/bash
# ============================================================================
# PERCEPTIX PRODUCTION DEPLOYMENT - FINAL STEPS
# ============================================================================
# This script completes the deployment setup for Perceptix FastAPI application
# Run this script as the mignon user
# ============================================================================

set -e

echo "============================================================================"
echo "PERCEPTIX PRODUCTION DEPLOYMENT"
echo "============================================================================"
echo ""

# Check if running as correct user
if [ "$(whoami)" != "mignon" ]; then
    echo "ERROR: This script must be run as 'mignon' user"
    exit 1
fi

echo "Step 1: Installing Gunicorn (if not already installed)..."
echo "--------------------------------------------------------------------"
source /home/mignon/gemini/venv/bin/activate
pip install gunicorn uvicorn[standard] -q
echo "✓ Gunicorn installed"
echo ""

echo "Step 2: Installing systemd service file..."
echo "--------------------------------------------------------------------"
sudo cp /tmp/perceptix-api.service /etc/systemd/system/perceptix-api.service
sudo chmod 644 /etc/systemd/system/perceptix-api.service
sudo systemctl daemon-reload
echo "✓ Systemd service installed"
echo ""

echo "Step 3: Installing Nginx configuration..."
echo "--------------------------------------------------------------------"
sudo cp /tmp/nginx-perceptix.conf /etc/nginx/sites-available/perceptix
sudo ln -sf /etc/nginx/sites-available/perceptix /etc/nginx/sites-enabled/perceptix

# Remove broken symlink if exists
if [ -L "/etc/nginx/sites-enabled/gemini" ]; then
    sudo rm /etc/nginx/sites-enabled/gemini
    echo "✓ Removed broken gemini symlink"
fi

sudo nginx -t
echo "✓ Nginx configuration installed and validated"
echo ""

echo "Step 4: Obtaining SSL certificate with Certbot..."
echo "--------------------------------------------------------------------"
echo "You need to run this command manually:"
echo ""
echo "  sudo certbot --nginx -d perceptix.duckdns.org -d www.perceptix.duckdns.org"
echo ""
echo "Press Enter after you've obtained the SSL certificate..."
read -r

echo ""
echo "Step 5: Testing database connection..."
echo "--------------------------------------------------------------------"
python3 <<'PYEOF'
import psycopg2
import os

try:
    conn = psycopg2.connect(
        dbname="perceptix_db",
        user="perceptix_user",
        password="Gemini@!1",
        host="localhost",
        port="5432"
    )
    print("✓ PostgreSQL connection successful")
    conn.close()
except Exception as e:
    print(f"✗ PostgreSQL connection failed: {e}")
    print("Please verify your database is configured correctly")
    exit(1)
PYEOF
echo ""

echo "Step 6: Starting services..."
echo "--------------------------------------------------------------------"
sudo systemctl enable perceptix-api.service
sudo systemctl start perceptix-api.service
sudo systemctl reload nginx
echo "✓ Services started"
echo ""

echo "Step 7: Checking service status..."
echo "--------------------------------------------------------------------"
sleep 3
sudo systemctl status perceptix-api.service --no-pager -l
echo ""

echo "Step 8: Testing API endpoint..."
echo "--------------------------------------------------------------------"
sleep 2
curl -s http://127.0.0.1:8000/health || echo "API not responding yet (wait a moment)"
echo ""

echo "============================================================================"
echo "DEPLOYMENT COMPLETE!"
echo "============================================================================"
echo ""
echo "Your application is now running at:"
echo "  • https://perceptix.duckdns.org"
echo ""
echo "Useful commands:"
echo "  • Check status:   sudo systemctl status perceptix-api"
echo "  • View logs:      sudo journalctl -u perceptix-api -f"
echo "  • Restart:        sudo systemctl restart perceptix-api"
echo "  • Stop:           sudo systemctl stop perceptix-api"
echo ""
echo "Log files:"
echo "  • Application:    /home/mignon/gemini/logs/stdout.log"
echo "  • Errors:         /home/mignon/gemini/logs/stderr.log"
echo "  • Gunicorn:       /home/mignon/gemini/logs/access.log"
echo "  • Nginx:          /var/log/nginx/perceptix-access.log"
echo ""
echo "============================================================================"
