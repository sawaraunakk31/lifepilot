"""Opportunities endpoint - exposes the curated dataset for browsing."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])

@router.get("")
def list_opportunities():
    # In the new LangGraph architecture, opportunities are dynamically discovered 
    # and scraped based on the user's profile. We no longer serve a static list.
    return []
