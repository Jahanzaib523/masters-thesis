from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .db import get_db
from .routers.auth import login_complete, login_init, register_user
from .routers.voice_auth import voice_register, voice_login_init, voice_login_complete
from . import schemas

templates = Jinja2Templates(directory="app/templates")

router = APIRouter()


# =============================================================================
# Root
# =============================================================================


@router.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/web/login", status_code=302)


# =============================================================================
# Text Registration/Login
# =============================================================================


@router.get("/register", include_in_schema=False)
async def register_form(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "error": None},
    )


@router.post("/register", include_in_schema=False)
async def register_submit(
    request: Request,
    username: str = Form(...),
    email: str | None = Form(None),
    password: str | None = Form(None),
    secret_text: str = Form(...),
    db: Session = Depends(get_db),
):
    payload = schemas.UserCreate(
        username=username,
        email=email,
        password=password,
        secret_text=secret_text,
    )
    try:
        user = register_user(payload, db)
    except Exception as exc:  # noqa: BLE001
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": str(exc)},
            status_code=400,
        )

    return templates.TemplateResponse(
        "register_success.html",
        {"request": request, "user": user},
    )


@router.get("/login", include_in_schema=False)
async def login_form(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": None, "challenge_id": None, "prompt": None},
    )


@router.post("/login/start", include_in_schema=False)
async def login_start(
    request: Request,
    identifier: str = Form(...),
    db: Session = Depends(get_db),
):
    payload = schemas.LoginInitRequest(identifier=identifier)
    try:
        init_resp = login_init(payload, db)
    except Exception as exc:  # noqa: BLE001
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": str(exc),
                "challenge_id": None,
                "prompt": None,
            },
            status_code=400,
        )

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": None,
            "challenge_id": init_resp.challenge_id,
            "prompt": init_resp.prompt,
        },
    )


@router.post("/login/complete", include_in_schema=False)
async def login_finish(
    request: Request,
    challenge_id: int = Form(...),
    response_text: str = Form(...),
    db: Session = Depends(get_db),
):
    payload = schemas.LoginCompleteRequest(
        challenge_id=challenge_id,
        response_text=response_text,
    )
    try:
        result = login_complete(payload, db)
    except Exception as exc:  # noqa: BLE001
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": str(exc),
                "challenge_id": challenge_id,
                "prompt": None,
            },
            status_code=400,
        )

    return templates.TemplateResponse(
        "login_result.html",
        {"request": request, "result": result},
    )


# =============================================================================
# Voice Registration/Login (for blind users)
# =============================================================================


@router.get("/voice/register", include_in_schema=False)
async def voice_register_form(request: Request):
    return templates.TemplateResponse(
        "voice_register.html",
        {"request": request, "error": None},
    )


@router.post("/voice/register", include_in_schema=False)
async def voice_register_submit(
    request: Request,
    username: str = Form(...),
    email: str | None = Form(None),
    password: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        user = await voice_register(
            username=username,
            email=email,
            password=password,
            file=file,
            db=db,
        )
    except Exception as exc:  # noqa: BLE001
        return templates.TemplateResponse(
            "voice_register.html",
            {"request": request, "error": str(exc)},
            status_code=400,
        )

    return templates.TemplateResponse(
        "register_success.html",
        {"request": request, "user": user},
    )


@router.get("/voice/login", include_in_schema=False)
async def voice_login_form(request: Request):
    return templates.TemplateResponse(
        "voice_login.html",
        {"request": request, "error": None, "challenge_id": None, "prompt": None},
    )


@router.post("/voice/login/init", include_in_schema=False)
async def voice_login_init_web(
    request: Request,
    identifier: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        init_resp = await voice_login_init(identifier=identifier, db=db)
    except Exception as exc:  # noqa: BLE001
        return templates.TemplateResponse(
            "voice_login.html",
            {"request": request, "error": str(exc), "challenge_id": None, "prompt": None},
            status_code=400,
        )

    return templates.TemplateResponse(
        "voice_login.html",
        {
            "request": request,
            "error": None,
            "challenge_id": init_resp.challenge_id,
            "prompt": init_resp.prompt,
        },
    )


@router.post("/voice/login/complete", include_in_schema=False)
async def voice_login_complete_web(
    request: Request,
    challenge_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        result = await voice_login_complete(challenge_id=challenge_id, file=file, db=db)
    except Exception as exc:  # noqa: BLE001
        return templates.TemplateResponse(
            "voice_login.html",
            {"request": request, "error": str(exc), "challenge_id": challenge_id, "prompt": None},
            status_code=400,
        )

    return templates.TemplateResponse(
        "login_result.html",
        {"request": request, "result": result},
    )



