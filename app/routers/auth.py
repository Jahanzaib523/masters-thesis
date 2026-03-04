from datetime import datetime
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
from ..groq_client import (
    score_semantic_similarity,
    generate_semantic_summary,
    synthesize_speech,
    transcribe_audio,
)
from ..passwords import hash_password
from ..tokens import create_access_token, decode_access_token

router = APIRouter()
security = HTTPBearer(auto_error=False)


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


@router.post("/register", response_model=schemas.UserPublic, status_code=status.HTTP_201_CREATED)
def register_user(payload: schemas.UserCreate, db: Session = Depends(get_db)) -> schemas.UserPublic:
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
        password_hash=hash_password(payload.password) if payload.password else None,
    )
    db.add(user)
    db.flush()  # Ensure user.id is available

    # Generate embedding for local similarity fallback
    embedding_vector = semantic_service.embed(payload.secret_text)
    raw_bytes = vector_to_bytes(embedding_vector)
    encrypted_bytes = encrypt_embedding(raw_bytes)

    # Generate semantic summary using LLM (stores concept, NOT raw text)
    semantic_summary = generate_semantic_summary(payload.secret_text)
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

    return user


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
    )


@router.post("/login/complete", response_model=schemas.LoginResult)
def login_complete(payload: schemas.LoginCompleteRequest, db: Session = Depends(get_db)) -> schemas.LoginResult:
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
        llm_score = score_semantic_similarity(semantic_summary, payload.response_text)
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

    # Hard-reject near-empty responses (1-2 words can never convey a full concept)
    response_stripped = (payload.response_text or "").strip()
    word_count = len(response_stripped.split())
    if word_count <= 2:
        similarity = min(similarity, 0.3)

    challenge.attempt_count += 1

    max_attempts = getattr(settings, "max_login_attempts", 3)
    success_threshold = settings.similarity_threshold
    near_threshold = max(0.0, success_threshold - 0.1)

    result_type = models.LoginResultType.FAILURE
    message = "We could not match your description closely enough. You can try again."
    token: Optional[str] = None

    if similarity >= success_threshold:
        result_type = models.LoginResultType.SUCCESS
        message = "Authentication successful."
        token = create_access_token(subject=str(user.id), extra_claims={"username": user.username})
        challenge.status = models.LoginChallengeStatus.COMPLETED
    elif similarity >= near_threshold and challenge.attempt_count < max_attempts:
        message = (
            "Your answer is close to what we expect. "
            "Please add a bit more detail or express the idea in a different way."
        )
    elif challenge.attempt_count >= max_attempts:
        result_type = models.LoginResultType.LOCKED
        message = "Too many unsuccessful attempts for this challenge. Please start a new login."
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
    )


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
) -> None:
    """Remove all existing secret embeddings for user and add one new one (text or voice)."""
    db.query(models.SecretEmbedding).filter(models.SecretEmbedding.user_id == user_id).delete()
    embedding_vector = semantic_service.embed(secret_text)
    raw_bytes = vector_to_bytes(embedding_vector)
    encrypted_bytes = encrypt_embedding(raw_bytes)
    semantic_summary = generate_semantic_summary(secret_text)
    semantic_summary_encrypted = encrypt_text(semantic_summary) if semantic_summary else None
    secret_embedding = models.SecretEmbedding(
        user_id=user_id,
        secret_type=secret_type,
        embedding_encrypted=encrypted_bytes,
        semantic_summary_encrypted=semantic_summary_encrypted,
        model_name=settings.embedding_model_name,
    )
    db.add(secret_embedding)


@router.post("/profile/secret", response_model=schemas.ProfileResponse)
def update_profile_secret_text(
    payload: schemas.SecretUpdateText,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> schemas.ProfileResponse:
    """Set semantic secret to a new text phrase. Overwrites voice secret if present (one per account)."""
    _replace_secret_for_user(db, user.id, payload.secret_text, models.SecretType.TEXT)
    db.commit()
    db.refresh(user)
    return _profile_response(user, db)


@router.post("/profile/secret/voice", response_model=schemas.ProfileResponse)
async def update_profile_secret_voice(
    file: UploadFile = File(...),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> schemas.ProfileResponse:
    """Set semantic secret from spoken audio. Overwrites text secret if present (one per account)."""
    audio_bytes = await file.read()
    secret_text = transcribe_audio(file.filename or "audio.wav", audio_bytes)
    if not secret_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to transcribe the provided audio.",
        )
    _replace_secret_for_user(db, user.id, secret_text, models.SecretType.VOICE)
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

