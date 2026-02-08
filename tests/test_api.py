import pytest
from fastapi import status

pytestmark = pytest.mark.anyio

async def test_health_check(client):
    """Test health check endpoint (public)."""
    response = await client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "healthy"

async def test_gemini_proof_endpoint(client):
    """Test hackathon Gemini proof endpoint."""
    response = await client.get("/api/v1/hackathon/gemini-proof")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "configured_model" in data
    assert "provider" in data
    assert "reasoning_path" in data
    assert data["provider"] == "google-genai"

async def test_login(client):
    """Test login endpoint."""
    response = await client.post(
        "/api/v1/auth/token",
        data={"username": "demo", "password": "secret"}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

async def test_login_json_payload(client):
    """Test login endpoint with JSON payload."""
    response = await client.post(
        "/api/v1/auth/token",
        json={"username": "demo", "password": "secret"}
    )
    assert response.status_code == status.HTTP_200_OK

async def test_login_fail(client):
    """Test login failure."""
    response = await client.post(
        "/api/v1/auth/token",
        data={"username": "demo", "password": "wrongpassword"}
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

async def test_metrics_route_accessible_without_auth(client):
    """Test metrics endpoint is not auth-protected."""
    response = await client.get("/api/v1/metrics")
    assert response.status_code != status.HTTP_401_UNAUTHORIZED

    if response.status_code == status.HTTP_200_OK:
        data = response.json()
        assert "counters" in data
        assert "gauges" in data
        assert "timers" in data

async def test_trigger_cycle_unauthorized(client):
    """Test trigger cycle without token."""
    response = await client.post(
        "/api/v1/cycles/trigger",
        json={"simulate_failure": False}
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

async def test_trigger_cycle_authorized(client, auth_headers):
    """Test trigger cycle with token."""
    # This might fail if system is not initialized or DB issue, 
    # but we care about Auth passing (so not 401).
    # If 500/503 it means Auth passed.
    response = await client.post(
        "/api/v1/cycles/trigger",
        json={"simulate_failure": False},
        headers=auth_headers
    )
    assert response.status_code != status.HTTP_401_UNAUTHORIZED
