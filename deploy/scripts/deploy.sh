#!/bin/bash
# ============================================================================
# Perceptix Deployment Script
# ============================================================================
# Automated deployment script for updating the Perceptix application
# on a production server.
#
# Usage:
#   ./deploy.sh [--skip-frontend] [--skip-restart] [--branch BRANCH]
#
# Options:
#   --skip-frontend  Skip frontend build
#   --skip-restart   Skip service restart
#   --branch BRANCH  Deploy specific Git branch (default: main)
# ============================================================================

set -e  # Exit on error

# ============================================================================
# CONFIGURATION
# ============================================================================

APP_DIR="/home/mignon/gemini"
VENV_DIR="$APP_DIR/venv"
FRONTEND_DIR="$APP_DIR/frontend"
STATIC_DIR="/home/mignon/gemini/frontend/dist"
SERVICE_NAME="perceptix-api.service"
LOG_FILE="/var/log/gemini/deploy.log"

# Default options
SKIP_FRONTEND=false
SKIP_RESTART=false
GIT_BRANCH="main"

# ============================================================================
# PARSE ARGUMENTS
# ============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-frontend)
            SKIP_FRONTEND=true
            shift
            ;;
        --skip-restart)
            SKIP_RESTART=true
            shift
            ;;
        --branch)
            GIT_BRANCH="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--skip-frontend] [--skip-restart] [--branch BRANCH]"
            exit 1
            ;;
    esac
done

# ============================================================================
# FUNCTIONS
# ============================================================================

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE" 
}

error() {
    log "ERROR: $1"
    exit 1
}

check_user() {
    if [ "$(whoami)" != "mignon" ] && [ "$(whoami)" != "root" ]; then
        error "This script must be run as 'mignon' user or root"
    fi
}

backup_database() {
    log "Creating database backup..."
    local BACKUP_SCRIPT="$APP_DIR/deploy/scripts/backup-database.sh"
    if [ -f "$BACKUP_SCRIPT" ]; then
        bash "$BACKUP_SCRIPT" || log "Warning: Backup failed"
    else
        log "Warning: Backup script not found at $BACKUP_SCRIPT, skipping backup"
    fi
}

check_git_changes() {
    cd "$APP_DIR"

    # Check if it's a git repository
    if [ ! -d ".git" ]; then
        log "Not a git repository, skipping git checks"
        return 0 # Return 0 so it continues the deployment
    fi

    # Fetch latest changes
    log "Fetching latest changes from Git..."
    if ! git fetch origin 2>/dev/null; then
        log "Warning: Git fetch failed, continuing with local code"
        return 0
    fi

    # Check if there are changes
    local local_commit=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
    local remote_commit=$(git rev-parse origin/$GIT_BRANCH 2>/dev/null || echo "unknown")

    if [ "$local_commit" = "unknown" ] || [ "$remote_commit" = "unknown" ]; then
        log "Cannot determine git status, continuing deployment"
        return 0
    fi

    if [ "$local_commit" = "$remote_commit" ]; then
        log "No git changes detected (at commit $local_commit)"
        # We still return 0 because if the user ran the script, they likely want to redeploy
        return 0
    else
        log "Changes detected: $local_commit -> $remote_commit"
        return 0
    fi
}

update_code() {
    cd "$APP_DIR"

    if [ ! -d ".git" ]; then
        log "Not a git repository, skipping code update"
        return 0
    fi

    log "Pulling latest code from branch: $GIT_BRANCH..."

    # Stash any local changes
    if ! git diff-index --quiet HEAD --; then
        log "Stashing local changes..."
        git stash
    fi

    # Pull latest code
    git checkout "$GIT_BRANCH"
    git pull origin "$GIT_BRANCH"

    log "Code updated to commit: $(git rev-parse --short HEAD)"
}

update_dependencies() {
    log "Updating Python dependencies..."

    cd "$APP_DIR"
    source "$VENV_DIR/bin/activate"

    # Upgrade pip
    pip install --upgrade pip -q

    # Install/update requirements
    pip install -r requirements.txt -q

    log "Dependencies updated"
}

build_frontend() {
    if [ "$SKIP_FRONTEND" = true ]; then
        log "Skipping frontend build (--skip-frontend flag set)"
        return 0
    fi

    log "Building frontend..."

    cd "$FRONTEND_DIR"

    # Install dependencies if needed
    if [ ! -d "node_modules" ] || [ "package.json" -nt "node_modules" ]; then
        log "Installing frontend dependencies..."
        npm ci
    fi

    # Build production bundle
    log "Running production build..."
    npm run build

    # If STATIC_DIR is the same as the build dir, we don't need to copy, 
    # but we might want to ensure permissions.
    if [ "$FRONTEND_DIR/dist" != "$STATIC_DIR" ]; then
        log "Deploying static files to $STATIC_DIR..."
        sudo mkdir -p "$STATIC_DIR"
        sudo cp -r dist/* "$STATIC_DIR/"
    fi
    
    sudo chown -R www-data:www-data "$STATIC_DIR"
    sudo chmod -R 755 "$STATIC_DIR"

    log "Frontend built and deployed"
}

run_migrations() {
    log "Running database migrations..."

    cd "$APP_DIR"
    source "$VENV_DIR/bin/activate"

    # Run database migrations if they exist
    # (Perceptix auto-migrates, but you can add custom migration logic here)
    python << EOF
from database import DatabaseManager
from config import load_config

config = load_config()
db = DatabaseManager(config.database.path, config.database.max_connections)
print("Database schema verified")
EOF

    log "Migrations completed"
}

restart_service() {
    if [ "$SKIP_RESTART" = true ]; then
        log "Skipping service restart (--skip-restart flag set)"
        return 0
    fi

    log "Restarting application service..."

    sudo systemctl restart "$SERVICE_NAME"

    # Wait for service to start
    sleep 3

    # Check service status
    if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
        log "Service restarted successfully"
    else
        error "Service failed to restart!"
    fi
}

reload_nginx() {
    log "Reloading Nginx configuration..."

    # Test configuration first
    if sudo nginx -t 2>&1 | tee -a "$LOG_FILE"; then
        sudo systemctl reload nginx
        log "Nginx reloaded successfully"
    else
        error "Nginx configuration test failed!"
    fi
}

verify_deployment() {
    log "Verifying deployment..."

    # Wait for application to be ready
    sleep 5

    # Check health endpoint
    local health_url="http://127.0.0.1:8001/health"
    local response=$(curl -s -f "$health_url" 2>&1 || echo "FAILED")

    if echo "$response" | grep -q "healthy"; then
        log "Health check passed: $response"
    else
        error "Health check failed: $response"
    fi

    # Check service status
    if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
        log "Service is running"
    else
        error "Service is not running!"
    fi

    log "Deployment verification completed successfully"
}

# ============================================================================
# MAIN DEPLOYMENT FLOW
# ============================================================================

log "============================================================"
log "Starting deployment to $APP_DIR"
log "Branch: $GIT_BRANCH"
log "Skip Frontend: $SKIP_FRONTEND"
log "Skip Restart: $SKIP_RESTART"
log "============================================================"

# Verify running as correct user
check_user

# Create pre-deployment backup
backup_database

# Check for changes
if ! check_git_changes && [ "$SKIP_RESTART" = false ]; then
    log "No deployment needed"
    exit 0
fi

# Update code
update_code

# Update Python dependencies
update_dependencies

# Build frontend
build_frontend

# Run migrations
run_migrations

# Restart service
restart_service

# Reload Nginx
if [ "$SKIP_FRONTEND" = false ]; then
    reload_nginx
fi

# Verify deployment
verify_deployment

# Get current version info
cd "$APP_DIR"
COMMIT_HASH=$(git rev-parse --short HEAD)
COMMIT_MSG=$(git log -1 --pretty=%B)
DEPLOY_TIME=$(date '+%Y-%m-%d %H:%M:%S') 

log "============================================================"
log "Deployment completed successfully!"
log "Commit: $COMMIT_HASH"
log "Message: $COMMIT_MSG"
log "Time: $DEPLOY_TIME"
log "============================================================"

exit 0
