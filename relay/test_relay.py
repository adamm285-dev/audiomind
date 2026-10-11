"""
test_relay.py - Test Suite for Antigravity Standalone Cloud Relay.
Verifies fail-closed authentication, tenant isolation, spoof prevention, and lifecycle validation.
"""
import os
import pytest
from fastapi.testclient import TestClient

from server import app, lifespan
from models import init_db, SessionLocal, AgentDispatch, DEFAULT_TENANT_ID
from agent_dispatch_router import create_signed_token

TEST_SECRET = "super-secret-relay-token-at-least-32-chars-long!"
os.environ["RELAY_AUTH_SECRET"] = TEST_SECRET

client = TestClient(app)

TENANT_A = "tenant_alpha"
TENANT_B = "tenant_bravo"

TOKEN_A = create_signed_token(TENANT_A, TEST_SECRET)
TOKEN_B = create_signed_token(TENANT_B, TEST_SECRET)


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    monkeypatch.setenv("RELAY_AUTH_SECRET", TEST_SECRET)
    init_db()
    db = SessionLocal()
    try:
        db.query(AgentDispatch).delete()
        db.commit()
    finally:
        db.close()


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_dispatch_and_poll_lifecycle():
    auth_headers = {"Authorization": f"Bearer {TOKEN_A}"}

    # 1. Queue an instruction
    resp = client.post(
        "/api/agent/dispatch",
        json={"instruction": "Anti, run unit tests and report results."},
        headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["status"] == "QUEUED"
    dispatch_id = data["dispatch_id"]

    # 2. Desktop polls pending
    poll_resp = client.get("/api/agent/pending", headers=auth_headers)
    assert poll_resp.status_code == 200
    poll_data = poll_resp.json()
    assert poll_data["has_pending"] is True
    assert poll_data["dispatch"]["id"] == dispatch_id
    assert poll_data["dispatch"]["instruction"] == "Anti, run unit tests and report results."

    # 3. Second poll returns empty (already DELIVERED)
    poll_resp2 = client.get("/api/agent/pending", headers=auth_headers)
    assert poll_resp2.status_code == 200
    assert poll_resp2.json()["has_pending"] is False

    # 4. Desktop acknowledges execution
    ack_resp = client.post(
        "/api/agent/ack",
        json={
            "dispatch_id": dispatch_id,
            "status": "EXECUTED",
            "execution_summary": "All 27 unit tests passed cleanly."
        },
        headers=auth_headers
    )
    assert ack_resp.status_code == 200
    assert ack_resp.json()["status"] == "EXECUTED"

    # 5. Check status
    status_resp = client.get(f"/api/agent/status/{dispatch_id}", headers=auth_headers)
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] == "EXECUTED"
    assert status_data["execution_summary"] == "All 27 unit tests passed cleanly."


def test_no_auth_header_returns_401():
    resp = client.post("/api/agent/dispatch", json={"instruction": "Echo test"})
    assert resp.status_code == 401
    assert "Missing authorization header" in resp.json()["detail"]


def test_wrong_token_returns_401():
    resp = client.post(
        "/api/agent/dispatch",
        json={"instruction": "Echo test"},
        headers={"Authorization": "Bearer wrong-forged-token"}
    )
    assert resp.status_code == 401
    assert "Invalid" in resp.json()["detail"] or "unauthorized" in resp.json()["detail"]


def test_tenant_spoofing_prevented():
    """Ensure X-Tenant-Id spoofing cannot access or read another tenant's dispatch."""
    # Tenant A queues a dispatch
    disp_resp = client.post(
        "/api/agent/dispatch",
        json={"instruction": "Secret Tenant A proprietary code review"},
        headers={"Authorization": f"Bearer {TOKEN_A}"}
    )
    assert disp_resp.status_code == 200
    disp_id = disp_resp.json()["dispatch_id"]

    # Tenant B tries to poll pending while spoofing x-tenant-id: tenant_alpha
    spoof_headers = {
        "Authorization": f"Bearer {TOKEN_B}",
        "x-tenant-id": TENANT_A
    }
    poll_resp = client.get("/api/agent/pending", headers=spoof_headers)
    assert poll_resp.status_code == 200
    assert poll_resp.json()["has_pending"] is False

    # Tenant B tries to access Tenant A's status
    status_resp = client.get(f"/api/agent/status/{disp_id}", headers=spoof_headers)
    assert status_resp.status_code == 404
    # Must not echo tenant id in 404
    assert status_resp.json()["detail"] == f"Dispatch '{disp_id}' not found."


def test_ack_state_and_status_validation():
    """Verify that /ack rejects dispatches that are not DELIVERED or have invalid status."""
    auth_headers = {"Authorization": f"Bearer {TOKEN_A}"}

    # Queue dispatch (state = PENDING)
    disp_resp = client.post(
        "/api/agent/dispatch",
        json={"instruction": "Build release"},
        headers=auth_headers
    )
    disp_id = disp_resp.json()["dispatch_id"]

    # Attempting to /ack a PENDING dispatch (not yet DELIVERED) must fail with 400
    early_ack = client.post(
        "/api/agent/ack",
        json={"dispatch_id": disp_id, "status": "EXECUTED"},
        headers=auth_headers
    )
    assert early_ack.status_code == 400
    assert "DELIVERED" in early_ack.json()["detail"]

    # Deliver dispatch via pending poll
    client.get("/api/agent/pending", headers=auth_headers)

    # Attempting to /ack with invalid status must fail with 400
    invalid_status_ack = client.post(
        "/api/agent/ack",
        json={"dispatch_id": disp_id, "status": "UNKNOWN_STATUS"},
        headers=auth_headers
    )
    assert invalid_status_ack.status_code == 400
    assert "Invalid status" in invalid_status_ack.json()["detail"]

    # Valid ACK with FAILED
    valid_ack = client.post(
        "/api/agent/ack",
        json={"dispatch_id": disp_id, "status": "FAILED", "execution_summary": "Compilation error"},
        headers=auth_headers
    )
    assert valid_ack.status_code == 200
    assert valid_ack.json()["status"] == "FAILED"


@pytest.mark.asyncio
async def test_server_refuses_to_start_with_invalid_secret(monkeypatch):
    """Test that lifespan rejects unset or short secrets (<32 chars)."""
    # 1. Unset secret
    monkeypatch.delenv("RELAY_AUTH_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="RELAY_AUTH_SECRET"):
        async with lifespan(app):
            pass

    # 2. Too short secret (< 32 chars)
    monkeypatch.setenv("RELAY_AUTH_SECRET", "short_secret_123")
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        async with lifespan(app):
            pass

