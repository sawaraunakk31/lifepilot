"""AI Assistant service — RAG-powered, context-aware Q&A.

Uses the RAG pipeline (ChromaDB + LLM) for intelligent answers grounded
on the user's real matches and the knowledge base. Maintains conversation
memory for context continuity.
"""
from __future__ import annotations

import logging

from app.knowledge.rag import rag_answer
from app.memory.store import add_message, get_context_string

logger = logging.getLogger("lifepilot.assistant")


def answer(
    question: str,
    matches: list[dict],
    name: str | None = None,
    profile_id: int | None = None,
    profile: dict | None = None,
) -> dict:
    """Answer a user question using RAG + conversation memory."""

    # Add user message to memory
    if profile_id:
        add_message(profile_id, "user", question)

    # Get conversation context
    context = ""
    if profile_id:
        context = get_context_string(profile_id, last_n=3)

    # Build profile dict if not provided
    if not profile and name:
        profile = {"name": name}

    # Use RAG pipeline for the answer
    reply = rag_answer(
        question=question,
        matches=matches,
        profile=profile,
    )

    # Store assistant response in memory
    if profile_id:
        add_message(profile_id, "assistant", reply)

    return {
        "answer": reply,
        "grounded_on": len(matches),
    }
