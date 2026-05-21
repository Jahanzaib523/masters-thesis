import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import inspect, text

from .config import log_hf_env_diagnostics, resolve_hf_api_token, settings
from .db import Base, engine
from . import models  # noqa: F401
from .routers import auth as auth_router
from .routers import voice_auth as voice_auth_router
from . import web as web_routes
from .greeting_image import get_image_generation_health


def create_app() -> FastAPI:
    """Main entry point for the FastAPI app."""

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Semantic Authentication System (SAS) prototype - AI-driven usability-based "
            "user authentication with inclusive accessibility design.\n\n"
            "Supports:\n"
            "- **Text auth**: Type your semantic secret\n"
            "- **Voice auth**: Speak your secret (for blind users, with TTS prompts)\n\n"
            "All AI services use Groq free tier."
        ),
    )

    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin, "http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"])
    async def health():
        """Simple health check endpoint."""

        return {
            "status": "ok",
            "app_name": settings.app_name,
            "version": settings.app_version,
        }

    @app.get("/health/image-generation", tags=["system"])
    async def image_generation_health():
        """Image generation provider health for startup/config verification."""
        return get_image_generation_health()

    @app.get("/health/hf-env", tags=["system"])
    async def hf_env_diagnostics():
        """Safe diagnostics: which sources contain an HF token (no secrets returned)."""

        def _present(key: str) -> bool:
            return bool(os.environ.get(key, "").strip())

        tok_settings = bool((settings.hf_api_token or "").strip())
        resolved = bool(resolve_hf_api_token())
        return {
            "env_hf_api_token": _present("HF_API_TOKEN"),
            "env_hf_token": _present("HF_TOKEN"),
            "env_huggingface_hub_token": _present("HUGGING_FACE_HUB_TOKEN"),
            "settings_hf_api_token_nonempty": tok_settings,
            "resolved_token_available": resolved,
            "hint": (
                "If resolved_token_available is false, set HF_API_TOKEN or HF_TOKEN in the environment "
                "or remove empty HF_API_TOKEN=\"\" from app/.env"
            ),
        }

    # Routers
    app.include_router(auth_router.router, prefix="/auth", tags=["auth"])
    app.include_router(voice_auth_router.router, prefix="/auth", tags=["auth-voice"])

    # Web UI (HTML forms)
    app.include_router(web_routes.router, prefix="/web", tags=["web"])

    @app.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
    def serve_robots():
        return "User-agent: *\nDisallow: /\n"

    # Static files (Jinja2 web UI)
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    # Optional: serve built Vite SPA from frontend/dist (run: cd frontend && npm run build)
    frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="spa-assets")

        @app.get("/{path:path}", include_in_schema=False)
        def serve_spa(path: str):
            # Only serve index.html for known React Router pages
            clean_path = path.strip("/")
            if clean_path in ("", "register", "login", "result", "profile", "help"):
                index_path = frontend_dist / "index.html"
                if index_path.is_file():
                    return FileResponse(str(index_path))
            from fastapi import HTTPException
            raise HTTPException(404)

    return app


# Create database tables on startup (simple dev-time approach).
Base.metadata.create_all(bind=engine)


def _ensure_user_greeting_image_columns() -> None:
    """Quick script to make sure the database has the right columns for greeting images."""
    with engine.begin() as conn:
        inspector = inspect(conn)
        cols = {col["name"] for col in inspector.get_columns("users")}
        if "greeting_image_bytes" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN greeting_image_bytes BLOB"))
        if "greeting_image_mime" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN greeting_image_mime VARCHAR(64)"))
        if "login_mode" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN login_mode VARCHAR(32) NOT NULL DEFAULT 'both'"))


_ensure_user_greeting_image_columns()


def _ensure_login_challenge_gallery() -> None:
    """Add columns for the 6-image login challenge."""
    with engine.begin() as conn:
        inspector = inspect(conn)
        tables = inspector.get_table_names()
        if "login_challenges" in tables:
            cols = {c["name"] for c in inspector.get_columns("login_challenges")}
            if "image_gallery_verified_at" not in cols:
                conn.execute(text("ALTER TABLE login_challenges ADD COLUMN image_gallery_verified_at DATETIME"))
            if "image_pick_failures" not in cols:
                conn.execute(text("ALTER TABLE login_challenges ADD COLUMN image_pick_failures INTEGER NOT NULL DEFAULT 0"))
        if "login_challenge_gallery_slots" not in tables:
            conn.execute(
                text(
                    """
                    CREATE TABLE login_challenge_gallery_slots (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        challenge_id INTEGER NOT NULL,
                        slot INTEGER NOT NULL,
                        image_bytes BLOB NOT NULL,
                        image_mime VARCHAR(64) NOT NULL,
                        is_target INTEGER NOT NULL DEFAULT 0,
                        FOREIGN KEY(challenge_id) REFERENCES login_challenges (id)
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_gallery_challenge_slot "
                    "ON login_challenge_gallery_slots (challenge_id, slot)"
                )
            )


_ensure_login_challenge_gallery()


def _ensure_user_gallery_pool() -> None:
    """Add columns for pre-generated galleries."""
    with engine.begin() as conn:
        inspector = inspect(conn)
        tables = inspector.get_table_names()
        if "user_gallery_pool_slots" not in tables:
            conn.execute(
                text(
                    """
                    CREATE TABLE user_gallery_pool_slots (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        slot INTEGER NOT NULL,
                        image_bytes BLOB NOT NULL,
                        image_mime VARCHAR(64) NOT NULL,
                        is_target INTEGER NOT NULL DEFAULT 0,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(user_id) REFERENCES users (id)
                    )
                    """
                )
            )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_gallery_slot "
                "ON user_gallery_pool_slots (user_id, slot)"
            )
        )


_ensure_user_gallery_pool()

log_hf_env_diagnostics()

app = create_app()

