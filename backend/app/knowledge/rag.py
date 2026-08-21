"""RAG (Retrieval-Augmented Generation) pipeline.

Retrieves relevant scheme context from ChromaDB, augments the user's
question with that context, and sends it to the LLM for a grounded answer.
"""
from __future__ import annotations

import logging

from app.knowledge.vectorstore import search as vector_search
from app.llm.provider import get_provider

logger = logging.getLogger("lifepilot.knowledge.rag")

_RAG_PROMPT = """You are LifePilot, an AI assistant helping Indian citizens discover and apply for government schemes, scholarships, and grants.

## Context — Relevant Schemes:
{context}

## User's Profile Summary:
{profile_summary}

## User's Matched Schemes (if any):
{matches_summary}

## User's Question:
{question}

## Instructions:
1. Answer ONLY based on the context and matches above. Do NOT invent schemes.
2. Be specific — mention scheme names, amounts, deadlines, documents.
3. Be warm and encouraging but factual.
4. If the context doesn't cover the question, say so honestly.
5. Format nicely with bullet points where helpful.
"""


def rag_answer(
    question: str,
    matches: list[dict] | None = None,
    profile: dict | None = None,
) -> str:
    """Answer a question using RAG: vector search + LLM."""
    llm = get_provider()

    # Retrieve relevant context from vector store
    context_docs = vector_search(question, n_results=5)
    context_text = ""
    if context_docs:
        lines = []
        for doc in context_docs:
            lines.append(
                f"- {doc.get('title', 'Unknown')}: {doc.get('description', '')} "
                f"| Amount: {doc.get('amount', 'N/A')} | Deadline: {doc.get('deadline', 'N/A')}"
            )
        context_text = "\n".join(lines)
    else:
        context_text = "No additional context available from knowledge base."

    # Summarize matches
    matches_summary = "No matches computed yet."
    if matches:
        eligible = [m for m in matches if m.get("eligible")]
        if eligible:
            lines = [f"User is eligible for {len(eligible)} scheme(s):"]
            for m in eligible[:5]:
                lines.append(f"  - {m['title']}: {m.get('amount', 'N/A')}")
            matches_summary = "\n".join(lines)
        else:
            matches_summary = f"User has {len(matches)} partial matches but none fully eligible yet."

    # Profile summary
    profile_summary = "No profile available."
    if profile:
        parts = []
        if profile.get("name"):
            parts.append(f"Name: {profile['name']}")
        if profile.get("category"):
            parts.append(f"Category: {profile['category']}")
        if profile.get("state"):
            parts.append(f"State: {profile['state']}")
        if profile.get("education_level"):
            parts.append(f"Education: {profile['education_level']}")
        if profile.get("annual_income"):
            parts.append(f"Income: ₹{profile['annual_income']:,}")
        profile_summary = ", ".join(parts) if parts else "Incomplete profile."

    prompt = _RAG_PROMPT.format(
        context=context_text,
        profile_summary=profile_summary,
        matches_summary=matches_summary,
        question=question,
    )

    if llm.name != "mock":
        try:
            answer = llm.generate(
                prompt,
                system="You are LifePilot, a helpful civic AI assistant. Be concise, warm, factual."
            )
            if answer and len(answer) > 20:
                return answer
        except Exception as e:
            logger.warning(f"RAG LLM call failed: {e}")

    # Fallback for mock/offline
    return _offline_answer(question, matches or [], profile)


def _offline_answer(question: str, matches: list[dict], profile: dict | None) -> str:
    """Simple keyword-based fallback when LLM is unavailable."""
    q = question.lower()
    eligible = [m for m in matches if m.get("eligible")]

    if any(w in q for w in ("eligible", "qualify", "can i")):
        if eligible:
            lines = [f"You're eligible for {len(eligible)} scheme(s):"]
            for m in eligible[:5]:
                lines.append(f"• {m['title']} — {m.get('amount', 'N/A')}")
            return "\n".join(lines)
        return "No fully eligible schemes found yet. Complete your profile for better matches."

    if any(w in q for w in ("document", "papers", "checklist")):
        docs = set()
        for m in eligible:
            for d in m.get("documents", []):
                docs.add(d)
        if docs:
            return "Documents you'll need:\n" + "\n".join(f"• {d}" for d in sorted(docs))
        return "No documents to prepare yet."

    if any(w in q for w in ("deadline", "when", "date")):
        lines = ["Upcoming deadlines:"]
        for m in matches[:5]:
            if m.get("deadline"):
                lines.append(f"• {m['title']} — {m['deadline']}")
        return "\n".join(lines) if len(lines) > 1 else "No deadlines found."

    if any(w in q for w in ("how much", "benefit", "money", "amount")):
        if eligible:
            lines = [f"You could unlock benefits from {len(eligible)} scheme(s):"]
            for m in eligible[:5]:
                lines.append(f"• {m['title']} — {m.get('amount', 'varies')}")
            return "\n".join(lines)

    return (
        f"You have {len(eligible)} eligible and {len(matches) - len(eligible)} partial matches. "
        f"Ask about eligibility, documents, deadlines, or any specific scheme!"
    )
