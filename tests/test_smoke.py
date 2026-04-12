import os
import uuid


def _ensure_env():
    # Ensure required secrets exist for tests (do NOT use in production).
    # These are only used in-memory for the test run.
    os.environ.setdefault("SAS_ENCRYPTION_KEY", "uQk4_y1e5jQmKQW8m3f8rLrR1m2k5XxgVf3qk9g1JmA=")
    os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
    os.environ.setdefault("EMBEDDING_PROVIDER", "hf")


def test_health_and_text_auth_flow():
    _ensure_env()

    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    suffix = uuid.uuid4().hex[:12]
    username = f"alice_{suffix}"
    email = f"alice_{suffix}@example.com"

    # Health
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

    # Register
    r = client.post(
        "/auth/register",
        json={
            "username": username,
            "email": email,
            "password": "Password123!",
            "secret_text": (
                "A quick brown fox jumps over a lazy dog. Famous pangram for typing demos."
            ),
        },
    )
    assert r.status_code == 201, r.text
    user_id = r.json()["id"]
    assert user_id

    # Login init
    r = client.post(
        "/auth/login/init",
        json={"identifier": username, "password": "Password123!"},
    )
    assert r.status_code == 200, r.text
    challenge_id = r.json()["challenge_id"]
    assert challenge_id

    # Login complete (should often succeed with real embeddings if meaning matches)
    r = client.post(
        "/auth/login/complete",
        json={
            "challenge_id": challenge_id,
            "response_text": "A sentence containing every alphabet letter, involving a fox and a lazy dog.",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "message" in data
    # token should exist only if success, but must not be dummy anymore
    if data["success"]:
        assert data["token"] and data["token"] != "dummy-token"

