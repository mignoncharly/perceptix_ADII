#!/bin/bash
# ============================================================================
# Perceptix Database Backup Script
# ============================================================================
# This script backs up the Perceptix SQLite databases with compression
# and automatic cleanup of old backups.
#
# Installation:
#   1. Copy to: /usr/local/bin/backup-perceptix-db.sh
#   2. Make executable: chmod +x /usr/local/bin/backup-perceptix-db.sh
#   3. Add to crontab: crontab -u perceptix -e
#      0 2 * * * /usr/local/bin/backup-perceptix-db.sh
# ============================================================================

set -e  # Exit on error

# ============================================================================
# CONFIGURATION
# ============================================================================

# Backup directory
BACKUP_DIR="/home/mignon/gemini/backups"

# Database paths
DB_MAIN="/home/mignon/gemini/data/perceptix_memory.db"
DB_ACKS="/home/mignon/gemini/data/incident_acks.db"
DB_COOLDOWN="/home/mignon/gemini/data/rules_cooldown.db"
DB_TENANTS="/home/mignon/gemini/data/perceptix_tenants.db"

# Retention period (days)
RETENTION_DAYS=30

# Log file
LOG_FILE="/var/log/gemini/backup.log"

# ============================================================================
# FUNCTIONS
# ============================================================================

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

backup_database() {
    local db_path=$1
    local db_name=$(basename "$db_path" .db)
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="$BACKUP_DIR/${db_name}_${timestamp}.db"

    if [ -f "$db_path" ]; then
        log "Backing up $db_name..."

        # Use SQLite backup command for safe backup
        sqlite3 "$db_path" ".backup '$backup_file'"

        # Compress backup
        gzip "$backup_file"

        local compressed_size=$(du -h "${backup_file}.gz" | cut -f1)
        log "Created backup: ${db_name}_${timestamp}.db.gz (${compressed_size})"
    else
        log "Database not found: $db_path (skipping)"
    fi
}

cleanup_old_backups() {
    log "Cleaning up backups older than $RETENTION_DAYS days..."

    local deleted_count=0
    while IFS= read -r file; do
        rm -f "$file"
        deleted_count=$((deleted_count + 1))
        log "Deleted old backup: $(basename "$file")"
    done < <(find "$BACKUP_DIR" -name "*.db.gz" -mtime +$RETENTION_DAYS)

    if [ $deleted_count -eq 0 ]; then
        log "No old backups to delete"
    else
        log "Deleted $deleted_count old backup(s)"
    fi
}

verify_backup() {
    local backup_file=$1

    if [ -f "$backup_file" ]; then
        # Verify gzip integrity
        if gzip -t "$backup_file" 2>/dev/null; then
            log "Backup verification successful: $(basename "$backup_file")"
            return 0
        else
            log "ERROR: Backup verification failed: $(basename "$backup_file")"
            return 1
        fi
    else
        log "ERROR: Backup file not found: $backup_file"
        return 1
    fi
}

# ============================================================================
# MAIN
# ============================================================================

log "============================================================"
log "Starting Perceptix database backup"
log "============================================================"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Check disk space
available_space=$(df -BG "$BACKUP_DIR" | tail -1 | awk '{print $4}' | sed 's/G//')
if [ "$available_space" -lt 1 ]; then
    log "WARNING: Low disk space! Available: ${available_space}GB"
fi

# Backup each database
backup_database "$DB_MAIN"
backup_database "$DB_ACKS"
backup_database "$DB_COOLDOWN"
backup_database "$DB_TENANTS"

# Verify the most recent backups
timestamp=$(date +%Y%m%d_%H%M%S)
verify_backup "$BACKUP_DIR/perceptix_memory_${timestamp}.db.gz" || true

# Cleanup old backups
cleanup_old_backups

# Calculate total backup size
total_size=$(du -sh "$BACKUP_DIR" | cut -f1)
backup_count=$(find "$BACKUP_DIR" -name "*.db.gz" | wc -l)

log "============================================================"
log "Backup completed successfully"
log "Total backups: $backup_count"
log "Total size: $total_size"
log "============================================================"

exit 0
