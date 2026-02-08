#!/bin/bash
# Quick deployment script for Cognizant frontend

set -e

echo "🚀 Deploying Cognizant Frontend to Production"
echo "=============================================="

# Check if dist directory exists
if [ ! -d "dist" ]; then
    echo "❌ Error: dist/ directory not found. Run 'npm run build' first."
    exit 1
fi

# Create web directory if it doesn't exist
echo "📁 Creating web directory..."
sudo mkdir -p /var/www/cognizant
sudo chown -R $USER:$USER /var/www/cognizant

# Copy files
echo "📦 Copying built files..."
cp -r dist/* /var/www/cognizant/

# Verify
echo "✅ Files copied successfully:"
ls -lh /var/www/cognizant/

echo ""
echo "📝 Next steps:"
echo "1. Configure nginx (see DEPLOYMENT.md for full config)"
echo "2. Test nginx config: sudo nginx -t"
echo "3. Reload nginx: sudo systemctl reload nginx"
echo "4. Visit: https://cognizant.duckdns.org/"
echo ""
echo "✨ Frontend files deployed to /var/www/cognizant"
