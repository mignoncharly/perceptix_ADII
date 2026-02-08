"""
Concurrent Incidents Load Test

Tests Historian and Escalator performance with concurrent incident creation.
"""

from locust import HttpUser, task, between, events
import logging
import random

logger = logging.getLogger(__name__)


class IncidentManagementUser(HttpUser):
    """
    Simulates concurrent incident creation and retrieval.
    Tests Historian write performance and Escalator notification handling.
    """

    wait_time = between(1, 3)

    def on_start(self):
        """Initialize user."""
        self.created_incidents = []

    @task(3)
    def get_recent_incidents(self):
        """Retrieve recent incidents."""
        limit = random.choice([5, 10, 20])

        with self.client.get(
            f"/api/v1/incidents?limit={limit}",
            catch_response=True,
            name="GET /api/v1/incidents (various limits)"
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    self.created_incidents = [inc.get('report_id') for inc in data if inc.get('report_id')]
                    response.success()
                else:
                    response.failure("Invalid response format")
            else:
                response.failure(f"Status code: {response.status_code}")

    @task(2)
    def get_incident_details(self):
        """Get details of specific incidents."""
        if not self.created_incidents:
            return

        incident_id = random.choice(self.created_incidents)

        with self.client.get(
            f"/api/v1/incidents/{incident_id}",
            catch_response=True,
            name="GET /api/v1/incidents/{id}"
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 404:
                # Incident cleaned up
                response.success()
            else:
                response.failure(f"Status code: {response.status_code}")

    @task(1)
    def trigger_cycle_with_failure(self):
        """
        Trigger cycle to create incidents.

        Note: This requires the system to support failure simulation,
        or we rely on natural anomaly detection.
        """
        with self.client.post(
            "/api/v1/cycles/trigger",
            catch_response=True,
            name="POST /api/v1/cycles/trigger (incident creation)"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status code: {response.status_code}")

    @task(2)
    def get_incidents_by_type(self):
        """Test incident filtering (if supported)."""
        with self.client.get(
            "/api/v1/incidents?limit=10",
            catch_response=True,
            name="GET /api/v1/incidents (filtered)"
        ) as response:
            if response.status_code == 200:
                data = response.json()

                # Analyze incident types
                if isinstance(data, list) and data:
                    types = {}
                    for inc in data:
                        inc_type = inc.get('incident_type', 'UNKNOWN')
                        types[inc_type] = types.get(inc_type, 0) + 1

                    logger.debug(f"Incident type distribution: {types}")

                response.success()
            else:
                response.failure(f"Status code: {response.status_code}")

    @task(1)
    def check_historian_health(self):
        """Monitor Historian health during load."""
        with self.client.get(
            "/api/v1/metrics",
            catch_response=True,
            name="GET /api/v1/metrics (historian check)"
        ) as response:
            if response.status_code == 200:
                data = response.json()
                counters = data.get("counters", {})

                # Check incident counts
                total_incidents = counters.get("incidents_total", 0)
                if total_incidents > 0:
                    logger.debug(f"Total incidents in system: {total_incidents}")

                response.success()
            else:
                response.failure(f"Status code: {response.status_code}")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when test starts."""
    logger.info("=== Concurrent Incidents Load Test Started ===")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when test stops."""
    logger.info("=== Concurrent Incidents Load Test Completed ===")

    stats = environment.stats

    # Log incident-related endpoint statistics
    for name, stat in stats.entries.items():
        if "incident" in name.lower():
            logger.info(f"\n{name}:")
            logger.info(f"  Total requests: {stat.num_requests}")
            logger.info(f"  Failures: {stat.num_failures}")
            logger.info(f"  Failure rate: {stat.fail_ratio * 100:.2f}%")
            logger.info(f"  Avg response time: {stat.avg_response_time:.2f}ms")
            logger.info(f"  P95 response time: {stat.get_response_time_percentile(0.95):.2f}ms")
            logger.info(f"  RPS: {stat.total_rps:.2f}")
