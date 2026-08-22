"""Conversation memory store — persists chat history per user session.

Uses SQLite (via the existing database) for cross-session persistence.
Keeps the last N messages per user to provide context to the LLM.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone

logger = logging.getLogger("lifepilot.memory")

# In-memory store (persists for the server lifetime; can be backed by DB later)
_conversations: dict[int, list[dict]] = defaultdict(list)
MAX_HISTORY = 20


def add_message(profile_id: int, role: str, content: str) -> None:
    """Add a message to the conversation history."""
    _conversations[profile_id].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    # Trim to max history
    if len(_conversations[profile_id]) > MAX_HISTORY:
        _conversations[profile_id] = _conversations[profile_id][-MAX_HISTORY:]


def get_history(profile_id: int, last_n: int = 10) -> list[dict]:
    """Get recent conversation history for a user."""
    return _conversations.get(profile_id, [])[-last_n:]


def get_context_string(profile_id: int, last_n: int = 5) -> str:
    """Get conversation history formatted as a context string for LLM."""
    history = get_history(profile_id, last_n)
    if not history:
        return ""
    lines = ["## Recent Conversation:"]
    for msg in history:
        role = "User" if msg["role"] == "user" else "LifePilot"
        lines.append(f"{role}: {msg['content'][:200]}")
    return "\n".join(lines)


def clear_history(profile_id: int) -> None:
    """Clear conversation history for a user."""
    _conversations.pop(profile_id, None)
