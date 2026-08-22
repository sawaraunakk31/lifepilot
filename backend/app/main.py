"""LifePilot FastAPI application entrypoint.

Serves the JSON API under /api/* and the built-in web UI from /static.
Run:  uvicorn app.main:app --reload
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Force UTF-8 encoding for Windows terminals to prevent charmap UnicodeEncodeErrors
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.llm.provider import get_provider
from app.routers import agent, opportunities, profiles
from app.security import add_security

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

app = FastAPI(title=settings.app_name, version="2.0.0")

# Security hardening
add_security(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    # Initialize LLM provider
    provider = get_provider()
    logging.getLogger("lifepilot").info(f"LLM provider: {provider.name} (available: {provider.available()})")
    # Initialize ChromaDB
    try:
        from app.knowledge.vectorstore import get_vectorstore
        vs = get_vectorstore()
        logging.getLogger("lifepilot").info(f"ChromaDB: {vs.count()} documents indexed")
    except Exception as e:
        logging.getLogger("lifepilot").warning(f"ChromaDB init skipped: {e}")


@app.get("/api/health", tags=["health"])
def health():
    provider = get_provider()
    chroma_count = 0
    try:
        from app.knowledge.vectorstore import get_vectorstore
        chroma_count = get_vectorstore().count()
    except Exception:
        pass

    return {
        "status": "ok",
        "app": settings.app_name,
        "version": "2.0.0",
        "environment": settings.environment,
        "llm_provider": provider.name,
        "llm_available": provider.available(),
        "vector_db_documents": chroma_count,
        "scraping_enabled": settings.scraping_enabled,
    }


app.include_router(profiles.router)
app.include_router(opportunities.router)
app.include_router(agent.router)

# ---- Static frontend (built-in single-page UI) ----
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))
