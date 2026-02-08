"""
Locust Load Testing for Cognizant System

Tests API endpoints under various load conditions.
"""

from locust import HttpUser, task, between, events
from typing import Dict, Any
import json
import logging

logger = logging.getLogger(__name__)


class CognizantAPIUser(HttpUser):
    """
    Simulates a user/service calling Cognizant API endpoints.

    Tests:
    - Health check endpoint
    - Metrics retrieval
    - Incident listing
    - Cycle triggering
    - Rules management
    """

    # Wait 1-3 seconds between tasks
    wait_time = between(1, 3)

    def on_start(self):
        """Called when a simulated user starts."""
        logger.info("Starting Cognizant API user simulation")
        self.incident_ids = []
        self.cycle_ids = []

    @task(10)
    def get_health(self):
        """Check system health (most frequent task)."""
        with self.client.get(
            "/health",
            catch_response=True,
            name="GET /health"
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "healthy":
                    response.success()
                else:
                    response.failure(f"Unhealthy status: {data.get('status')}")
            else:
                response.failure(f"Status code: {response.status_code}")

    @task(8)
    def get_metrics(self):
        """Get system metrics."""
        with self.client.get(
            "/api/v1/metrics",
            catch_response=True,
            name="GET /api/v1/metrics"
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if "counters" in data and "gauges" in data:
                    response.success()
                else:
                    response.failure("Invalid metrics format")
            else:
                response.failure(f"Status code: {response.status_code}")

    @task(5)
    def get_incidents(self):
        """Get recent incidents."""
        with self.client.get(
            "/api/v1/incidents?limit=10",
            catch_response=True,
            name="GET /api/v1/incidents"
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    # Cache incident IDs for later use
                    self.incident_ids = [inc.get('report_id') for inc in data if inc.get('report_id')]
                    response.success()
                else:
                    response.failure("Invalid incidents format")
            else:
                response.failure(f"Status code: {response.status_code}")

    @task(3)
    def get_incident_details(self):
        """Get specific incident details."""
        if not self.incident_ids:
            # Skip if no incidents cached
            return

        incident_id = self.incident_ids[0]
        with self.client.get(
            f"/api/v1/incidents/{incident_id}",
            catch_response=True,
            name="GET /api/v1/incidents/{id}"
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 404:
                # Incident might have been cleaned up
                response.success()
            else:
                response.failure(f"Status code: {response.status_code}")

    @task(2)
    def trigger_cycle(self):
        """Trigger a monitoring cycle."""
        with self.client.post(
            "/api/v1/cycles/trigger",
            catch_response=True,
            name="POST /api/v1/cycles/trigger"
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if "cycle_id" in data:
                    self.cycle_ids.append(data["cycle_id"])
                    response.success()
                else:
                    response.failure("No cycle_id in response")
            else:
                response.failure(f"Status code: {response.status_code}")

    @task(4)
    def get_rules(self):
        """Get alerting rules."""
        with self.client.get(
            "/api/v1/rules",
            catch_response=True,
            name="GET /api/v1/rules"
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    response.success()
                else:
                    response.failure("Invalid rules format")
            else:
                response.failure(f"Status code: {response.status_code}")

    @task(2)
    def get_rules_summary(self):
        """Get rules summary."""
        with self.client.get(
            "/api/v1/rules/summary",
            catch_response=True,
            name="GET /api/v1/rules/summary"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status code: {response.status_code}")

    @task(1)
    def get_system_summary(self):
        """Get system summary."""
        with self.client.get(
            "/api/v1/dashboard/summary",
            catch_response=True,
            name="GET /api/v1/dashboard/summary"
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if "system_health_score" in data:
                    response.success()
                else:
                    response.failure("Invalid summary format")
            else:
                response.failure(f"Status code: {response.status_code}")


class CognizantHighLoadUser(CognizantAPIUser):
    """
    High-load user for stress testing.

    Simulates more aggressive polling with shorter wait times.
    """
    wait_time = between(0.5, 1.5)


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when load test starts."""
    logger.info("=== Cognizant Load Test Started ===")
    logger.info(f"Target host: {environment.host}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when load test stops."""
    logger.info("=== Cognizant Load Test Completed ===")

    # Log summary statistics
    stats = environment.stats
    logger.info(f"Total requests: {stats.total.num_requests}")
    logger.info(f"Total failures: {stats.total.num_failures}")
    logger.info(f"Average response time: {stats.total.avg_response_time:.2f}ms")
    logger.info(f"Max response time: {stats.total.max_response_time:.2f}ms")
    logger.info(f"Requests per second: {stats.total.total_rps:.2f}")
