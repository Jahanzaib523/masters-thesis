import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import settings
from .db import Base, engine
from . import models  # noqa: F401
from .routers import auth as auth_router
from .routers import voice_auth as voice_auth_router
from . import web as web_routes


# Allow frontend (Vite dev or built SPA) to call API
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")


def create_app() -> FastAPI:
    """Application factory for the SAS FastAPI app."""

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
        allow_origins=[FRONTEND_ORIGIN, "http://127.0.0.1:5173", "http://localhost:5173"],
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

    # Routers
    app.include_router(auth_router.router, prefix="/auth", tags=["auth"])
    app.include_router(voice_auth_router.router, prefix="/auth", tags=["auth-voice"])

    # Web UI (HTML forms)
    app.include_router(web_routes.router, prefix="/web", tags=["web"])

    # Static files (Jinja2 web UI)
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    # Optional: serve built Vite SPA from frontend/dist (run: cd frontend && npm run build)
    frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="spa-assets")

        @app.get("/{path:path}", include_in_schema=False)
        def serve_spa(path: str):
            if path.startswith(("auth/", "auth", "health", "web/", "static/", "docs", "openapi.json", "assets/")):
                from fastapi import HTTPException
                raise HTTPException(404)
            index_path = frontend_dist / "index.html"
            if index_path.is_file():
                return FileResponse(str(index_path))
            from fastapi import HTTPException
            raise HTTPException(404)

    return app


# Create database tables on startup (simple dev-time approach).
Base.metadata.create_all(bind=engine)

app = create_app()

