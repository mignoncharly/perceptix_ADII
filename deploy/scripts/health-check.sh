#!/bin/bash
# ============================================================================
# Perceptix Health Check Script
# ============================================================================
# This script performs health checks on the Perceptix application
# and can be used for monitoring and alerting.
#
# Installation:
#   1. Copy to: /usr/local/bin/perceptix-health-check.sh
#   2. Make executable: chmod +x /usr/local/bin/perceptix-health-check.sh
#   3. Add to crontab: crontab -e
#      */5 * * * * /usr/local/bin/perceptix-health-check.sh
# ============================================================================

set -e

# ============================================================================
# CONFIGURATION
# ============================================================================

# CHANGE THIS to your actual domain or IP
API_URL="${PERCEPTIX_URL:-https://perceptix.yourdomain.com}"

# Health check endpoints
HEALTH_ENDPOINT="$API_URL/health"
READY_ENDPOINT="$API_URL/health/ready"

# Expected responses
EXPECTED_STATUS="healthy"

# Log file
LOG_FILE="/var/log/gemini/health-check.log"

# Alert thresholds
MAX_RESPONSE_TIME=5  # seconds
MAX_FAILURES=3

# Alert webhook (optional - Slack webhook URL)
ALERT_WEBHOOK="${SLACK_WEBHOOK_URL:-}"

# State file for tracking consecutive failures
STATE_FILE="/tmp/perceptix-health-state"

# ============================================================================
# FUNCTIONS
# ============================================================================

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

send_alert() {
    local message=$1
    local level=${2:-warning}

    log "$level: $message"

    # Send Slack alert if webhook is configured
    if [ -n "$ALERT_WEBHOOK" ]; then
        local emoji
        case $level in
            critical) emoji=":rotating_light:" ;;
            warning) emoji=":warning:" ;;
            info) emoji=":information_source:" ;;
            *) emoji=":white_check_mark:" ;;
        esac

        curl -X POST "$ALERT_WEBHOOK" \
            -H 'Content-Type: application/json' \
            -d "{\"text\": \"$emoji Perceptix Health Check: $message\"}" \
            --silent --output /dev/null || true
    fi
}

get_failure_count() {
    if [ -f "$STATE_FILE" ]; then
        cat "$STATE_FILE"
    else
        echo "0"
    fi
}

increment_failure_count() {
    local count=$(get_failure_count)
    count=$((count + 1))
    echo "$count" > "$STATE_FILE"
    echo "$count"
}

reset_failure_count() {
    echo "0" > "$STATE_FILE"
}

check_endpoint() {
    local endpoint=$1
    local start_time=$(date +%s)

    # Perform health check with timeout
    local response=$(curl -s -f -m "$MAX_RESPONSE_TIME" "$endpoint" 2>&1 || echo "FAILED")

    local end_time=$(date +%s)
    local response_time=$((end_time - start_time))

    # Check if response is successful
    if echo "$response" | grep -q "$EXPECTED_STATUS"; then
        log "OK: $endpoint responded in ${response_time}s"
        return 0
    else
        log "FAILED: $endpoint - Response: $response"
        return 1
    fi
}

check_service_status() {
    # Check if systemd service is running
    if systemctl is-active --quiet perceptix-api.service; then
        log "Service status: RUNNING"
        return 0
    else
        log "Service status: STOPPED or FAILED"
        return 1
    fi
}

check_disk_space() {
    local data_dir="/home/mignon/gemini/data"
    local threshold=90  # Alert if disk usage > 90%

    local usage=$(df "$data_dir" | tail -1 | awk '{print $5}' | sed 's/%//')

    if [ "$usage" -gt "$threshold" ]; then
        send_alert "Disk usage critical: ${usage}% (threshold: ${threshold}%)" "critical"
        return 1
    else
        log "Disk usage: ${usage}%"
        return 0
    fi
}

check_database() {
    local db_path="/home/mignon/gemini/data/perceptix_memory.db"

    if [ -f "$db_path" ]; then
        # Check database integrity
        if sqlite3 "$db_path" "PRAGMA integrity_check;" | grep -q "ok"; then
            log "Database integrity: OK"
            return 0
        else
            log "Database integrity: FAILED"
            send_alert "Database integrity check failed!" "critical"
            return 1
        fi
    else
        log "Database not found: $db_path"
        send_alert "Database file missing!" "critical"
        return 1
    fi
}

check_log_errors() {
    local error_log="/var/log/gemini/error.log"
    local time_window="5 minutes"

    # Count recent errors (last 5 minutes)
    local error_count=0
    if [ -f "$error_log" ]; then
        error_count=$(find "$error_log" -mmin -5 -exec grep -c "ERROR\|CRITICAL" {} \; 2>/dev/null || echo "0")
    fi

    if [ "$error_count" -gt 10 ]; then
        send_alert "$error_count errors in last $time_window" "warning"
        return 1
    else
        log "Recent errors: $error_count (last $time_window)"
        return 0
    fi
}

# ============================================================================
# MAIN
# ============================================================================

log "Starting health check..."

# Initialize exit code
exit_code=0

# Check systemd service status
if ! check_service_status; then
    send_alert "Perceptix API service is not running!" "critical"
    exit_code=2
fi

# Check health endpoint
if check_endpoint "$HEALTH_ENDPOINT"; then
    # Success - reset failure counter
    reset_failure_count
else
    # Failure - increment counter
    failure_count=$(increment_failure_count)

    if [ "$failure_count" -ge "$MAX_FAILURES" ]; then
        send_alert "Health check failed $failure_count consecutive times!" "critical"
        exit_code=2
    else
        log "Health check failed (attempt $failure_count/$MAX_FAILURES)"
        exit_code=1
    fi
fi

# Check readiness endpoint
if ! check_endpoint "$READY_ENDPOINT"; then
    send_alert "Readiness check failed" "warning"
    exit_code=1
fi

# Additional checks
check_disk_space || exit_code=1
check_database || exit_code=2
check_log_errors || exit_code=1

# Summary
if [ $exit_code -eq 0 ]; then
    log "Health check completed: ALL CHECKS PASSED"
elif [ $exit_code -eq 1 ]; then
    log "Health check completed: WARNINGS DETECTED"
else
    log "Health check completed: CRITICAL ISSUES DETECTED"
fi

exit $exit_code
