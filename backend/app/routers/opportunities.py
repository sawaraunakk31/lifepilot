"""Opportunities endpoint - exposes the curated dataset for browsing."""
from __future__ import annotations

from fastapi import APIRouter

from app.agents.orchestrator import _load_opportunities

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


@router.get("")
def list_opportunities():
    opps = _load_opportunities()
    # Return a browse-friendly view (hide internal criteria matching structure detail).
    return [
        {
            "id": o["id"],
            "title": o["title"],
            "provider": o.get("provider"),
            "url": o.get("url"),
            "amount": o.get("amount"),
            "deadline": o.get("deadline"),
            "category": o.get("category"),
            "description": o.get("description"),
            "documents": o.get("documents", []),
        }
        for o in opps
    ]
