"""
Metrics Collection and Performance Monitoring
Provides instrumentation for all system components.
"""
import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from collections import defaultdict
from threading import Lock


logger = logging.getLogger("PerceptixMetrics")


class MetricsCollector:
    """
    Collects and aggregates system metrics.
    Thread-safe singleton for metrics collection.
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.metrics: Dict[str, Any] = defaultdict(list)
        self.counters: Dict[str, int] = defaultdict(int)
        self.gauges: Dict[str, float] = {}
        self.timers: Dict[str, list] = defaultdict(list)
        self._lock = Lock()
        self._initialized = True

        logger.info("[METRICS] Collector initialized")

    def increment(self, metric_name: str, value: int = 1, tags: Optional[Dict] = None) -> None:
        """
        Increment a counter metric.

        Args:
            metric_name: Name of the metric
            value: Value to increment by
            tags: Optional tags for the metric
        """
        with self._lock:
            key = self._make_key(metric_name, tags)
            self.counters[key] += value

    def gauge(self, metric_name: str, value: float, tags: Optional[Dict] = None) -> None:
        """
        Set a gauge metric (current value).

        Args:
            metric_name: Name of the metric
            value: Current value
            tags: Optional tags for the metric
        """
        with self._lock:
            key = self._make_key(metric_name, tags)
            self.gauges[key] = value

    def timing(self, metric_name: str, duration_ms: float, tags: Optional[Dict] = None) -> None:
        """
        Record a timing metric.

        Args:
            metric_name: Name of the metric
            duration_ms: Duration in milliseconds
            tags: Optional tags for the metric
        """
        with self._lock:
            key = self._make_key(metric_name, tags)
            self.timers[key].append(duration_ms)

            # Keep only last 100 measurements per metric
            if len(self.timers[key]) > 100:
                self.timers[key] = self.timers[key][-100:]

    def _make_key(self, metric_name: str, tags: Optional[Dict] = None) -> str:
        """Create a metric key with tags."""
        if not tags:
            return metric_name

        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{metric_name}[{tag_str}]"

    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all collected metrics.

        Returns:
            Dict: Metrics summary
        """
        with self._lock:
            summary = {
                "counters": dict(self.counters),
                "gauges": dict(self.gauges),
                "timers": {}
            }

            # Calculate timer statistics
            for key, values in self.timers.items():
                if values:
                    summary["timers"][key] = {
                        "count": len(values),
                        "min": min(values),
                        "max": max(values),
                        "mean": sum(values) / len(values),
                        "p50": self._percentile(values, 50),
                        "p95": self._percentile(values, 95),
                        "p99": self._percentile(values, 99)
                    }

            return summary

    def _percentile(self, values: list, percentile: int) -> float:
        """Calculate percentile of values."""
        if not values:
            return 0.0

        sorted_values = sorted(values)
        index = int((percentile / 100.0) * len(sorted_values))
        index = min(index, len(sorted_values) - 1)
        return sorted_values[index]

    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self.counters.clear()
            self.gauges.clear()
            self.timers.clear()
            logger.info("[METRICS] All metrics reset")

    def export_prometheus(self) -> str:
        """
        Export metrics in Prometheus format.

        Returns:
            str: Prometheus-formatted metrics
        """
        lines = []
        lines.append("# HELP perceptix_metrics System metrics")
        lines.append("# TYPE perceptix_metrics gauge")

        with self._lock:
            # Export counters
            for key, value in self.counters.items():
                safe_key = key.replace("[", "{").replace("]", "}").replace("=", '="') + '"'
                lines.append(f"perceptix_counter_{safe_key} {value}")

            # Export gauges
            for key, value in self.gauges.items():
                safe_key = key.replace("[", "{").replace("]", "}").replace("=", '="') + '"'
                lines.append(f"perceptix_gauge_{safe_key} {value}")

            # Export timer summaries
            for key, values in self.timers.items():
                if values:
                    safe_key = key.replace("[", "{").replace("]", "}").replace("=", '="') + '"'
                    avg = sum(values) / len(values)
                    lines.append(f"perceptix_timing_avg_{safe_key} {avg}")

        return "\n".join(lines)


class Timer:
    """
    Context manager for timing code blocks.

    Example:
        with Timer("operation_name", tags={"component": "observer"}):
            # Code to time
            pass
    """

    def __init__(self, metric_name: str, tags: Optional[Dict] = None,
                 collector: Optional[MetricsCollector] = None):
        """
        Initialize timer.

        Args:
            metric_name: Name of the metric
            tags: Optional tags
            collector: Optional metrics collector (uses singleton if not provided)
        """
        self.metric_name = metric_name
        self.tags = tags
        self.collector = collector or MetricsCollector()
        self.start_time = None
        self.duration_ms = None

    def __enter__(self):
        """Start timing."""
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop timing and record metric."""
        end_time = time.time()
        self.duration_ms = (end_time - self.start_time) * 1000
        self.collector.timing(self.metric_name, self.duration_ms, self.tags)


class SystemMetrics:
    """
    High-level metrics for the Perceptix system.
    Provides convenient methods for common metrics.
    """

    def __init__(self):
        self.collector = MetricsCollector()

    def record_cycle(self, cycle_id: int, duration_ms: float, had_anomaly: bool) -> None:
        """Record a cycle execution."""
        self.collector.increment("cycles_total")
        self.collector.timing("cycle_duration_ms", duration_ms)

        if had_anomaly:
            self.collector.increment("anomalies_detected")

    def record_hypothesis(self, confidence: float, verification_status: str) -> None:
        """Record hypothesis generation and verification."""
        self.collector.increment("hypotheses_generated")
        self.collector.gauge("hypothesis_confidence_last", confidence)
        self.collector.increment(f"verification_status_{verification_status}")

    def record_investigation_step(self, action: str, duration_ms: float, success: bool) -> None:
        """Record investigation step."""
        self.collector.increment(f"investigation_action_{action}")
        self.collector.timing(f"investigation_duration_ms", duration_ms, {"action": action})

        if success:
            self.collector.increment(f"investigation_success_{action}")
        else:
            self.collector.increment(f"investigation_failure_{action}")

    def record_alert(self, channel: str, success: bool, alert_level: str) -> None:
        """Record alert broadcast."""
        self.collector.increment("alerts_total")
        self.collector.increment(f"alert_channel_{channel}")
        self.collector.increment(f"alert_level_{alert_level}")

        if success:
            self.collector.increment(f"alert_success_{channel}")
        else:
            self.collector.increment(f"alert_failure_{channel}")

    def record_error(self, component: str, error_type: str) -> None:
        """Record an error."""
        self.collector.increment("errors_total")
        self.collector.increment(f"error_{component}_{error_type}")

    def record_agent_execution(self, agent: str, duration_ms: float, success: bool, tokens_used: int = 0) -> None:
        """Record an agent execution."""
        self.collector.increment(f"agent_execution_count", tags={"agent": agent})
        self.collector.timing(f"agent_duration_ms", duration_ms, {"agent": agent})
        self.collector.increment("tokens_used_total", value=tokens_used)

        if success:
            self.collector.increment(f"agent_success_count", tags={"agent": agent})
        else:
            self.collector.increment(f"agent_failure_count", tags={"agent": agent})

    def record_system_resources(self) -> None:
        """Record system resource usage."""
        import os
        try:
            # Simple resource collection without external dependencies
            # CPU usage (load average)
            load1, load5, load15 = os.getloadavg()
            self.collector.gauge("system_cpu_load_1m", load1)
            
            # Memory usage (using /proc/meminfo on Linux)
            if os.path.exists("/proc/meminfo"):
                with open("/proc/meminfo", "r") as f:
                    meminfo = f.readlines()
                    total = 0
                    free = 0
                    for line in meminfo:
                        if "MemTotal" in line:
                            total = int(line.split()[1])
                        if "MemAvailable" in line:
                            free = int(line.split()[1])
                    if total > 0:
                        usage = 1.0 - (free / total)
                        self.collector.gauge("system_memory_usage_pct", usage * 100)
        except Exception as e:
            logger.debug(f"Failed to collect system resources: {e}")

    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary."""
        return self.collector.get_summary()


# -------------------------------------------------------------------------
# TERMINAL EXECUTION BLOCK
# -------------------------------------------------------------------------
if __name__ == "__main__":
    print("\n" + "="*70)
    print("METRICS MODULE - STANDALONE TEST")
    print("="*70 + "\n")

    try:
        # Test MetricsCollector
        collector = MetricsCollector()
        print("✓ MetricsCollector initialized")

        # Test counters
        collector.increment("test_counter", 5)
        collector.increment("test_counter", 3)
        print("✓ Counter increments recorded")

        # Test gauges
        collector.gauge("test_gauge", 42.5)
        print("✓ Gauge recorded")

        # Test timers
        for i in range(10):
            collector.timing("test_timer", 100.0 + i * 10)
        print("✓ Timings recorded")

        # Test Timer context manager
        with Timer("test_operation"):
            time.sleep(0.1)
        print("✓ Timer context manager works")

        # Test SystemMetrics
        metrics = SystemMetrics()
        metrics.record_cycle(1, 150.5, True)
        metrics.record_hypothesis(95.0, "CONFIRMED")
        metrics.record_investigation_step("check_git_diff", 50.0, True)
        metrics.record_alert("slack", True, "CRITICAL")
        print("✓ SystemMetrics recording works")

        # Get summary
        summary = collector.get_summary()
        print(f"\n--- Metrics Summary ---")
        print(f"Counters: {len(summary['counters'])}")
        print(f"Gauges: {len(summary['gauges'])}")
        print(f"Timers: {len(summary['timers'])}")

        # Show some examples
        if "test_counter" in summary['counters']:
            print(f"\ntest_counter = {summary['counters']['test_counter']}")

        if "test_timer" in summary['timers']:
            timer_stats = summary['timers']['test_timer']
            print(f"\ntest_timer:")
            print(f"  avg: {timer_stats['avg']:.2f}ms")
            print(f"  p95: {timer_stats['p95']:.2f}ms")

        # Test Prometheus export
        prometheus_output = collector.export_prometheus()
        lines = prometheus_output.split('\n')
        print(f"\nPrometheus export: {len(lines)} lines")

        print("\n" + "="*70)
        print("✓ ALL METRICS TESTS PASSED")
        print("="*70 + "\n")

    except Exception as e:
        print(f"\n✗ METRICS TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
