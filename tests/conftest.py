import pytest
import httpx
from api import app, lifespan
from config import load_config, PerceptixConfig, SystemConfig, DatabaseConfig
from auth import create_access_token

@pytest.fixture
async def client():
    """Async API client with explicit lifespan management."""
    async with lifespan(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client

@pytest.fixture
def auth_token():
    """Generate a valid auth token for testing."""
    return create_access_token(data={"sub": "testuser"})

@pytest.fixture
def auth_headers(auth_token):
    """Return headers with valid auth token."""
    return {"Authorization": f"Bearer {auth_token}"}

@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    config = load_config()
    config.system.mode = "TEST"
    return config
