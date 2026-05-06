import os
import time
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

    # Registration greeting preview
    r = client.post(
        "/auth/register/preview-greeting-image",
        json={"image_text": "A fox silhouette over a lazy dog under moonlight."},
    )
    assert r.status_code == 200, r.text
    assert (r.headers.get("content-type") or "").startswith("image/")

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
            "image_text": "A fox silhouette over a lazy dog under moonlight.",
        },
    )
    assert r.status_code == 201, r.text
    user_id = r.json()["id"]
    assert user_id

    # Login init (image/gallery prep is async now; poll briefly until ready)
    r = None
    for _ in range(30):
        r = client.post(
            "/auth/login/init",
            json={"identifier": username, "password": "Password123!"},
        )
        if r.status_code == 200:
            break
        if r.status_code == 503 and "still being prepared" in r.text.lower():
            time.sleep(1)
            continue
        break
    assert r is not None
    assert r.status_code == 200, r.text
    init_data = r.json()
    challenge_id = init_data["challenge_id"]
    assert challenge_id
    assert len(init_data.get("greeting_gallery_urls") or []) == 6

    from app.db import SessionLocal
    from app import models

    sess = SessionLocal()
    try:
        target = (
            sess.query(models.LoginChallengeGallerySlot)
            .filter(
                models.LoginChallengeGallerySlot.challenge_id == challenge_id,
                models.LoginChallengeGallerySlot.is_target.is_(True),
            )
            .one()
        )
        good_slot = target.slot
    finally:
        sess.close()

    r = client.post(
        f"/auth/login/challenge/{challenge_id}/pick-greeting-image",
        json={"selected_slot": good_slot},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("success") is True

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

    # Switch to image-only and verify pick can complete login directly.
    from app.db import SessionLocal
    from app import models
    sess = SessionLocal()
    try:
        user = sess.query(models.User).filter(models.User.id == user_id).one()
        user.login_mode = models.LoginMode.IMAGE_ONLY
        sess.commit()
    finally:
        sess.close()

    r = None
    for _ in range(30):
        r = client.post(
            "/auth/login/init",
            json={"identifier": username, "password": "Password123!"},
        )
        if r.status_code == 200:
            break
        if r.status_code == 503 and "still being prepared" in r.text.lower():
            time.sleep(1)
            continue
        break
    assert r is not None
    assert r.status_code == 200, r.text
    init_data = r.json()
    assert init_data.get("semantic_required") is False
    challenge_id = init_data["challenge_id"]

    sess = SessionLocal()
    try:
        target = (
            sess.query(models.LoginChallengeGallerySlot)
            .filter(
                models.LoginChallengeGallerySlot.challenge_id == challenge_id,
                models.LoginChallengeGallerySlot.is_target.is_(True),
            )
            .one()
        )
        good_slot = target.slot
    finally:
        sess.close()

    r = client.post(
        f"/auth/login/challenge/{challenge_id}/pick-greeting-image",
        json={"selected_slot": good_slot},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("success") is True
    assert r.json().get("token")

