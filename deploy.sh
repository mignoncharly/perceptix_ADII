#!/bin/bash
# ============================================================================
# Gemini Deployment Script
# ============================================================================
# Automated deployment script for updating the Gemini application
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
# CONFIGURATION - UPDATED PATHS
# ============================================================================

APP_DIR="/home/mignon/gemini"
VENV_DIR="$APP_DIR/venv"
FRONTEND_DIR="$APP_DIR/frontend"
STATIC_DIR="/var/www/gemini"                # Updated from /var/www/cognizant
SERVICE_NAME="gemini-api.service"          # Updated from cognizant-api.service
LOG_FILE="$APP_DIR/logs/deploy.log"        # Updated from /var/log/gemini/deploy.log
BACKUP_DIR="$APP_DIR/backups"

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

setup_logging() {
    # Ensure log directory exists
    mkdir -p "$(dirname "$LOG_FILE")"
    touch "$LOG_FILE"
    chmod 644 "$LOG_FILE"
}

backup_database() {
    log "Creating database backup..."
    
    # Ensure backup directory exists
    mkdir -p "$BACKUP_DIR"
    
    # Backup PostgreSQL database
    local DATE=$(date +%Y%m%d_%H%M%S)
    local BACKUP_FILE="$BACKUP_DIR/cognizant_db_$DATE.sql"
    
    if command -v pg_dump &> /dev/null; then
        PGPASSWORD='Gemini@!1' pg_dump -h localhost -U cognizant_user -d cognizant_db > "$BACKUP_FILE"
        
        if [ $? -eq 0 ]; then
            gzip -f "$BACKUP_FILE"
            log "PostgreSQL backup created: $BACKUP_FILE.gz"
        else
            log "Warning: PostgreSQL backup failed"
        fi
    else
        log "Warning: pg_dump not found, skipping PostgreSQL backup"
    fi
    
    # Backup SQLite database if exists
    local SQLITE_DB="$APP_DIR/data/cognizant_memory.db"
    if [ -f "$SQLITE_DB" ]; then
        local SQLITE_BACKUP="$BACKUP_DIR/cognizant_memory_$DATE.db"
        sqlite3 "$SQLITE_DB" ".backup '$SQLITE_BACKUP'"
        gzip -f "$SQLITE_BACKUP"
        log "SQLite backup created: $SQLITE_BACKUP.gz"
    fi
    
    # Remove backups older than 30 days
    find "$BACKUP_DIR" -name "*.gz" -mtime +30 -delete
}

check_git_changes() {
    cd "$APP_DIR"

    # Check if it's a git repository
    if [ ! -d ".git" ]; then
        log "Not a git repository, skipping git checks"
        return 0  # Return true to continue deployment
    fi

    # Fetch latest changes
    log "Fetching latest changes from Git..."
    git fetch origin 2>/dev/null || true

    # Check if there are changes
    local local_commit=$(git rev-parse HEAD 2>/dev/null || echo "no-git")
    local remote_commit=$(git rev-parse origin/$GIT_BRANCH 2>/dev/null || echo "no-remote")

    if [ "$local_commit" = "no-git" ] || [ "$remote_commit" = "no-remote" ]; then
        log "Cannot determine git status, continuing deployment"
        return 0
    fi

    if [ "$local_commit" = "$remote_commit" ]; then
        log "No changes detected (already at latest commit: ${local_commit:0:7})"
        return 1
    else
        log "Changes detected: ${local_commit:0:7} -> ${remote_commit:0:7}"
        return 0
    fi
}

update_code() {
    cd "$APP_DIR"

    # Check if it's a git repository
    if [ ! -d ".git" ]; then
        log "Not a git repository, skipping git operations"
        return 0
    fi

    log "Pulling latest code from branch: $GIT_BRANCH..."

    # Stash any local changes
    if ! git diff-index --quiet HEAD -- 2>/dev/null; then
        log "Stashing local changes..."
        git stash
    fi

    # Pull latest code
    git checkout "$GIT_BRANCH" 2>/dev/null || git checkout -b "$GIT_BRANCH"
    git pull origin "$GIT_BRANCH" 2>/dev/null || log "Warning: Git pull failed"

    log "Code updated to commit: $(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
}

update_dependencies() {
    log "Updating Python dependencies..."

    cd "$APP_DIR"
    
    # Check if virtual environment exists
    if [ ! -f "$VENV_DIR/bin/activate" ]; then
        error "Virtual environment not found at $VENV_DIR"
    fi
    
    source "$VENV_DIR/bin/activate"

    # Upgrade pip
    pip install --upgrade pip -q

    # Install/update requirements
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt -q
        log "Dependencies updated from requirements.txt"
    else
        log "Warning: requirements.txt not found"
    fi
}

build_frontend() {
    if [ "$SKIP_FRONTEND" = true ]; then
        log "Skipping frontend build (--skip-frontend flag set)"
        return 0
    fi

    # Check if frontend directory exists
    if [ ! -d "$FRONTEND_DIR" ]; then
        log "Warning: Frontend directory not found at $FRONTEND_DIR"
        return 0
    fi

    log "Building frontend..."

    cd "$FRONTEND_DIR"

    # Check if package.json exists
    if [ ! -f "package.json" ]; then
        log "Warning: package.json not found in frontend directory"
        return 0
    fi

    # Install dependencies if needed
    if [ ! -d "node_modules" ] || [ "package.json" -nt "node_modules" ]; then
        log "Installing frontend dependencies..."
        npm ci 2>&1 | tee -a "$LOG_FILE" || {
            log "Warning: npm ci failed, trying npm install..."
            npm install 2>&1 | tee -a "$LOG_FILE"
        }
    fi

    # Build production bundle
    log "Running production build..."
    npm run build 2>&1 | tee -a "$LOG_FILE"

    # Ensure static directory exists
    sudo mkdir -p "$STATIC_DIR"
    
    # Copy build to static directory
    log "Deploying static files..."
    sudo cp -r dist/* "$STATIC_DIR/"
    sudo chown -R www-data:www-data "$STATIC_DIR"
    sudo chmod -R 755 "$STATIC_DIR"

    log "Frontend built and deployed"
}

run_migrations() {
    log "Running database migrations..."

    cd "$APP_DIR"
    
    # Check if virtual environment exists
    if [ ! -f "$VENV_DIR/bin/activate" ]; then
        log "Warning: Virtual environment not found, skipping migrations"
        return 0
    fi
    
    source "$VENV_DIR/bin/activate"

    # Run database migrations if they exist
    # (Gemini auto-migrates, but you can add custom migration logic here)
    python3 << EOF 2>&1 | tee -a "$LOG_FILE"
from database import DatabaseManager
from config import load_config

try:
    config = load_config()
    db = DatabaseManager(config.database.path, config.database.max_connections)
    print("Database schema verified")
except Exception as e:
    print(f"Warning: Database check failed - {e}")
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
COMMIT_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
DEPLOY_TIME=$(date '+%Y-%m-%d %H:%M:%S') 

log "============================================================"
log "Deployment completed successfully!"
log "Commit: $COMMIT_HASH"
log "Time: $DEPLOY_TIME"
log "============================================================"

exit 0
