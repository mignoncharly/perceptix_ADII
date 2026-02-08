#!/bin/bash
# Complete deployment script for Cognizant frontend
# This runs both deploy.sh and configure-nginx.sh

set -e

echo "🚀 Full Cognizant Frontend Deployment"
echo "======================================"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Check if dist directory exists
if [ ! -d "$SCRIPT_DIR/dist" ]; then
    echo "❌ Error: dist/ directory not found."
    echo "Please run 'npm run build' first to create the production build."
    exit 1
fi

# Step 1: Deploy files
echo "Step 1/2: Deploying files to /var/www/cognizant"
echo "------------------------------------------------"
"$SCRIPT_DIR/deploy.sh"

echo ""
echo "Step 2/2: Configuring nginx"
echo "------------------------------------------------"
"$SCRIPT_DIR/configure-nginx.sh"

echo ""
echo "✨ Full deployment complete!"
