import pytest
from unittest.mock import MagicMock
from config import load_config
from observer import Observer
from reasoner import CausalReasoner
from agent_loops import Investigator, Verifier
from models import ObservationPackage, SystemState, SystemMode, InvestigationStep

@pytest.fixture
def config():
    return load_config()

def test_observer_initialization(config):
    observer = Observer(config)
    assert observer is not None
    assert observer.component_id == "OBSERVER_V2"

@pytest.mark.anyio
async def test_observer_get_state(config):
    observer = Observer(config)
    state = await observer.get_system_state(simulate_failure=False)
    assert isinstance(state, ObservationPackage)
    assert state.payload is not None
    assert "orders_table" in state.payload.table_metrics

def test_reasoner_mock_mode(config):
    # Force MOCK mode for testing
    config.system.mode = SystemMode.MOCK
    reasoner = CausalReasoner(config)
    
    mock_observation = MagicMock(spec=ObservationPackage)
    mock_observation.payload = MagicMock(spec=SystemState)
    mock_observation.payload.table_metrics = {"orders_table": MagicMock(null_rates={"attribution_source": 0.05})}
    mock_observation.payload.model_dump.return_value = {}
    
    result = reasoner.generate_hypotheses(mock_observation)
    assert result is not None
    assert len(result.reasoning.hypotheses) > 0
    assert result.reasoning.severity_assessment.value == "P3"

@pytest.mark.anyio
async def test_investigator_execution(config):
    investigator = Investigator(config)
    # Mock the tool to avoid real git operations
    investigator._tool_check_git_diff = MagicMock(return_value={
        "tool": "check_git_diff",  # Required field
        "status": "no_relevant_changes",
        "diff": ""
    })
    
    plan = [InvestigationStep(step_id=1, action="check_git_diff", target="test", args={})]
    evidence = await investigator.execute_plan(plan)
    assert len(evidence) == 1
    assert evidence[0].step_id == 1
    assert "no_relevant_changes" in evidence[0].evidence.status
