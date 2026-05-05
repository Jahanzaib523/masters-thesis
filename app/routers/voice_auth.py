from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..db import get_db
from ..groq_client import transcribe_audio, synthesize_speech
from ..llm_provider import SemanticLlmBackend, get_semantic_llm_backend
from ..routers.auth import login_complete_core, login_init, register_user_core
from .. import schemas

router = APIRouter()


async def voice_register_service(
    username: str,
    email: str | None,
    password: str,
    image_text: str,
    file: UploadFile,
    db: Session,
    llm_backend: SemanticLlmBackend,
) -> schemas.UserPublic:
    """Transcribe audio then register (shared by /auth/voice/register and web UI)."""

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

    try:
        payload = schemas.UserCreate(
            username=username,
            email=email,
            password=password,
            secret_text=secret_text,
            image_text=image_text,
            secret_type="voice",
        )
    except ValidationError as exc:
        first = exc.errors()[0].get("msg", "Invalid input.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(first)) from exc
    return register_user_core(payload, db, llm_backend)


@router.post("/voice/register", response_model=schemas.UserPublic, status_code=status.HTTP_201_CREATED)
async def voice_register(
    username: str = Form(...),
    email: str | None = Form(None),
    password: str = Form(...),
    image_text: str = Form(...),
    file: UploadFile = File(..., description="Audio file with spoken secret"),
    db: Session = Depends(get_db),
    llm_backend: SemanticLlmBackend = Depends(get_semantic_llm_backend),
):
    """Voice-based registration: transcribe spoken secret, then register."""

    return await voice_register_service(username, email, password, image_text, file, db, llm_backend)


@router.post("/voice/login/init", response_model=schemas.LoginInitResponse)
def voice_login_init(
    identifier: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
    llm_backend: SemanticLlmBackend = Depends(get_semantic_llm_backend),
):
    """Initialize voice login challenge (same as text init, just form-based)."""

    payload = schemas.LoginInitRequest(identifier=identifier, password=password)
    return login_init(payload, db, llm_backend)


async def voice_login_complete_service(
    challenge_id: int,
    file: UploadFile,
    db: Session,
    llm_backend: SemanticLlmBackend,
) -> schemas.LoginResult:
    """Transcribe login response then complete challenge."""

    audio_bytes = await file.read()
    response_text = transcribe_audio(file.filename or "audio", audio_bytes)
    if not response_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to transcribe the provided audio.",
        )

    payload = schemas.LoginCompleteRequest(challenge_id=challenge_id, response_text=response_text)
    return login_complete_core(payload, db, llm_backend)


@router.post("/voice/login/complete", response_model=schemas.LoginResult)
async def voice_login_complete(
    challenge_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    llm_backend: SemanticLlmBackend = Depends(get_semantic_llm_backend),
):
    """Complete voice login: transcribe spoken response, then run semantic login."""

    return await voice_login_complete_service(challenge_id, file, db, llm_backend)
