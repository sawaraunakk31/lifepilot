"""Flexible, grounded AI assistant over a user's opportunity matches.

Understands greetings, help, benefits, documents, deadlines, eligibility,
"how do I apply", gaps, comparisons, and *scheme-specific* questions
(e.g. "am I eligible for Pragati?", "documents for Startup India").

Answers are grounded on real data (matches + dataset) so nothing is invented.
The configured LLM (if any, e.g. local Ollama) only rephrases the final text.
Runs fully offline with the default mock provider.
"""
from __future__ import annotations

import re
from datetime import date

from app.agents.orchestrator import _load_opportunities
from app.llm.provider import get_provider
from app.services import analytics

_STOP = {
    "the", "for", "and", "of", "scheme", "schemes", "scholarship", "scholarships",
    "students", "student", "india", "national", "with", "students", "yojana", "fund",
}


def _days_left(deadline: str | None) -> int | None:
    if not deadline:
        return None
    try:
        return (date.fromisoformat(deadline) - date.today()).days
    except ValueError:
        return None


def _norm(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()) + " "


def _has(q: str, *words: str) -> bool:
    return any(re.search(r"\b" + re.escape(w) + r"\b", q) for w in words)


def _scheme_tokens(opp: dict) -> set[str]:
    toks: set[str] = set()
    for t in re.split(r"[^a-z0-9]+", opp["title"].lower()):
        if len(t) >= 4 and t not in _STOP:
            toks.add(t)
    for t in opp["id"].lower().split("-"):
        if len(t) >= 2 and t not in _STOP:
            toks.add(t)
    return toks


def _find_scheme(q: str, opportunities: list[dict]) -> dict | None:
    best, best_score = None, 0
    for opp in opportunities:
        score = sum(1 for t in _scheme_tokens(opp) if re.search(r"\b" + re.escape(t) + r"\b", q))
        if score > best_score:
            best, best_score = opp, score
    return best if best_score >= 1 else None


def _match_for(opp_id: str, matches: list[dict]) -> dict | None:
    return next((m for m in matches if m["opportunity_id"] == opp_id), None)


# ─────────────── scheme-specific answers ───────────────
def _answer_scheme(q: str, opp: dict, matches: list[dict], name: str | None) -> str:
    m = _match_for(opp["id"], matches)
    title = opp["title"]
    amount = opp.get("amount", "—")
    deadline = opp.get("deadline")
    dleft = _days_left(deadline)

    header = f"**{title}**"
    status = ""
    if m:
        if m["eligible"]:
            status = f"\n✅ You appear ELIGIBLE (match {round(m['score']*100)}%)."
        else:
            gaps = "; ".join(m.get("unmet", [])[:3])
            status = f"\n⚠️ Not fully eligible yet. To qualify: {gaps or 'complete your profile'}."

    if _has(q, "document", "documents", "papers", "certificate", "need", "require", "requirements", "checklist"):
        docs = "\n".join(f"• {d}" for d in opp.get("documents", []))
        return f"{header} — documents you'll need:\n{docs}{status}"

    if _has(q, "deadline", "last", "date", "when", "due", "closing", "expire", "by"):
        d = f"{deadline} ({dleft} days left)" if dleft is not None and dleft >= 0 else (deadline or "see portal")
        return f"{header}\n📅 Deadline: {d}{status}"

    if _has(q, "how", "apply", "steps", "process", "procedure", "where"):
        steps = ""
        if m and m.get("roadmap"):
            steps = "\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(m["roadmap"]))
        else:
            steps = f"\nApply on the official portal: {opp.get('url')}"
        return f"{header} — how to apply:{steps}{status}"

    if _has(q, "eligible", "eligibility", "qualify", "can", "am"):
        if m:
            good = "; ".join(m.get("reasons", [])[:3])
            return f"{header}{status}\nWhy: {good or 'based on your profile'}"
        return f"{header} — run LifePilot from your profile to check your eligibility.{status}"

    # general scheme summary
    d = f"{deadline} ({dleft}d left)" if dleft is not None and dleft >= 0 else (deadline or "see portal")
    return (f"{header}\n{opp.get('description', '')}\n💰 {amount}\n📅 {d}\n🔗 {opp.get('url', '')}{status}")


# ─────────────── global answers ───────────────
def _answer_core(question: str, matches: list[dict], name: str | None) -> str:
    q = _norm(question)
    who = name or "you"
    eligible = [m for m in matches if m["eligible"]]
    opportunities = _load_opportunities()

    # Greeting / thanks / help
    if _has(q, "hi", "hello", "hey", "namaste", "hola") and len(question.split()) <= 4:
        return (f"Hello {who.split()[0] if name else 'there'}! I can help you understand your "
                f"{len(eligible)} eligible scheme(s) — ask about benefits, documents, deadlines, "
                f"how to apply, or any specific scheme by name.")
    if _has(q, "thanks", "thank", "thankyou", "thx"):
        return "You're welcome! Want me to list your document checklist or the nearest deadline next?"
    if _has(q, "help") or _has(q, "what", "can", "you", "do") and _has(q, "you"):
        return ("I'm grounded on your real matches. Try:\n"
                "• \"How much can I unlock?\"\n"
                "• \"Which schemes am I eligible for?\"\n"
                "• \"What documents do I need?\"\n"
                "• \"When are the deadlines?\"\n"
                "• \"How do I apply for Pragati?\"\n"
                "• \"Why am I not eligible for more?\"")

    # Scheme-specific question takes priority when a scheme is clearly named.
    scheme = _find_scheme(q, opportunities)
    if scheme and _has(q, "pragati", "yasasvi", "vidyasiri", "inspire", "startup", "kaushal",
                       "pmkvy", "matric", "central", "sector", "disabilit", "seed") :
        return _answer_scheme(q, scheme, matches, name)

    # Benefit / money
    if _has(q, "how", "much") or _has(q, "benefit", "money", "worth", "value", "unlock", "amount", "stipend", "earn", "get"):
        ins = analytics.build_insights(matches)
        if eligible:
            lines = [f"You're eligible for {len(eligible)} scheme(s), worth an estimated "
                     f"{ins['estimated_benefit_label']} per year combined:"]
            lines += [f"• {m['title']} — {m.get('amount')}" for m in eligible[:6]]
            return "\n".join(lines)
        return "No fully-eligible schemes yet — add more profile details to unlock matches."

    # Documents
    if _has(q, "document", "documents", "papers", "certificate", "checklist", "requirements", "need", "submit"):
        ins = analytics.build_insights(matches)
        if ins["master_documents"]:
            docs = [f"• {d['document']} (used by {d['used_by']} scheme(s))" for d in ins["master_documents"][:10]]
            return "Your combined document checklist:\n" + "\n".join(docs)
        return "No documents to prepare yet — you have no eligible schemes so far."

    # Deadlines
    if _has(q, "deadline", "last", "date", "when", "due", "closing", "expire", "closes"):
        opens = [m for m in matches if (_days_left(m.get("deadline")) or -1) >= 0]
        opens.sort(key=lambda m: _days_left(m.get("deadline")) or 9999)
        if opens:
            lines = ["Upcoming deadlines (soonest first):"]
            lines += [f"• {m['title']} — {m.get('deadline')} ({_days_left(m.get('deadline'))} days left)" for m in opens[:6]]
            return "\n".join(lines)
        return "No open deadlines were found in the current dataset."

    # Gaps / improve
    if _has(q, "why", "not") or _has(q, "gap", "gaps", "missing", "improve", "increase", "more"):
        partial = [m for m in matches if not m["eligible"]]
        if partial:
            lines = ["To unlock more schemes, address these gaps:"]
            for m in partial[:5]:
                if m.get("unmet"):
                    lines.append(f"• {m['title']}: {m['unmet'][0]}")
            return "\n".join(lines)
        return "Great news — you meet the criteria for every matched scheme!"

    # Compare / best / top
    if _has(q, "compare", "best", "top", "rank", "recommend", "which", "suggest"):
        if eligible:
            top = sorted(eligible, key=lambda m: (-m["score"], _days_left(m.get("deadline")) or 9999))
            lines = ["Your best options right now:"]
            for m in top[:5]:
                d = _days_left(m.get("deadline"))
                dtxt = f", closes in {d}d" if d is not None and d >= 0 else ""
                lines.append(f"• {m['title']} — {m.get('amount')} (match {round(m['score']*100)}%{dtxt})")
            return "\n".join(lines)

    # Eligibility list
    if _has(q, "eligible", "eligibility", "qualify", "apply", "can", "entitled"):
        if eligible:
            lines = [f"{who} qualify for {len(eligible)} scheme(s):"]
            lines += [f"• {m['title']} — {m.get('amount')} (match {round(m['score']*100)}%)" for m in eligible[:6]]
            return "\n".join(lines)
        partial = [m for m in matches if not m["eligible"]][:1]
        if partial:
            tips = "; ".join(partial[0].get("unmet", [])[:2])
            return f"No full matches yet. Closest: {partial[0]['title']}. To qualify: {tips or 'complete your profile'}."
        return "Run LifePilot from your profile first to see eligible schemes."

    # Count
    if _has(q, "how", "many"):
        return f"You have {len(eligible)} fully-eligible and {len(matches) - len(eligible)} partial matches."

    # If a scheme was detected without a clear intent keyword, still answer about it.
    if scheme:
        return _answer_scheme(q, scheme, matches, name)

    # Fallback
    ins = analytics.build_insights(matches)
    return (f"You have {ins['eligible_count']} eligible and {ins['partial_count']} partial matches, "
            f"worth about {ins['estimated_benefit_label']}/year. Ask me about a specific scheme, or about "
            f"eligibility, documents, deadlines, benefits, or how to apply.")


def answer(question: str, matches: list[dict], name: str | None = None) -> dict:
    core = _answer_core(question, matches, name)
    provider = get_provider()
    if provider.name != "mock" and provider.available():
        prompt = (
            "Rephrase this factual answer for a citizen in a warm, clear, concise tone. "
            "Do NOT add new facts, numbers, or schemes. Preserve all bullet points and figures.\n\n"
            f"Answer:\n{core}"
        )
        phrased = provider.generate(prompt, system="You are LifePilot, a helpful civic assistant.")
        if phrased:
            core = phrased
    return {"answer": core, "grounded_on": len(matches)}
