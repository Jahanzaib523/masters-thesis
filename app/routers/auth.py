from datetime import datetime, timedelta
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import settings
from ..db import get_db
from ..security import encrypt_embedding, decrypt_embedding, encrypt_text, decrypt_text
from ..semantic import semantic_service, vector_to_bytes, bytes_to_vector
from ..groq_client import synthesize_speech, transcribe_audio
from ..llm_provider import SemanticLlmBackend, get_semantic_llm_backend
from ..semantic_llm import generate_semantic_summary, score_semantic_similarity
from ..passwords import hash_password, verify_password
from ..tokens import create_access_token, create_signed_token, decode_access_token
from ..config import resolve_hf_api_token
from ..greeting_image import generate_greeting_image

router = APIRouter()
logger = logging.getLogger("sas.auth")
security = HTTPBearer(auto_error=False)


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
    return delays or [30, 300, 1800]


def _is_temporarily_locked(user: models.User) -> bool:
    return bool(user.semantic_locked_until and user.semantic_locked_until > datetime.utcnow())


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> models.User:
    """Require valid JWT and return the current user; otherwise 401."""
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
    """Register a new user and store encrypted semantic embeddings for their secret."""

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
    try:
        image_bytes, image_mime, seed, prompt_hash = generate_greeting_image(payload.image_text)
    except Exception as exc:
        db.rollback()
        logger.error(
            "register_user_core: greeting image failed user_id=%s hf_resolved=%s err=%s",
            getattr(user, "id", None),
            bool(resolve_hf_api_token()),
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not generate your security greeting image. Please try again. ({exc})",
        )
    user.greeting_image_path = None
    user.greeting_image_bytes = image_bytes
    user.greeting_image_mime = image_mime
    user.greeting_seed = seed
    user.greeting_prompt_hash = prompt_hash
    user.greeting_model_name = settings.image_model
    db.commit()
    db.refresh(user)

    return user


@router.post("/register", response_model=schemas.UserPublic, status_code=status.HTTP_201_CREATED)
def register_account(
    payload: schemas.UserCreate,
    db: Session = Depends(get_db),
    llm_backend: SemanticLlmBackend = Depends(get_semantic_llm_backend),
) -> schemas.UserPublic:
    """HTTP: register with optional X-Semantic-LLM-Provider: openai for OpenAI chat LLM."""

    return register_user_core(payload, db, llm_backend)


@router.post("/login/init", response_model=schemas.LoginInitResponse)
def login_init(payload: schemas.LoginInitRequest, db: Session = Depends(get_db)) -> schemas.LoginInitResponse:
    """Initialize a semantic login challenge for the given identifier."""

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
            detail="Security greeting image is missing for this account. Please reset your secret in Profile.",
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

    return schemas.LoginInitResponse(
        challenge_id=challenge.id,
        prompt=prompt,
        secret_type=secret_type,
        audio_prompt_available=True,  # TTS is always available
        greeting_image_url=f"/auth/login/challenge/{challenge.id}/greeting-image",
    )


@router.get("/login/challenge/{challenge_id}/greeting-image")
def get_login_challenge_greeting_image(
    challenge_id: int,
    db: Session = Depends(get_db),
) -> Response:
    """Serve greeting image for a valid login challenge (pre-semantic step)."""
    challenge = db.query(models.LoginChallenge).filter(models.LoginChallenge.id == challenge_id).first()
    if not challenge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found.")
    if challenge.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Challenge expired.")
    user = db.query(models.User).filter(models.User.id == challenge.user_id).first()
    if not user or not user.greeting_image_bytes:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Greeting image not found.")
    return Response(content=user.greeting_image_bytes, media_type=user.greeting_image_mime or "image/png")


def login_complete_core(
    payload: schemas.LoginCompleteRequest,
    db: Session,
    llm_backend: SemanticLlmBackend,
) -> schemas.LoginResult:
    """Complete a semantic login challenge by comparing user input with stored embeddings."""

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

    user = db.query(models.User).filter(models.User.id == challenge.user_id).first()
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
        challenge.status = models.LoginChallengeStatus.COMPLETED
        db.commit()
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

    if secret_embedding.semantic_summary_encrypted:
        semantic_summary = decrypt_text(secret_embedding.semantic_summary_encrypted)
        llm_score = score_semantic_similarity(semantic_summary, payload.response_text, llm_backend)
        if llm_score is not None:
            similarity = llm_score
        else:
            # LLM failed, fall back to embeddings
            stored_bytes = decrypt_embedding(secret_embedding.embedding_encrypted)
            stored_vector = bytes_to_vector(stored_bytes)
            response_vector = semantic_service.embed(payload.response_text)
            similarity = semantic_service.similarity(stored_vector, response_vector)
    else:
        # No semantic summary stored, use embeddings only
        stored_bytes = decrypt_embedding(secret_embedding.embedding_encrypted)
        stored_vector = bytes_to_vector(stored_bytes)
        response_vector = semantic_service.embed(payload.response_text)
        similarity = semantic_service.similarity(stored_vector, response_vector)

    challenge.attempt_count += 1

    max_attempts = getattr(settings, "max_login_attempts", 3)
    success_threshold = settings.similarity_threshold
    near_threshold = max(0.0, success_threshold - 0.1)

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
        result_type = models.LoginResultType.LOCKED
        message = "Too many unsuccessful attempts for this challenge. Please start a new login."
        challenge.status = models.LoginChallengeStatus.COMPLETED

    if result_type != models.LoginResultType.SUCCESS:
        user.semantic_failed_attempts += 1
        hard_lock_after = max(settings.semantic_hard_lock_after_failures, 1)
        if user.semantic_failed_attempts >= hard_lock_after:
            user.semantic_hard_locked = True
            user.semantic_locked_until = None
            result_type = models.LoginResultType.LOCKED
            message = "Account locked due to repeated semantic failures. Recovery via email is required."
            challenge.status = models.LoginChallengeStatus.COMPLETED
        else:
            start_after = max(settings.semantic_lockout_start_after_failures, 1)
            delays = _parse_lockout_delays()
            if user.semantic_failed_attempts >= start_after:
                delay_idx = min(user.semantic_lock_step, len(delays) - 1)
                retry_after_seconds = delays[delay_idx]
                user.semantic_locked_until = datetime.utcnow() + timedelta(seconds=retry_after_seconds)
                if user.semantic_lock_step < len(delays) - 1:
                    user.semantic_lock_step += 1
                result_type = models.LoginResultType.LOCKED
                message = f"Too many failed semantic attempts. Try again in {retry_after_seconds} seconds."
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
    """HTTP: complete login; optional X-Semantic-LLM-Provider: openai."""

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
    )


@router.get("/profile", response_model=schemas.ProfileResponse)
def get_profile(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> schemas.ProfileResponse:
    """Get current user profile (username, email, secret_type)."""
    return _profile_response(user, db)


@router.patch("/profile", response_model=schemas.ProfileResponse)
def update_profile(
    payload: schemas.ProfileUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> schemas.ProfileResponse:
    """Update username, email, and/or password. Only provided fields are updated."""
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
    """Remove all existing secret embeddings for user and add one new one (text or voice)."""
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
    try:
        image_bytes, image_mime, seed, prompt_hash = generate_greeting_image(secret_text)
    except Exception as exc:
        logger.error(
            "_replace_secret_for_user: greeting image failed user_id=%s hf_resolved=%s err=%s",
            user_id,
            bool(resolve_hf_api_token()),
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not generate your security greeting image. Please try again. ({exc})",
        )
    user.greeting_image_path = None
    user.greeting_image_bytes = image_bytes
    user.greeting_image_mime = image_mime
    user.greeting_seed = seed
    user.greeting_prompt_hash = prompt_hash
    user.greeting_model_name = settings.image_model


@router.post("/profile/secret", response_model=schemas.ProfileResponse)
def update_profile_secret_text(
    payload: schemas.SecretUpdateText,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    llm_backend: SemanticLlmBackend = Depends(get_semantic_llm_backend),
) -> schemas.ProfileResponse:
    """Set semantic secret to a new text phrase. Overwrites voice secret if present (one per account)."""
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
    """Set semantic secret from spoken audio. Overwrites text secret if present (one per account)."""
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
    """Convert text to speech audio. Returns WAV audio for accessibility."""

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
    """Get the login prompt as spoken audio for blind users."""

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
    """Issue an email recovery token for hard-locked accounts.

    In this prototype, token is returned in response for local testing.
    """
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
    """Confirm unlock token and clear hard lock state."""
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

