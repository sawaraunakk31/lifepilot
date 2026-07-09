"""Lightweight AI assistant over a user's opportunity matches.

Deterministic intent detection provides grounded, factual answers (no hallucination),
and the configured LLM only rephrases the final answer when available. Works offline.
"""
from __future__ import annotations

from datetime import date

from app.llm.provider import get_provider
from app.services import analytics


def _days_left(deadline: str | None) -> int | None:
    if not deadline:
        return None
    try:
        return (date.fromisoformat(deadline) - date.today()).days
    except ValueError:
        return None


def _answer_core(question: str, matches: list[dict], name: str | None) -> str:
    q = question.lower().strip()
    eligible = [m for m in matches if m["eligible"]]

    # Intent: money / benefit
    if any(k in q for k in ["how much", "benefit", "money", "amount", "worth", "value", "unlock"]):
        ins = analytics.build_insights(matches)
        if eligible:
            lines = [f"You are eligible for {len(eligible)} scheme(s), worth an estimated "
                     f"{ins['estimated_benefit_label']} per year in combined benefits:"]
            for m in eligible[:5]:
                lines.append(f"• {m['title']} — {m.get('amount')}")
            return "\n".join(lines)
        return "No fully-eligible schemes yet, so no benefit estimate. Add more profile details to unlock matches."

    # Intent: documents
    if any(k in q for k in ["document", "papers", "certificate", "need to submit", "checklist"]):
        ins = analytics.build_insights(matches)
        if ins["master_documents"]:
            docs = [f"• {d['document']} (used by {d['used_by']} scheme(s))" for d in ins["master_documents"][:8]]
            return "Here is your combined document checklist:\n" + "\n".join(docs)
        return "No documents to prepare yet — you have no eligible schemes so far."

    # Intent: deadlines
    if any(k in q for k in ["deadline", "last date", "when", "expire", "closing", "due"]):
        opens = [m for m in matches if (_days_left(m.get("deadline")) or -1) >= 0]
        opens.sort(key=lambda m: _days_left(m.get("deadline")) or 9999)
        if opens:
            lines = ["Upcoming deadlines (soonest first):"]
            for m in opens[:5]:
                d = _days_left(m.get("deadline"))
                lines.append(f"• {m['title']} — {m.get('deadline')} ({d} days left)")
            return "\n".join(lines)
        return "No open deadlines were found in the current dataset."

    # Intent: eligibility list
    if any(k in q for k in ["eligible", "qualify", "which scheme", "what can i", "apply", "recommend", "best"]):
        if eligible:
            lines = [f"{name or 'You'} qualify for {len(eligible)} scheme(s):"]
            for m in eligible[:6]:
                lines.append(f"• {m['title']} — {m.get('amount')} (match {round(m['score']*100)}%)")
            return "\n".join(lines)
        partial = [m for m in matches if not m["eligible"]][:3]
        if partial:
            tips = "; ".join(partial[0].get("unmet", [])[:2])
            return ("No full matches yet. Closest option: "
                    f"{partial[0]['title']}. To qualify: {tips or 'complete your profile'}.")
        return "Run the agents from your profile first to see eligible schemes."

    # Intent: gaps / why not
    if any(k in q for k in ["why not", "gap", "missing", "improve", "increase"]):
        partial = [m for m in matches if not m["eligible"]]
        if partial:
            lines = ["To unlock more schemes, address these gaps:"]
            for m in partial[:4]:
                if m.get("unmet"):
                    lines.append(f"• {m['title']}: {m['unmet'][0]}")
            return "\n".join(lines)
        return "Great news — you meet the criteria for all matched schemes!"

    # Fallback summary
    ins = analytics.build_insights(matches)
    return (f"You have {ins['eligible_count']} eligible and {ins['partial_count']} partial matches, "
            f"worth about {ins['estimated_benefit_label']}/year. Ask me about eligibility, documents, "
            f"deadlines, or benefits.")


def answer(question: str, matches: list[dict], name: str | None = None) -> dict:
    core = _answer_core(question, matches, name)
    provider = get_provider()
    # Only let a *real* model rephrase; the mock returns text verbatim so we keep the grounded answer.
    if provider.name != "mock" and provider.available():
        prompt = (
            "Rephrase the following factual answer for a citizen in a warm, clear, concise tone. "
            "Do NOT add new facts, numbers, or schemes. Keep all bullet points.\n\n"
            f"Answer:\n{core}"
        )
        phrased = provider.generate(prompt, system="You are LifePilot, a helpful civic assistant.")
        if phrased:
            core = phrased
    return {"answer": core, "grounded_on": len(matches)}
