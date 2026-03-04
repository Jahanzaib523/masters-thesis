from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..groq_client import transcribe_audio, synthesize_speech
from ..routers.auth import login_complete, login_init, register_user
from .. import schemas

router = APIRouter()


@router.post("/voice/register", response_model=schemas.UserPublic, status_code=status.HTTP_201_CREATED)
async def voice_register(
    username: str = Form(...),
    email: str | None = Form(None),
    password: str | None = Form(None),
    file: UploadFile = File(..., description="Audio file with spoken secret"),
    db: Session = Depends(get_db),
):
    """Voice-based registration: transcribe spoken secret, then register."""

    audio_bytes = await file.read()
    secret_text = transcribe_audio(file.filename or "audio.wav", audio_bytes)
    if not secret_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to transcribe the provided audio.",
        )

    payload = schemas.UserCreate(
        username=username,
        email=email,
        password=password,
        secret_text=secret_text,
        secret_type="voice",  # Mark as voice-registered
    )
    return register_user(payload, db)


@router.post("/voice/login/init", response_model=schemas.LoginInitResponse)
async def voice_login_init(
    identifier: str = Form(...),
    db: Session = Depends(get_db),
):
    """Initialize voice login challenge (same as text init, just form-based)."""

    payload = schemas.LoginInitRequest(identifier=identifier)
    return login_init(payload, db)


@router.post("/voice/login/complete", response_model=schemas.LoginResult)
async def voice_login_complete(
    challenge_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Complete voice login: transcribe spoken response, then run semantic login."""

    audio_bytes = await file.read()
    response_text = transcribe_audio(file.filename or "audio", audio_bytes)
    if not response_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to transcribe the provided audio.",
        )

    payload = schemas.LoginCompleteRequest(challenge_id=challenge_id, response_text=response_text)
    return login_complete(payload, db)

