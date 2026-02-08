import pytest
import time
from main import PerceptixSystem
from config import load_config
from models import SystemMode

@pytest.mark.anyio
async def test_full_system_cycle_mock():
    """
    Test a full cycle from Observation to Escalation in MOCK mode.
    """
    config = load_config()
    config.system.mode = SystemMode.MOCK
    config.system.max_cycles = 10
    config.notification.enabled = False
    config.notification.channels = ["console"]
    
    # PerceptixSystem is NOT an context manager anymore if we removed __enter__/__exit__?
    # Wait, original code used 'with PerceptixSystem(...)'. Did I change that?
    # The __init__ doesn't look like context manager. 
    # But let's check if it has __enter__. If not, use standard init.
    system = PerceptixSystem(config)
    baseline = system.get_metrics_summary()["counters"].copy()
    
    # Run a nominal cycle (it may still detect anomalies based on live sample data).
    await system.run_cycle(cycle_id=1, simulate_failure=False)
    
    # Run an anomalous cycle
    report = await system.run_cycle(cycle_id=2, simulate_failure=True)
    assert report is not None
    assert report.final_confidence_score > 0
    assert report.incident_type is not None
    
    # Check metrics
    summary = system.get_metrics_summary()
    assert summary["counters"]["cycles_total"] >= baseline.get("cycles_total", 0) + 1
    assert summary["counters"]["anomalies_detected"] >= baseline.get("anomalies_detected", 0) + 1
