"""RoadmapAgent — generates personalized step-by-step action plans.

Uses LLM to create a warm, practical roadmap. Falls back to template-based
generation when offline.
"""
from __future__ import annotations

import json
import logging
from datetime import date

from app.agents.base import BaseAgent
from app.agents.state import AgentState
from app.services import analytics

logger = logging.getLogger("lifepilot.agents.roadmap")

_ROADMAP_PROMPT = """You are LifePilot, an AI Chief of Staff helping Indian citizens claim government benefits.

## Citizen: {name}
## Top Eligible Scheme: {title} ({amount})
## All Eligible Schemes: {eligible_count}
## Total Potential Value: {total_value}
## Nearest Deadline: {nearest_deadline}

Write a 2-3 sentence encouraging introduction for this citizen's personalized action plan.
Be warm, practical, specific. Mention the top scheme and total value. Don't be generic.
"""


def _days_left(deadline: str | None) -> int | None:
    if not deadline:
        return None
    try:
        return (date.fromisoformat(deadline) - date.today()).days
    except ValueError:
        return None


def _build_roadmap_steps(profile: dict, opp: dict, unmet: list[str]) -> list[str]:
    """Template-based roadmap steps per scheme."""
    steps = []
    steps.append(f"Visit the official portal: {opp.get('url', 'check portal')}")
    if unmet:
        steps.append("Resolve eligibility gaps: " + "; ".join(unmet[:3]))
    steps.append("Collect & scan all required documents (see your checklist).")
    steps.append("Create/verify your account on the official portal.")
    steps.append("Fill the application form and attach documents.")
    dl = _days_left(opp.get("deadline"))
    if dl is not None:
        if dl < 0:
            steps.append("Note: deadline has passed — check for the next cycle.")
        else:
            steps.append(f"Submit before {opp.get('deadline')} (~{dl} days left).")
    else:
        steps.append("Submit before the stated deadline on the portal.")
    steps.append("Save acknowledgement/reference number and track status.")
    return steps


class RoadmapAgent(BaseAgent):
    name = "RoadmapAgent"
    description = "Creates personalized step-by-step action plans using LLM"

    def execute(self, state: AgentState) -> AgentState:
        profile = state.profile
        matches = state.matches
        eligible = [m for m in matches if m.get("eligible")]

        # Build per-scheme roadmaps
        for m in matches:
            m["roadmap"] = _build_roadmap_steps(
                profile, m, m.get("unmet", [])
            )

        # Build insights
        owned_docs = state.owned_documents or []
        insights = analytics.build_insights(matches, owned_docs)
        state.insights.update(insights)

        # Generate intro with LLM
        top = eligible[0] if eligible else None
        if top and self.llm.name != "mock":
            nearest = None
            for m in eligible:
                dl = _days_left(m.get("deadline"))
                if dl is not None and dl >= 0:
                    nearest = f"{m.get('deadline')} ({dl} days)"
                    break

            prompt = _ROADMAP_PROMPT.format(
                name=profile.get("name", "Citizen"),
                title=top["title"],
                amount=top.get("amount", "financial support"),
                eligible_count=len(eligible),
                total_value=insights.get("estimated_benefit_label", "significant"),
                nearest_deadline=nearest or "check portals",
            )
            intro = self.llm.generate(
                prompt,
                system="Be concise, warm, practical. 2-3 sentences max."
            )
            if intro and len(intro) > 20:
                state.roadmap_intro = intro
            else:
                state.roadmap_intro = self._default_intro(profile, eligible, insights)
        elif top:
            state.roadmap_intro = self._default_intro(profile, eligible, insights)
        else:
            state.roadmap_intro = (
                "No fully eligible opportunities found yet. "
                "Complete more profile details or explore partial matches below."
            )

        state.add_log(
            agent=self.name,
            message=f"Generated personalized roadmaps for {len(matches)} schemes. "
                    f"Estimated potential value: {insights.get('estimated_benefit_label', '₹0')}/year.",
            confidence=0.88,
        )
        return state

    def _default_intro(self, profile: dict, eligible: list, insights: dict) -> str:
        name = profile.get("name", "").split()[0] if profile.get("name") else "there"
        value = insights.get("estimated_benefit_label", "significant financial support")
        return (
            f"Great news, {name}! You're eligible for {len(eligible)} scheme(s) "
            f"worth up to {value}/year. Follow the roadmap below to start applying."
        )
