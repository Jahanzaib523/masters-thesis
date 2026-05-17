from datetime import datetime, timedelta
import concurrent.futures
import json
import logging
import secrets
import hashlib
import time
import re
from threading import Thread
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import settings
from ..db import SessionLocal, get_db
from ..security import encrypt_embedding, decrypt_embedding, encrypt_text, decrypt_text
from ..semantic import semantic_service, vector_to_bytes, bytes_to_vector
from ..groq_client import synthesize_speech, transcribe_audio
from ..llm_provider import SemanticLlmBackend, get_semantic_llm_backend
from ..semantic_llm import generate_semantic_summary, generate_text_with_prompt, score_semantic_similarity
from ..passwords import hash_password, verify_password
from ..tokens import create_access_token, create_signed_token, decode_access_token
from ..greeting_image import generate_decoy_greeting_image, generate_greeting_image

router = APIRouter()
logger = logging.getLogger("sas.auth")
security = HTTPBearer(auto_error=False)


def _generate_greeting_image_with_retry(image_text: str, max_attempts: int = 3) -> tuple[bytes, str, int, str]:
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return generate_greeting_image(image_text)
        except Exception as exc:
            last_exc = exc
            if attempt >= max_attempts:
                break
            # Short exponential backoff with jitter-ish stagger.
            time.sleep(0.8 * attempt)
    raise RuntimeError(f"Greeting image generation failed after {max_attempts} attempts: {last_exc}") from last_exc


def _generate_single_decoy_with_retry(
    user_id: int,
    decoy_index: int,
    decoy_text: str,
    max_attempts: int = 3,
) -> tuple[int, tuple[bytes, str]]:
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return decoy_index, generate_decoy_greeting_image(f"user-{user_id}", decoy_index, decoy_text)
        except Exception as exc:
            last_exc = exc
            if attempt >= max_attempts:
                break
            time.sleep(0.8 * attempt)
    raise RuntimeError(
        f"Decoy generation failed for user={user_id} decoy_index={decoy_index} after {max_attempts} attempts: {last_exc}"
    ) from last_exc


def _rebuild_user_gallery_pool(
    db: Session,
    user: models.User,
    llm_backend: SemanticLlmBackend,
) -> None:
    """Rebuild the user's pre-generated image gallery."""
    real_b = user.greeting_image_bytes
    real_m = user.greeting_image_mime or "image/png"
    if not real_b:
        raise ValueError("User has no security greeting image.")

    try:
        decoy_texts = _build_decoy_image_texts(user.id, llm_backend)
        if len(decoy_texts) != 5:
            decoy_texts = _fallback_decoy_texts()
        workers = min(5, max(2, len(decoy_texts)))
        decoys_by_index: dict[int, tuple[bytes, str]] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(_generate_single_decoy_with_retry, user.id, i, decoy_text)
                for i, decoy_text in enumerate(decoy_texts)
            ]
            for future in concurrent.futures.as_completed(futures):
                idx, decoy = future.result()
                decoys_by_index[idx] = decoy
        decoys = [decoys_by_index[i] for i in range(len(decoy_texts))]
    except Exception as exc:
        logger.exception("user gallery pool: decoy generation failed user_id=%s", user.id)
        raise RuntimeError(f"Could not generate gallery pool for user {user.id}. ({exc})") from exc

    db.query(models.UserGalleryPoolSlot).filter(
        models.UserGalleryPoolSlot.user_id == user.id
    ).delete(synchronize_session=False)
    correct_slot = secrets.randbelow(6)
    decoy_i = 0
    for slot in range(6):
        if slot == correct_slot:
            b, m, is_target = real_b, real_m, True
        else:
            b, m = decoys[decoy_i]
            decoy_i += 1
            is_target = False
        db.add(
            models.UserGalleryPoolSlot(
                user_id=user.id,
                slot=slot,
                image_bytes=b,
                image_mime=m,
                is_target=is_target,
            )
        )
    db.commit()


def _get_user_gallery_pool(
    db: Session,
    user_id: int,
) -> list[models.UserGalleryPoolSlot]:
    return (
        db.query(models.UserGalleryPoolSlot)
        .filter(models.UserGalleryPoolSlot.user_id == user_id)
        .order_by(models.UserGalleryPoolSlot.slot.asc())
        .all()
    )


def _populate_login_challenge_gallery_from_pool(
    db: Session,
    challenge: models.LoginChallenge,
    pool_rows: list[models.UserGalleryPoolSlot],
) -> None:
    if len(pool_rows) != 6:
        raise ValueError("Security gallery is unavailable for this account.")
    for row in pool_rows:
        db.add(
            models.LoginChallengeGallerySlot(
                challenge_id=challenge.id,
                slot=row.slot,
                image_bytes=row.image_bytes,
                image_mime=row.image_mime,
                is_target=row.is_target,
            )
        )
    db.commit()


def _refresh_user_gallery_pool_async(user_id: int, llm_backend: SemanticLlmBackend) -> None:
    """Fire off a background job to rebuild the user's gallery after they log in."""
    def _job() -> None:
        db = SessionLocal()
        try:
            user = db.query(models.User).filter(models.User.id == user_id).first()
            if not user:
                return
            _rebuild_user_gallery_pool(db, user, llm_backend)
            logger.info("user gallery pool refreshed user_id=%s", user_id)
        except Exception:
            logger.exception("user gallery pool refresh failed user_id=%s", user_id)
        finally:
            db.close()

    Thread(target=_job, daemon=True).start()


def _generate_user_security_image_sync_and_async(
    user: models.User,
    db: Session,
    image_text: str,
    llm_backend: SemanticLlmBackend,
) -> None:
    """Generate the main image right away, then spin up the 5 decoys in the background."""
    image_text = (image_text or "").strip()
    if not image_text:
        return

    # 1. Generate the main image so the user sees it immediately
    try:
        image_bytes, image_mime, seed, prompt_hash = _generate_greeting_image_with_retry(image_text)
        user.greeting_image_path = None
        user.greeting_image_bytes = image_bytes
        user.greeting_image_mime = image_mime
        user.greeting_seed = seed
        user.greeting_prompt_hash = prompt_hash
        user.greeting_model_name = settings.image_model
        
        # 2. Wipe the old gallery to make room for the new ones
        db.query(models.UserGalleryPoolSlot).filter(models.UserGalleryPoolSlot.user_id == user.id).delete()
        
        db.commit()
        db.refresh(user)
        logger.info("user security image generated synchronously user_id=%s", user.id)
    except Exception:
        logger.exception("user security image sync generation failed user_id=%s", user.id)
        return

    user_id = user.id

    # 3. Kick off the decoy generation in the background
    def _job() -> None:
        local_db = SessionLocal()
        try:
            local_user = local_db.query(models.User).filter(models.User.id == user_id).first()
            if not local_user:
                return
            _rebuild_user_gallery_pool(local_db, local_user, llm_backend)
            logger.info("user security gallery pool generated user_id=%s", user_id)
        except Exception:
            logger.exception("user security gallery pool generation failed user_id=%s", user_id)
        finally:
            local_db.close()

    Thread(target=_job, daemon=True).start()


def _text_signature(text: str) -> set[str]:
    """Quick fingerprint to make sure we aren't generating duplicate decoys."""
    tokens = [t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split() if len(t) > 2]
    return set(tokens)


def _is_diverse_enough(candidates: list[str]) -> bool:
    if len(candidates) != 5:
        return False
    norm = []
    for c in candidates:
        v = (c or "").strip().lower()
        if not v or v in norm:
            return False
        norm.append(v)
    sigs = [_text_signature(c) for c in candidates]
    # overlap ratio threshold; enforce pair-wise distinction
    for i in range(len(sigs)):
        for j in range(i + 1, len(sigs)):
            a, b = sigs[i], sigs[j]
            if not a or not b:
                return False
            overlap = len(a & b) / max(1, min(len(a), len(b)))
            if overlap > 0.6:
                return False
    return True


def _fallback_decoy_texts() -> list[str]:
    return [
        "A red lighthouse on stormy ocean cliffs at dusk",
        "An origami crane floating over a snowy pine forest",
        "A steampunk compass beside ancient maps and brass gears",
        "A tropical parrot perched on bright coral reef rocks",
        "A desert caravan crossing golden dunes under a full moon",
    ]


def _extract_json_array_from_text(text: str) -> list[str]:
    """Extract the JSON array even if the LLM wraps it in markdown blocks."""
    raw = (text or "").strip()
    if not raw:
        return []
    # direct parse
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x).strip() for x in data if isinstance(x, str)]
    except Exception:
        pass
    # fenced code block
    fence = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", raw, flags=re.IGNORECASE)
    if fence:
        try:
            data = json.loads(fence.group(1))
            if isinstance(data, list):
                return [str(x).strip() for x in data if isinstance(x, str)]
        except Exception:
            pass
    # first bracketed array
    bracket = re.search(r"(\[[\s\S]*\])", raw)
    if bracket:
        try:
            data = json.loads(bracket.group(1))
            if isinstance(data, list):
                return [str(x).strip() for x in data if isinstance(x, str)]
        except Exception:
            pass
    return []


def _build_decoy_image_texts(challenge_id: int, llm_backend: SemanticLlmBackend) -> list[str]:
    """Ask the LLM to come up with 5 random decoy prompts."""
    try:
        system_seed = f"challenge-{challenge_id}-{hashlib.sha256(str(challenge_id).encode()).hexdigest()[:8]}"
        system_prompt = (
            "You generate decoy prompts for a security image challenge.\n"
            "Output MUST be valid JSON only: an array of exactly 5 strings.\n"
            "No prose, no explanation, no markdown, no keys."
        )
        user_prompt = (
            "Create 5 short image descriptions for decoy images.\n"
            "Rules:\n"
            "- Each description must be clearly different in meaning/context.\n"
            "- Keep each under 14 words.\n"
            "- Do not mention security/authentication.\n"
            "- Avoid overlap in nouns/themes.\n"
            f"Seed hint: {system_seed}\n"
            "Return JSON array only."
        )
        response = generate_text_with_prompt(
            system_prompt,
            user_prompt,
            llm_backend,
            temperature=0.7,
            max_tokens=220,
        ) or ""
        prompts = _extract_json_array_from_text(response)
        logger.info(
            "decoy_prompt_debug: backend=%s challenge_id=%s raw_len=%s parsed_count=%s",
            llm_backend.value,
            challenge_id,
            len(response),
            len(prompts),
        )
        if _is_diverse_enough(prompts):
            logger.info("decoy_prompt_debug: accepted_llm_output challenge_id=%s", challenge_id)
            return prompts
        logger.warning(
            "Decoy prompt LLM output rejected; using fallback. challenge_id=%s parsed=%s raw_output=%s",
            challenge_id,
            prompts,
            response,
        )
    except Exception as exc:
        logger.warning("Decoy prompt LLM generation failed; using fallback. challenge_id=%s err=%s", challenge_id, exc)
    return _fallback_decoy_texts()


def _parse_lockout_delays() -> list[int]:
    raw = (settings.semantic_lockout_delays_seconds or "").strip()
    delays: list[int] = []
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        try:
            value = int(token)
            if value > 0:
                delays.append(value)
        except ValueError:
            continue
    return delays or [30, 60, 1800, 3600]


def _is_temporarily_locked(user: models.User) -> bool:
    """Check if the current timestamp is within the user's lockout window."""
    return bool(user.semantic_locked_until and user.semantic_locked_until > datetime.utcnow())


def _apply_progressive_user_lockout(user: models.User) -> tuple[Optional[int], bool]:
    """Bump the failure counter and lock the account if they failed too many times.

    Returns:
    - retry_after_seconds (temporary lockout duration) or None
    - hard_locked (True when account enters hard lock)
    """
    user.semantic_failed_attempts += 1
    lock_window_size = max(1, int(settings.semantic_lockout_start_after_failures or 3))
    lockout_delays = _parse_lockout_delays()

    if user.semantic_failed_attempts % lock_window_size != 0:
        return None, False

    if user.semantic_lock_step < len(lockout_delays):
        retry_after_seconds = lockout_delays[user.semantic_lock_step]
        user.semantic_lock_step += 1
        user.semantic_locked_until = datetime.utcnow() + timedelta(seconds=retry_after_seconds)
        return retry_after_seconds, False

    user.semantic_hard_locked = True
    user.semantic_locked_until = None
    return None, True


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> models.User:
    """Grab the user from the JWT; throw a 401 if it's invalid."""
    if not credentials or credentials.scheme != "Bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Provide a valid Bearer token.",
        )
    payload = decode_access_token(credentials.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    return user


def _bucket_similarity(value: float) -> str:
    if value < 0.4:
        return "<0.4"
    if value < 0.6:
        return "0.4-0.6"
    if value < 0.8:
        return "0.6-0.8"
    return ">=0.8"


def register_user_core(
    payload: schemas.UserCreate,
    db: Session,
    llm_backend: SemanticLlmBackend,
) -> schemas.UserPublic:
    """Handle user registration and secure their semantic secret."""

    conditions = [models.User.username == payload.username]
    if payload.email:
        conditions.append(models.User.email == payload.email)

    existing = db.query(models.User).filter(or_(*conditions)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this username or email already exists.",
        )

    user = models.User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.flush()  # Ensure user.id is available

    # Generate embedding for local similarity fallback
    embedding_vector = semantic_service.embed(payload.secret_text)
    raw_bytes = vector_to_bytes(embedding_vector)
    encrypted_bytes = encrypt_embedding(raw_bytes)

    # Generate semantic summary using LLM (stores concept, NOT raw text)
    semantic_summary = generate_semantic_summary(payload.secret_text, llm_backend)
    semantic_summary_encrypted = encrypt_text(semantic_summary) if semantic_summary else None

    secret_embedding = models.SecretEmbedding(
        user_id=user.id,
        secret_type=payload.secret_type,
        embedding_encrypted=encrypted_bytes,
        semantic_summary_encrypted=semantic_summary_encrypted,
        model_name=settings.embedding_model_name,
    )
    db.add(secret_embedding)
    db.commit()
    db.refresh(user)
    _generate_user_security_image_sync_and_async(user, db, payload.image_text, llm_backend)

    return user


@router.post("/register", response_model=schemas.UserPublic, status_code=status.HTTP_201_CREATED)
def register_account(
    payload: schemas.UserCreate,
    db: Session = Depends(get_db),
    llm_backend: SemanticLlmBackend = Depends(get_semantic_llm_backend),
) -> schemas.UserPublic:
    """HTTP wrapper: Register a new user."""

    return register_user_core(payload, db, llm_backend)


@router.post("/login/init", response_model=schemas.LoginInitResponse)
def login_init(
    payload: schemas.LoginInitRequest,
    db: Session = Depends(get_db),
    llm_backend: SemanticLlmBackend = Depends(get_semantic_llm_backend),
) -> schemas.LoginInitResponse:
    """Kick off a new login session for the user."""

    user = db.query(models.User).filter(
        or_(models.User.username == payload.identifier, models.User.email == payload.identifier)
    ).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to start login for the provided identifier.",
        )

    if not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account has no password on file. Register a new account with a password, or set a password if you can access your profile another way.",
        )
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect password.",
        )
    if user.semantic_hard_locked:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account locked due to repeated semantic failures. Recovery via email is required.",
        )
    if _is_temporarily_locked(user):
        remaining = int((user.semantic_locked_until - datetime.utcnow()).total_seconds())
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Too many recent semantic failures. Try again in {max(1, remaining)} seconds.",
        )
    if not user.greeting_image_bytes:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Your security greeting image is still being prepared. "
                "Please wait a bit and try sign-in again."
            ),
        )

    # Get the user's secret type
    secret = (
        db.query(models.SecretEmbedding)
        .filter(models.SecretEmbedding.user_id == user.id)
        .order_by(models.SecretEmbedding.created_at.desc())
        .first()
    )
    secret_type = secret.secret_type if secret else "text"

    challenge = models.LoginChallenge(user_id=user.id)
    db.add(challenge)
    db.commit()
    db.refresh(challenge)

    try:
        pool_rows = _get_user_gallery_pool(db, user.id)
        if len(pool_rows) != 6 or sum(1 for r in pool_rows if r.is_target) != 1:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Your security image challenge is still being prepared. "
                    "Please wait a bit and try sign-in again."
                ),
            )
        _populate_login_challenge_gallery_from_pool(db, challenge, pool_rows)
    except HTTPException:
        db.rollback()
        db.query(models.LoginChallengeGallerySlot).filter(
            models.LoginChallengeGallerySlot.challenge_id == challenge.id
        ).delete(synchronize_session=False)
        db.delete(challenge)
        db.commit()
        raise
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        db.delete(challenge)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    # Generate appropriate prompt based on secret type
    if secret_type == "voice":
        prompt = (
            "Speak or describe the idea behind your secret. "
            "You can paraphrase, explain, use an analogy, or describe it in another language."
        )
    else:
        prompt = (
            "Describe the idea behind your secret in your own words. "
            "You can paraphrase, explain, use an analogy, or describe it in another language—"
            "as long as it captures the same meaning."
        )

    gallery_urls = [f"/auth/login/challenge/{challenge.id}/gallery-image/{s}" for s in range(6)]
    return schemas.LoginInitResponse(
        challenge_id=challenge.id,
        prompt=prompt,
        secret_type=secret_type,
        audio_prompt_available=True,  # TTS is always available
        greeting_image_url=None,
        greeting_gallery_urls=gallery_urls,
        semantic_required=user.login_mode != models.LoginMode.IMAGE_ONLY,
    )


@router.get("/login/challenge/{challenge_id}/gallery-image/{slot}")
def get_login_challenge_gallery_image(
    challenge_id: int,
    slot: int,
    db: Session = Depends(get_db),
) -> Response:
    """Serve a specific image tile for the login challenge."""
    if slot < 0 or slot > 5:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slot must be 0-5.")
    challenge = db.query(models.LoginChallenge).filter(models.LoginChallenge.id == challenge_id).first()
    if not challenge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found.")
    if challenge.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Challenge expired.")
    row = (
        db.query(models.LoginChallengeGallerySlot)
        .filter(
            models.LoginChallengeGallerySlot.challenge_id == challenge_id,
            models.LoginChallengeGallerySlot.slot == slot,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gallery image not found.")
    return Response(content=row.image_bytes, media_type=row.image_mime or "image/png")


@router.post(
    "/login/challenge/{challenge_id}/pick-greeting-image",
    response_model=schemas.GreetingImagePickResult,
)
def pick_login_challenge_greeting_image(
    challenge_id: int,
    payload: schemas.GreetingImagePickRequest,
    db: Session = Depends(get_db),
) -> schemas.GreetingImagePickResult:
    """Process the user's tile selection. Too many bad guesses locks the account."""
    challenge = db.query(models.LoginChallenge).filter(models.LoginChallenge.id == challenge_id).first()
    if not challenge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found.")
    if challenge.expires_at <= datetime.utcnow():
        challenge.status = models.LoginChallengeStatus.EXPIRED
        db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Challenge expired.")
    if challenge.status != models.LoginChallengeStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This login challenge is no longer active.",
        )

    user = db.query(models.User).filter(models.User.id == challenge.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found.")
    if user.semantic_hard_locked:
        challenge.status = models.LoginChallengeStatus.COMPLETED
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account locked due to repeated failures. Recovery via email is required.",
        )
    if _is_temporarily_locked(user):
        remaining = int((user.semantic_locked_until - datetime.utcnow()).total_seconds())
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Too many recent failures. Try again in {max(1, remaining)} seconds.",
        )

    if challenge.image_gallery_verified_at is not None:
        return schemas.GreetingImagePickResult(
            success=True,
            message="Security image already confirmed for this challenge.",
            remaining_attempts=None,
        )

    row = (
        db.query(models.LoginChallengeGallerySlot)
        .filter(
            models.LoginChallengeGallerySlot.challenge_id == challenge_id,
            models.LoginChallengeGallerySlot.slot == payload.selected_slot,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid slot.")

    if row.is_target:
        challenge.image_gallery_verified_at = datetime.utcnow()
        if user.login_mode == models.LoginMode.IMAGE_ONLY:
            challenge.status = models.LoginChallengeStatus.COMPLETED
            token = create_access_token(subject=str(user.id), extra_claims={"username": user.username})
            user.semantic_failed_attempts = 0
            user.semantic_lock_step = 0
            user.semantic_locked_until = None
            user.semantic_hard_locked = False
            db.commit()
            _refresh_user_gallery_pool_async(user.id, SemanticLlmBackend.groq)
            return schemas.GreetingImagePickResult(
                success=True,
                message="Authentication successful.",
                token=token,
                remaining_attempts=None,
            )
        db.commit()
        return schemas.GreetingImagePickResult(
            success=True,
            message="Correct security image. You can now complete the semantic step.",
            remaining_attempts=None,
        )

    challenge.image_pick_failures += 1
    retry_after_seconds, hard_locked = _apply_progressive_user_lockout(user)
    if hard_locked:
        challenge.status = models.LoginChallengeStatus.COMPLETED
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account locked due to repeated failures. Recovery via email is required.",
        )
    if retry_after_seconds:
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Too many failed attempts. Try again in {retry_after_seconds} seconds.",
        )
    lock_window_size = max(1, int(settings.semantic_lockout_start_after_failures or 3))
    remaining = lock_window_size - (user.semantic_failed_attempts % lock_window_size)
    db.commit()
    return schemas.GreetingImagePickResult(
        success=False,
        message="That is not your security image. Try another tile.",
        remaining_attempts=remaining,
    )


def login_complete_core(
    payload: schemas.LoginCompleteRequest,
    db: Session,
    llm_backend: SemanticLlmBackend,
) -> schemas.LoginResult:
    """Finish the login flow by checking if their text matches the secret."""

    challenge = db.query(models.LoginChallenge).filter(models.LoginChallenge.id == payload.challenge_id).first()
    if not challenge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or unknown login challenge.",
        )

    if challenge.status != models.LoginChallengeStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This login challenge is no longer active.",
        )

    if challenge.expires_at <= datetime.utcnow():
        challenge.status = models.LoginChallengeStatus.EXPIRED
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This login challenge has expired. Please start again.",
        )

    if challenge.image_gallery_verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select your security greeting image before answering the semantic challenge.",
        )
    user = db.query(models.User).filter(models.User.id == challenge.user_id).first()
    if user and user.login_mode == models.LoginMode.IMAGE_ONLY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account is configured for image-only login. Semantic step is not required.",
        )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Login failed.",
        )
    if user.semantic_hard_locked:
        challenge.status = models.LoginChallengeStatus.COMPLETED
        db.commit()
        return schemas.LoginResult(
            success=False,
            message="Account locked due to repeated semantic failures. Recovery via email is required.",
        )
    if _is_temporarily_locked(user):
        remaining = int((user.semantic_locked_until - datetime.utcnow()).total_seconds())
        return schemas.LoginResult(
            success=False,
            message=f"Please wait before trying again. Retry in {max(1, remaining)} seconds.",
            retry_after_seconds=max(1, remaining),
        )

    secret_embedding = (
        db.query(models.SecretEmbedding)
        .filter(models.SecretEmbedding.user_id == user.id)
        .order_by(models.SecretEmbedding.created_at.desc())
        .first()
    )
    if not secret_embedding:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Login is not configured correctly for this account.",
        )

    # How comparison works:
    # - At REGISTER we stored an LLM-generated "semantic summary" of your secret (not the raw phrase).
    # - At LOGIN we compare that stored summary to your new phrase. So the LLM sees two texts:
    #   (1) the summary, e.g. "Someone is aware of a past action another person did"
    #   (2) your login text, e.g. "8 months ago in hot season someone did something and someone knows"
    # - If the model scores similarity >= threshold (default 0.7), login succeeds.
    # - Fallback: if no summary (or Groq fails), we use sentence-transformers embeddings + cosine similarity.
    similarity: float = 0.0
    used_path = "unknown"
    llm_score_value: Optional[float] = None
    fallback_score_value: Optional[float] = None

    if secret_embedding.semantic_summary_encrypted:
        semantic_summary = decrypt_text(secret_embedding.semantic_summary_encrypted)
        llm_score = score_semantic_similarity(semantic_summary, payload.response_text, llm_backend)
        llm_score_value = llm_score
        if llm_score is not None:
            similarity = llm_score
            used_path = "llm"
        else:
            # LLM failed, fall back to embeddings
            stored_bytes = decrypt_embedding(secret_embedding.embedding_encrypted)
            stored_vector = bytes_to_vector(stored_bytes)
            response_vector = semantic_service.embed(payload.response_text)
            similarity = semantic_service.similarity(stored_vector, response_vector)
            fallback_score_value = similarity
            used_path = "embedding_fallback_after_llm_none"
    else:
        # No semantic summary stored, use embeddings only
        stored_bytes = decrypt_embedding(secret_embedding.embedding_encrypted)
        stored_vector = bytes_to_vector(stored_bytes)
        response_vector = semantic_service.embed(payload.response_text)
        similarity = semantic_service.similarity(stored_vector, response_vector)
        fallback_score_value = similarity
        used_path = "embedding_only_no_summary"

    challenge.attempt_count += 1

    max_attempts = getattr(settings, "max_login_attempts", 3)
    success_threshold = settings.similarity_threshold
    near_threshold = max(0.0, success_threshold - 0.1)
    logger.info(
        "semantic_debug challenge_id=%s user_id=%s backend=%s used_path=%s llm_score=%s fallback_score=%s final_similarity=%.4f threshold=%.4f near_threshold=%.4f response_len=%s",
        challenge.id,
        user.id,
        llm_backend.value,
        used_path,
        llm_score_value,
        fallback_score_value,
        similarity,
        success_threshold,
        near_threshold,
        len(payload.response_text or ""),
    )

    result_type = models.LoginResultType.FAILURE
    message = "We could not match your description closely enough. You can try again."
    token: Optional[str] = None

    retry_after_seconds: Optional[int] = None
    if similarity >= success_threshold:
        result_type = models.LoginResultType.SUCCESS
        message = "Authentication successful."
        token = create_access_token(subject=str(user.id), extra_claims={"username": user.username})
        challenge.status = models.LoginChallengeStatus.COMPLETED
        user.semantic_failed_attempts = 0
        user.semantic_lock_step = 0
        user.semantic_locked_until = None
        user.semantic_hard_locked = False
    elif similarity >= near_threshold and challenge.attempt_count < max_attempts:
        message = (
            "Your answer is close to what we expect. "
            "Please add a bit more detail or express the idea in a different way."
        )
    elif challenge.attempt_count >= max_attempts:
        # Keep challenge active; semantic lockout policy is handled below via user-level counters.
        message = "We could not match your description closely enough. You can try again."

    if result_type != models.LoginResultType.SUCCESS:
        # Progressive policy:
        # - Every 3 consecutive semantic failures triggers a lockout window.
        # - Lockout windows are configured by SEMANTIC_LOCKOUT_DELAYS_SECONDS.
        # - After the configured windows are exhausted, the next 3-failure boundary hard-locks.
        # - Starting a fresh login challenge does NOT reset these user-level counters.
        retry_after_seconds, hard_locked = _apply_progressive_user_lockout(user)
        if retry_after_seconds:
            result_type = models.LoginResultType.LOCKED
            message = f"Too many failed semantic attempts. Try again in {retry_after_seconds} seconds."
        elif hard_locked:
            result_type = models.LoginResultType.LOCKED
            message = "Account locked due to repeated semantic failures. Recovery via email is required."
            challenge.status = models.LoginChallengeStatus.COMPLETED

    # Record login event with anonymized similarity bucket
    similarity_bucket = _bucket_similarity(similarity)
    event = models.LoginEvent(
        user_id=user.id,
        result=result_type,
        similarity_bucket=similarity_bucket,
    )
    db.add(event)
    db.commit()

    if result_type == models.LoginResultType.SUCCESS:
        _refresh_user_gallery_pool_async(user.id, llm_backend)

    return schemas.LoginResult(
        success=result_type == models.LoginResultType.SUCCESS,
        message=message,
        similarity_score=round(similarity, 3),  # Include score for research/debugging
        token=token,
        retry_after_seconds=retry_after_seconds,
    )


@router.post("/login/complete", response_model=schemas.LoginResult)
def login_complete(
    payload: schemas.LoginCompleteRequest,
    db: Session = Depends(get_db),
    llm_backend: SemanticLlmBackend = Depends(get_semantic_llm_backend),
) -> schemas.LoginResult:
    """HTTP wrapper: Complete the login process."""

    return login_complete_core(payload, db, llm_backend)


# =============================================================================
# Profile (authenticated): update username, email, password, secret (text or voice)
# =============================================================================


def _profile_response(user: models.User, db: Session) -> schemas.ProfileResponse:
    secret = (
        db.query(models.SecretEmbedding)
        .filter(models.SecretEmbedding.user_id == user.id)
        .order_by(models.SecretEmbedding.created_at.desc())
        .first()
    )
    secret_type = secret.secret_type if secret else "text"
    return schemas.ProfileResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        created_at=user.created_at,
        secret_type=secret_type,
        login_mode=user.login_mode if user.login_mode in {models.LoginMode.BOTH, models.LoginMode.IMAGE_ONLY} else models.LoginMode.BOTH,
    )


@router.post("/register/preview-greeting-image")
def preview_registration_greeting_image(
    payload: schemas.RegistrationPreviewRequest,
) -> Response:
    """Generate a quick preview image so the user can see what it looks like before saving."""
    try:
        image_bytes, image_mime, _, _ = generate_greeting_image(payload.image_text)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not generate preview greeting image. ({exc})",
        ) from exc
    return Response(content=image_bytes, media_type=image_mime or "image/png")


@router.get("/profile", response_model=schemas.ProfileResponse)
def get_profile(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> schemas.ProfileResponse:
    """Return the user's profile info."""
    return _profile_response(user, db)


@router.post("/profile/greeting-image", response_model=schemas.ProfileResponse)
def update_profile_greeting_image(
    payload: schemas.GreetingImageUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    llm_backend: SemanticLlmBackend = Depends(get_semantic_llm_backend),
) -> schemas.ProfileResponse:
    """Update the user's greeting image without touching their semantic secret."""
    _generate_user_security_image_sync_and_async(user, db, payload.image_text, llm_backend)
    return _profile_response(user, db)


@router.get("/profile/greeting-image")
def get_profile_greeting_image(
    user: models.User = Depends(get_current_user),
) -> Response:
    """Serve the user's current greeting image."""
    if not user.greeting_image_bytes:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Greeting image not found.")
    return Response(content=user.greeting_image_bytes, media_type=user.greeting_image_mime or "image/png")


@router.post("/profile/login-mode", response_model=schemas.ProfileResponse)
def update_profile_login_mode(
    payload: schemas.LoginModeUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> schemas.ProfileResponse:
    """Toggle between 'both factors' and 'image only' modes."""
    user.login_mode = payload.login_mode
    db.commit()
    db.refresh(user)
    return _profile_response(user, db)


@router.patch("/profile", response_model=schemas.ProfileResponse)
def update_profile(
    payload: schemas.ProfileUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> schemas.ProfileResponse:
    """Update basic profile fields."""
    if payload.username is not None:
        existing = db.query(models.User).filter(
            models.User.username == payload.username,
            models.User.id != user.id,
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this username already exists.",
            )
        user.username = payload.username
    if "email" in payload.model_fields_set:
        email_val = payload.email.strip() if (payload.email and isinstance(payload.email, str)) else None
        if email_val:
            existing = db.query(models.User).filter(
                models.User.email == email_val,
                models.User.id != user.id,
            ).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A user with this email already exists.",
                )
            user.email = email_val
        else:
            user.email = None
    if payload.new_password is not None:
        user.password_hash = hash_password(payload.new_password)
    db.commit()
    db.refresh(user)
    return _profile_response(user, db)


def _replace_secret_for_user(
    db: Session,
    user_id: int,
    secret_text: str,
    secret_type: str,
    llm_backend: SemanticLlmBackend,
) -> None:
    """Nuke the old semantic secrets and save the new one."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    db.query(models.SecretEmbedding).filter(models.SecretEmbedding.user_id == user_id).delete()
    embedding_vector = semantic_service.embed(secret_text)
    raw_bytes = vector_to_bytes(embedding_vector)
    encrypted_bytes = encrypt_embedding(raw_bytes)
    semantic_summary = generate_semantic_summary(secret_text, llm_backend)
    semantic_summary_encrypted = encrypt_text(semantic_summary) if semantic_summary else None
    secret_embedding = models.SecretEmbedding(
        user_id=user_id,
        secret_type=secret_type,
        embedding_encrypted=encrypted_bytes,
        semantic_summary_encrypted=semantic_summary_encrypted,
        model_name=settings.embedding_model_name,
    )
    db.add(secret_embedding)
    # Do NOT regenerate greeting image when secret phrase changes.
    # Image is managed independently via /auth/profile/greeting-image.


@router.post("/profile/secret", response_model=schemas.ProfileResponse)
def update_profile_secret_text(
    payload: schemas.SecretUpdateText,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    llm_backend: SemanticLlmBackend = Depends(get_semantic_llm_backend),
) -> schemas.ProfileResponse:
    """Change the semantic secret to a new text phrase."""
    _replace_secret_for_user(db, user.id, payload.secret_text, models.SecretType.TEXT, llm_backend)
    db.commit()
    db.refresh(user)
    return _profile_response(user, db)


@router.post("/profile/secret/voice", response_model=schemas.ProfileResponse)
async def update_profile_secret_voice(
    file: UploadFile = File(...),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    llm_backend: SemanticLlmBackend = Depends(get_semantic_llm_backend),
) -> schemas.ProfileResponse:
    """Change the semantic secret via voice upload."""
    audio_bytes = await file.read()
    secret_text = transcribe_audio(file.filename or "audio.wav", audio_bytes)
    if not secret_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to transcribe the provided audio.",
        )
    secret_text = secret_text.strip()
    if not secret_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transcription was empty. Try speaking more clearly.",
        )
    if len(secret_text) > schemas.SECRET_TEXT_MAX_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Transcribed secret is too long (max {schemas.SECRET_TEXT_MAX_LENGTH} characters). "
                "Try a shorter phrase."
            ),
        )
    _replace_secret_for_user(db, user.id, secret_text, models.SecretType.VOICE, llm_backend)
    db.commit()
    db.refresh(user)
    return _profile_response(user, db)


def text_to_speech(text: str) -> Response:
    """Convert some text to a playable WAV file."""

    audio_bytes = synthesize_speech(text)
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Text-to-speech service is not available.",
        )

    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={"Content-Disposition": f'attachment; filename="prompt.wav"'},
    )


@router.get("/tts/prompt/{challenge_id}")
def get_prompt_audio(challenge_id: int, db: Session = Depends(get_db)) -> Response:
    """Fetch the login prompt audio."""

    challenge = db.query(models.LoginChallenge).filter(models.LoginChallenge.id == challenge_id).first()
    if not challenge:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Challenge not found.",
        )

    # Get the user's secret type to generate appropriate prompt
    secret = (
        db.query(models.SecretEmbedding)
        .filter(models.SecretEmbedding.user_id == challenge.user_id)
        .order_by(models.SecretEmbedding.created_at.desc())
        .first()
    )
    secret_type = secret.secret_type if secret else "text"

    if secret_type == "voice":
        prompt = "Speak or describe the idea behind your secret."
    else:
        prompt = "Describe the idea behind your secret in your own words. You can paraphrase, explain, or use an analogy."

    audio_bytes = synthesize_speech(prompt)
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Text-to-speech service is not available.",
        )

    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={"Content-Disposition": f'attachment; filename="prompt_{challenge_id}.wav"'},
    )


@router.post("/recovery/unlock/request", response_model=schemas.RecoveryResponse)
def request_unlock_recovery(
    payload: schemas.RecoveryRequest,
    db: Session = Depends(get_db),
) -> schemas.RecoveryResponse:
    """Generate a recovery token to email to the user."""
    user = db.query(models.User).filter(
        or_(models.User.username == payload.identifier, models.User.email == payload.identifier)
    ).first()
    generic = "If this account exists and is locked, a recovery message has been prepared."
    if not user or not user.semantic_hard_locked:
        return schemas.RecoveryResponse(message=generic)
    if not user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Locked account has no email on file for recovery.",
        )

    token = create_signed_token(
        subject=str(user.id),
        expires_minutes=30,
        extra_claims={"purpose": "semantic_unlock", "email": user.email},
    )
    return schemas.RecoveryResponse(
        message=generic,
        recovery_token=token,
    )


@router.post("/recovery/unlock/confirm", response_model=schemas.RecoveryResponse)
def confirm_unlock_recovery(
    payload: schemas.RecoveryConfirmRequest,
    db: Session = Depends(get_db),
) -> schemas.RecoveryResponse:
    """Use the recovery token to unlock the account."""
    token_payload = decode_access_token(payload.token)
    if not token_payload or token_payload.get("purpose") != "semantic_unlock":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired recovery token.",
        )
    try:
        user_id = int(token_payload["sub"])
    except (TypeError, ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid recovery token payload.",
        )
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    user.semantic_hard_locked = False
    user.semantic_failed_attempts = 0
    user.semantic_lock_step = 0
    user.semantic_locked_until = None
    db.commit()
    return schemas.RecoveryResponse(message="Account unlocked. You can sign in again.")


@router.get("/reset/{identifier}", response_model=schemas.AdminResetResponse)
def admin_reset_user_lockout(
    identifier: str,
    secret: str,
    db: Session = Depends(get_db),
) -> schemas.AdminResetResponse:
    """Emergency admin backdoor to unlock an account."""
    configured = (settings.admin_unlock_secret or "").strip()
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_UNLOCK_SECRET is not configured on the server.",
        )
    if secret != configured:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin reset secret.")

    user = db.query(models.User).filter(
        or_(models.User.username == identifier, models.User.email == identifier)
    ).first()
    if not user:
        return schemas.AdminResetResponse(
            message="No matching user found.",
            identifier=identifier,
            unlocked=False,
        )

    user.semantic_hard_locked = False
    user.semantic_failed_attempts = 0
    user.semantic_lock_step = 0
    user.semantic_locked_until = None
    db.commit()
    return schemas.AdminResetResponse(
        message="User lockout counters were reset.",
        identifier=identifier,
        unlocked=True,
    )

