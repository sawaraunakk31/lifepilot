"""Analytics & insight engine.

Turns a list of eligibility matches into high-impact, demo-ready insights:
- estimated potential financial benefit (parsed from scheme amounts)
- a de-duplicated master document checklist across all eligible schemes
- application readiness given the documents a user already owns
- deadline urgency buckets
- category distribution & average confidence

Pure Python, deterministic, no external calls.
"""
from __future__ import annotations

import re
from datetime import date


def parse_amount(text: str | None) -> int:
    """Best-effort parse of an annual rupee value from a free-text amount string."""
    if not text:
        return 0
    nums = re.findall(r"\u20b9\s*([\d,]+)", text)
    values = [int(n.replace(",", "")) for n in nums if n.replace(",", "").isdigit()]
    if not values:
        return 0
    value = max(values)
    low = text.lower()
    if "/month" in low or "per month" in low or "month" in low:
        value *= 12
    return value


def _days_left(deadline: str | None) -> int | None:
    if not deadline:
        return None
    try:
        return (date.fromisoformat(deadline) - date.today()).days
    except ValueError:
        return None


def _urgency_level(days: int | None) -> str:
    if days is None:
        return "unknown"
    if days < 0:
        return "closed"
    if days <= 14:
        return "critical"
    if days <= 45:
        return "soon"
    return "comfortable"


def build_insights(matches: list[dict], owned_documents: list[str] | None = None) -> dict:
    owned = {d.strip().lower() for d in (owned_documents or []) if d.strip()}

    eligible = [m for m in matches if m["eligible"]]
    partial = [m for m in matches if not m["eligible"]]

    # Estimated potential annual benefit (eligible only; grants counted once).
    estimated_benefit = 0
    for m in eligible:
        estimated_benefit += parse_amount(m.get("amount"))

    # Master, de-duplicated document checklist across eligible schemes.
    doc_map: dict[str, dict] = {}
    for m in eligible:
        for doc in m.get("documents", []):
            key = doc.strip().lower()
            if key not in doc_map:
                doc_map[key] = {"document": doc, "schemes": [], "owned": key in owned}
            doc_map[key]["schemes"].append(m["title"])
    master_documents = sorted(
        (
            {
                "document": v["document"],
                "used_by": len(v["schemes"]),
                "schemes": v["schemes"],
                "owned": v["owned"],
            }
            for v in doc_map.values()
        ),
        key=lambda d: (-d["used_by"], d["document"].lower()),
    )

    total_docs = len(master_documents)
    owned_docs = sum(1 for d in master_documents if d["owned"])
    readiness = round(100 * owned_docs / total_docs) if total_docs else 0

    # Deadline urgency (open items only), soonest first.
    urgency = []
    for m in matches:
        days = _days_left(m.get("deadline"))
        urgency.append(
            {
                "title": m["title"],
                "deadline": m.get("deadline"),
                "days_left": days,
                "level": _urgency_level(days),
                "eligible": m["eligible"],
            }
        )
    urgency.sort(key=lambda u: (u["days_left"] is None, u["days_left"] if u["days_left"] is not None else 9999))

    open_count = sum(1 for u in urgency if (u["days_left"] or -1) >= 0)
    critical = [u for u in urgency if u["level"] == "critical" and u["eligible"]]

    # Category distribution (by scheme id prefix is unreliable; use title-agnostic count of eligible/partial).
    avg_conf = round(sum(m["confidence"] for m in matches) / max(len(matches), 1), 2)

    return {
        "total_opportunities": len(matches),
        "eligible_count": len(eligible),
        "partial_count": len(partial),
        "open_count": open_count,
        "estimated_annual_benefit": estimated_benefit,
        "estimated_benefit_label": f"\u20b9{estimated_benefit:,}",
        "master_documents": master_documents,
        "documents_total": total_docs,
        "documents_owned": owned_docs,
        "readiness_percent": readiness,
        "urgency": urgency,
        "critical_count": len(critical),
        "avg_confidence": avg_conf,
        "top_pick": eligible[0] if eligible else (partial[0] if partial else None),
    }
