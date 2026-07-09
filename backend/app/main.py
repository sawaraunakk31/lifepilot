"""LifePilot FastAPI application entrypoint.

Serves the JSON API under /api/* and the built-in web UI from /static.
Run:  uvicorn app.main:app --reload
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.llm.provider import get_provider
from app.routers import agent, opportunities, profiles

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/api/health", tags=["health"])
def health():
    provider = get_provider()
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
        "llm_provider": provider.name,
        "llm_available": provider.available(),
    }


app.include_router(profiles.router)
app.include_router(opportunities.router)
app.include_router(agent.router)

# ---- Static frontend (built-in single-page UI) ----
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))
