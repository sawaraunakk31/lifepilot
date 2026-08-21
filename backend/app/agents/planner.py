"""PlannerAgent — analyzes user profile and creates a search strategy.

Uses the LLM to understand the user's situation and generate a targeted
search plan: which categories to search, which portals to hit, and
what keywords to use.
"""
from __future__ import annotations

import json
import logging

from app.agents.base import BaseAgent
from app.agents.state import AgentState

logger = logging.getLogger("lifepilot.agents.planner")

_PLAN_PROMPT = """You are LifePilot's Planner Agent. Analyze this citizen's profile and create a targeted search plan for finding scholarships, grants, and government schemes they may be eligible for.

## Citizen Profile:
{profile_json}

## Your Task:
Create a search plan with:
1. **categories**: List of scheme categories to search (e.g., "scholarship", "grant", "skill_training", "startup_fund")
2. **keywords**: Search keywords based on their profile (e.g., "SC scholarship Karnataka", "engineering merit scholarship")
3. **target_portals**: Government portals to check (e.g., "scholarships.gov.in", "ssp.postmatric.karnataka.gov.in")
4. **priority_factors**: What makes this profile special (e.g., "low income + SC category = high priority for post-matric scholarships")
5. **profile_strength**: Rate 1-10 how complete the profile is for matching

Respond ONLY with valid JSON:
```json
{{
  "categories": ["scholarship", "grant"],
  "keywords": ["keyword1", "keyword2"],
  "target_portals": ["portal1.gov.in"],
  "priority_factors": ["factor1", "factor2"],
  "profile_strength": 7,
  "summary": "Brief one-line summary of the plan"
}}
```"""


class PlannerAgent(BaseAgent):
    name = "PlannerAgent"
    description = "Analyzes user profile and creates a targeted search strategy"

    def execute(self, state: AgentState) -> AgentState:
        profile = state.profile
        profile_json = json.dumps(profile, indent=2, default=str)

        # Use LLM for intelligent planning
        if self.llm.name != "mock":
            prompt = _PLAN_PROMPT.format(profile_json=profile_json)
            plan = self.llm.generate_json(
                prompt,
                system="You are a government scheme expert for India. Respond only with valid JSON."
            )
            if plan and plan.get("categories"):
                state.search_plan = plan
                strength = plan.get("profile_strength", 5)
                confidence = min(0.5 + (strength / 20), 0.95)
                state.add_log(
                    agent=self.name,
                    message=plan.get("summary", f"Created search plan targeting {len(plan.get('categories', []))} categories."),
                    confidence=confidence,
                )
                return state

        # Fallback: rule-based planning (works offline)
        plan = self._rule_based_plan(profile)
        state.search_plan = plan
        plan_signals = [k for k in ("category", "state", "education_level",
                                     "field_of_study", "annual_income", "age")
                        if profile.get(k) not in (None, "")]
        confidence = round(0.5 + 0.5 * (len(plan_signals) / 6), 2)
        state.add_log(
            agent=self.name,
            message=f"Built search plan for {profile.get('name', 'user')} using "
                    f"{len(plan_signals)} profile signals: {', '.join(plan_signals) or 'basic profile'}.",
            confidence=confidence,
        )
        return state

    def _rule_based_plan(self, profile: dict) -> dict:
        """Deterministic plan when LLM is unavailable."""
        categories = ["scholarship"]
        keywords = []
        portals = ["scholarships.gov.in"]

        if profile.get("category") in ("SC", "ST", "OBC", "EWS"):
            keywords.append(f"{profile['category']} scholarship")
        if profile.get("state"):
            keywords.append(f"{profile['state']} scholarship")
            if profile["state"].lower() == "karnataka":
                portals.append("ssp.postmatric.karnataka.gov.in")
        if profile.get("education_level"):
            keywords.append(f"{profile['education_level']} scholarship")
        if profile.get("field_of_study"):
            keywords.append(f"{profile['field_of_study']} scholarship")
        if profile.get("goals") and any(w in (profile["goals"] or "").lower()
                                         for w in ("startup", "business", "entrepreneur")):
            categories.append("grant")
            keywords.append("startup grant India")
            portals.append("seedfund.startupindia.gov.in")

        categories.append("skilling")
        keywords.append("PMKVY skill training")

        return {
            "categories": categories,
            "keywords": keywords,
            "target_portals": portals,
            "priority_factors": [f"{profile.get('category', 'General')} category",
                                 f"Income ₹{profile.get('annual_income', 'unknown')}"],
            "profile_strength": sum(1 for k in ("name", "age", "gender", "state",
                                                  "category", "education_level",
                                                  "field_of_study", "annual_income")
                                    if profile.get(k) not in (None, "")),
            "summary": f"Rule-based plan for {profile.get('name', 'user')}",
        }
