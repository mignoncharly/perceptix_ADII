"""
Cycle Execution Load Test

Tests system performance under concurrent cycle execution.
"""

from locust import HttpUser, task, between, events
import logging
import time

logger = logging.getLogger(__name__)


class CycleExecutionUser(HttpUser):
    """
    Simulates concurrent cycle executions to test Observer and Reasoner performance.
    """

    wait_time = between(2, 5)

    def on_start(self):
        """Initialize user."""
        self.cycle_count = 0
        self.start_time = time.time()

    @task(1)
    def trigger_and_monitor_cycle(self):
        """Trigger a cycle and monitor its completion."""

        # Trigger cycle
        with self.client.post(
            "/api/v1/cycles/trigger",
            catch_response=True,
            name="POST /api/v1/cycles/trigger"
        ) as response:
            if response.status_code != 200:
                response.failure(f"Failed to trigger cycle: {response.status_code}")
                return

            data = response.json()
            cycle_id = data.get("cycle_id")

            if not cycle_id:
                response.failure("No cycle_id returned")
                return

            response.success()
            self.cycle_count += 1

        # Wait briefly for processing
        time.sleep(0.5)

        # Check if incident was detected
        with self.client.get(
            "/api/v1/incidents?limit=5",
            catch_response=True,
            name="GET /api/v1/incidents (after cycle)"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed to get incidents: {response.status_code}")

    @task(2)
    def check_metrics_during_load(self):
        """Monitor metrics during high load."""
        with self.client.get(
            "/api/v1/metrics",
            catch_response=True,
            name="GET /api/v1/metrics (during load)"
        ) as response:
            if response.status_code == 200:
                data = response.json()

                # Check for performance degradation indicators
                gauges = data.get("gauges", {})
                avg_cycle_time = gauges.get("avg_cycle_duration_seconds", 0)

                if avg_cycle_time > 30:
                    logger.warning(f"High cycle time detected: {avg_cycle_time}s")

                response.success()
            else:
                response.failure(f"Status code: {response.status_code}")

    def on_stop(self):
        """Log statistics when user stops."""
        elapsed = time.time() - self.start_time
        logger.info(f"User completed {self.cycle_count} cycles in {elapsed:.2f}s")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when test starts."""
    logger.info("=== Cycle Load Test Started ===")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when test stops."""
    logger.info("=== Cycle Load Test Completed ===")

    # Log detailed statistics
    stats = environment.stats

    for name, stat in stats.entries.items():
        if "cycle" in name.lower():
            logger.info(f"\n{name}:")
            logger.info(f"  Requests: {stat.num_requests}")
            logger.info(f"  Failures: {stat.num_failures}")
            logger.info(f"  Avg response time: {stat.avg_response_time:.2f}ms")
            logger.info(f"  P50: {stat.get_response_time_percentile(0.5):.2f}ms")
            logger.info(f"  P95: {stat.get_response_time_percentile(0.95):.2f}ms")
            logger.info(f"  P99: {stat.get_response_time_percentile(0.99):.2f}ms")
