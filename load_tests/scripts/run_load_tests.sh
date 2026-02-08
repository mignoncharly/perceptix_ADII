#!/bin/bash

# Load Test Runner Script
# Runs various load test scenarios and generates reports

set -e

REPORTS_DIR="load_tests/reports"
HOST="${COGNIZANT_HOST:-http://localhost:8000}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "=========================================="
echo "Cognizant Load Test Runner"
echo "=========================================="
echo "Target: $HOST"
echo "Reports: $REPORTS_DIR"
echo ""

# Create reports directory
mkdir -p "$REPORTS_DIR"

# Function to run a test scenario
run_test() {
    local name=$1
    local locustfile=$2
    local users=$3
    local spawn_rate=$4
    local duration=$5

    echo -e "${YELLOW}Running: $name${NC}"
    echo "  Users: $users | Spawn rate: $spawn_rate/s | Duration: ${duration}s"

    locust \
        -f "$locustfile" \
        --host="$HOST" \
        --users="$users" \
        --spawn-rate="$spawn_rate" \
        --run-time="${duration}s" \
        --headless \
        --html="$REPORTS_DIR/${name}_report.html" \
        --csv="$REPORTS_DIR/${name}_stats" \
        --loglevel=INFO

    echo -e "${GREEN}✓ Completed: $name${NC}"
    echo ""
}

# Test 1: Steady State Load
echo -e "${YELLOW}=== Test 1: Steady State Load ===${NC}"
run_test "steady_state" \
    "load_tests/locustfile.py" \
    10 \
    2 \
    60

# Test 2: Spike Test
echo -e "${YELLOW}=== Test 2: Spike Test ===${NC}"
run_test "spike_test" \
    "load_tests/locustfile.py" \
    50 \
    10 \
    30

# Test 3: Cycle Execution Load
echo -e "${YELLOW}=== Test 3: Cycle Execution Load ===${NC}"
run_test "cycle_load" \
    "load_tests/scenarios/cycle_load_test.py" \
    20 \
    5 \
    90

# Test 4: Concurrent Incidents
echo -e "${YELLOW}=== Test 4: Concurrent Incidents ===${NC}"
run_test "concurrent_incidents" \
    "load_tests/scenarios/concurrent_incidents_test.py" \
    15 \
    3 \
    60

# Test 5: Endurance Test
echo -e "${YELLOW}=== Test 5: Endurance Test ===${NC}"
run_test "endurance" \
    "load_tests/locustfile.py" \
    5 \
    1 \
    300

# Generate analysis reports
echo -e "${YELLOW}=== Generating Analysis Reports ===${NC}"

for test in steady_state spike_test cycle_load concurrent_incidents endurance; do
    if [ -f "$REPORTS_DIR/${test}_stats_stats_history.csv" ]; then
        echo "Analyzing: $test"
        python load_tests/scripts/analyze_results.py \
            "$REPORTS_DIR/${test}_stats_stats_history.csv" \
            "$REPORTS_DIR/${test}_analysis.json" > "$REPORTS_DIR/${test}_analysis.txt"
    fi
done

echo -e "${GREEN}=== All Load Tests Complete ===${NC}"
echo ""
echo "Reports saved to: $REPORTS_DIR"
echo ""
echo "Summary:"
ls -lh "$REPORTS_DIR"/*.html 2>/dev/null || echo "No HTML reports found"
