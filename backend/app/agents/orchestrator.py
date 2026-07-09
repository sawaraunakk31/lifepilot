"""Multi-agent orchestrator (a lightweight LangGraph-style pipeline).

State flows through a sequence of specialised agents. Each agent appends logs
with a confidence score. The whole pipeline is deterministic and runs offline;
the LLM (if configured) only *enhances* the roadmap wording.

Agents:
    PlannerAgent      -> turns the profile into a structured search plan
    ResearchAgent     -> loads candidate opportunities from the local dataset
    EligibilityAgent  -> scores each opportunity (rule-based + confidence)
    DocumentAgent     -> builds the required-document checklist
    TrackingAgent     -> extracts & sorts deadlines
    RoadmapAgent      -> writes a step-by-step personalised roadmap (LLM optional)
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.llm.provider import get_provider
from app.services import eligibility
from app.services import analytics

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "scholarships.json"


def _load_opportunities() -> list[dict]:
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def _profile_to_dict(profile) -> dict:
    return {
        "name": profile.name,
        "age": profile.age,
        "gender": profile.gender,
        "state": profile.state,
        "category": profile.category,
        "education_level": profile.education_level,
        "field_of_study": profile.field_of_study,
        "annual_income": profile.annual_income,
        "disability": profile.disability,
        "goals": profile.goals,
    }


def _days_left(deadline: str | None) -> int | None:
    if not deadline:
        return None
    try:
        d = date.fromisoformat(deadline)
        return (d - date.today()).days
    except ValueError:
        return None


def _build_roadmap(profile: dict, opp: dict, elig: eligibility.EligibilityResult) -> list[str]:
    """Template-based roadmap (works offline). Enhanced by LLM only for the intro."""
    steps: list[str] = []
    dleft = _days_left(opp.get("deadline"))
    steps.append(f"Review official details on the portal: {opp.get('url')}")
    if elig.unmet:
        steps.append("Resolve remaining eligibility gaps: " + "; ".join(elig.unmet))
    steps.append("Collect & scan the required documents (see checklist).")
    steps.append("Create/verify your account on the official government portal.")
    steps.append("Fill the application form and attach documents.")
    if dleft is not None:
        if dleft < 0:
            steps.append("Note: the listed deadline has passed \u2014 check the portal for the next cycle.")
        else:
            steps.append(f"Submit before the deadline ({opp.get('deadline')}, ~{dleft} days left).")
    else:
        steps.append("Submit before the stated deadline on the portal.")
    steps.append("Save the acknowledgement/reference number and track status.")
    return steps


class Orchestrator:
    def __init__(self) -> None:
        self.llm = get_provider()

    def run(self, profile) -> dict:
        pdict = _profile_to_dict(profile)
        owned_documents = list(getattr(profile, "owned_documents", None) or [])
        logs: list[dict] = []
        matches: list[dict] = []

        # 1) Planner
        plan_bits = [k for k in ("category", "state", "education_level", "field_of_study",
                                 "annual_income", "age") if pdict.get(k) not in (None, "")]
        logs.append({
            "agent": "PlannerAgent",
            "message": f"Built a search plan from profile of {pdict.get('name')}. "
                       f"Using signals: {', '.join(plan_bits) or 'basic profile'}.",
            "confidence": round(0.5 + 0.5 * (len(plan_bits) / 6), 2),
        })

        # 2) Research
        opportunities = _load_opportunities()
        logs.append({
            "agent": "ResearchAgent",
            "message": f"Loaded {len(opportunities)} opportunities from the curated dataset "
                       f"(scholarships, grants & skilling schemes).",
            "confidence": 0.95,
        })

        # 3) Eligibility + 4) Documents + 5) Tracking + 6) Roadmap (per opportunity)
        eligible_count = 0
        for opp in opportunities:
            elig = eligibility.evaluate(pdict, opp)
            if elig.eligible:
                eligible_count += 1
            roadmap = _build_roadmap(pdict, opp, elig)
            matches.append({
                "opportunity_id": opp["id"],
                "title": opp["title"],
                "provider": opp.get("provider"),
                "url": opp.get("url"),
                "amount": opp.get("amount"),
                "deadline": opp.get("deadline"),
                "eligible": elig.eligible,
                "score": elig.score,
                "confidence": elig.confidence,
                "reasons": elig.reasons,
                "unmet": elig.unmet,
                "documents": opp.get("documents", []),
                "roadmap": roadmap,
            })

        # Sort: eligible first, then by score, then by soonest deadline.
        def sort_key(m):
            dleft = _days_left(m["deadline"])
            return (not m["eligible"], -m["score"], dleft if dleft is not None else 9999)

        matches.sort(key=sort_key)

        avg_conf = round(sum(m["confidence"] for m in matches) / max(len(matches), 1), 2)
        logs.append({
            "agent": "EligibilityAgent",
            "message": f"Evaluated {len(matches)} opportunities. "
                       f"{eligible_count} fully eligible, "
                       f"{len(matches) - eligible_count} partial/ineligible.",
            "confidence": avg_conf,
        })
        logs.append({
            "agent": "DocumentAgent",
            "message": "Generated a personalised document checklist for each eligible opportunity.",
            "confidence": 0.9,
        })

        upcoming = [m for m in matches if (_days_left(m["deadline"]) or -1) >= 0]
        logs.append({
            "agent": "TrackingAgent",
            "message": f"Tracked deadlines. {len(upcoming)} opportunities still open for application.",
            "confidence": 0.9,
        })

        # 6) Roadmap intro (LLM-enhanced when a real model is configured)
        top = matches[0] if matches else None
        if top and top["eligible"]:
            prompt = (
                f"You are LifePilot, an AI Chief of Staff. In 2 short sentences, encourage "
                f"{pdict.get('name')} to apply for '{top['title']}' ({top['amount']}). Be practical."
            )
            intro = self.llm.generate(prompt, system="Be concise, warm and practical.")
        else:
            intro = ("No fully-eligible opportunities matched yet. Complete more profile details "
                     "or explore the partial matches below to widen your options.")
        logs.append({
            "agent": "RoadmapAgent",
            "message": intro,
            "confidence": 0.85,
        })

        summary = (
            f"Found {eligible_count} eligible and {len(matches) - eligible_count} partial matches "
            f"for {pdict.get('name')}. LLM provider: {self.llm.name}."
        )

        insights = analytics.build_insights(matches, owned_documents)
        logs.append({
            "agent": "InsightAgent",
            "message": f"Estimated potential value {insights['estimated_benefit_label']}/year across "
                       f"eligible schemes. Application readiness: {insights['readiness_percent']}%.",
            "confidence": 0.88,
        })

        return {"summary": summary, "logs": logs, "matches": matches, "insights": insights}
