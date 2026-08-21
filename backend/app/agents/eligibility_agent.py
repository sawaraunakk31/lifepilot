"""EligibilityAgent — evaluates each opportunity against the user's profile.

Combines the existing rule-based engine with LLM-powered reasoning for
nuanced edge cases. Produces explainable verdicts with confidence scores.
"""
from __future__ import annotations

import json
import logging

from app.agents.base import BaseAgent
from app.agents.state import AgentState
from app.services import eligibility as elig_engine

logger = logging.getLogger("lifepilot.agents.eligibility")

_ELIGIBILITY_PROMPT = """You are LifePilot's Eligibility Agent. Evaluate whether this citizen qualifies for the scheme.

## Citizen Profile:
{profile_json}

## Scheme Details:
- Title: {title}
- Description: {description}
- Criteria: {criteria_json}

## Rule-Based Result:
- Eligible: {rule_eligible}
- Score: {rule_score}
- Reasons met: {reasons}
- Unmet criteria: {unmet}

## Your Task:
Review the rule-based result and provide your assessment. Consider edge cases
the rules might miss (e.g., "engineering" matches "technical education").
Respond with JSON:
```json
{{
  "eligible": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation of your assessment",
  "additional_reasons": ["any extra reasons the rules missed"],
  "additional_gaps": ["any extra gaps the rules missed"]
}}
```"""


class EligibilityAgent(BaseAgent):
    name = "EligibilityAgent"
    description = "Evaluates eligibility using rules + LLM reasoning"

    def execute(self, state: AgentState) -> AgentState:
        profile = state.profile
        opportunities = state.raw_opportunities
        matches: list[dict] = []
        eligible_count = 0

        for opp in opportunities:
            # Step 1: Rule-based evaluation (always runs, fast, deterministic)
            elig = elig_engine.evaluate(profile, opp)

            # Step 2: LLM enhancement (if available)
            llm_conf = elig.confidence
            if self.llm.name != "mock" and opp.get("criteria"):
                try:
                    llm_result = self._llm_evaluate(profile, opp, elig)
                    if llm_result:
                        # Merge LLM insights with rule-based results
                        if llm_result.get("additional_reasons"):
                            elig.reasons.extend(llm_result["additional_reasons"])
                        if llm_result.get("additional_gaps"):
                            elig.unmet.extend(llm_result["additional_gaps"])
                        llm_conf = llm_result.get("confidence", elig.confidence)
                        # LLM can override eligibility only if it has higher confidence
                        if llm_conf > elig.confidence:
                            elig.eligible = llm_result.get("eligible", elig.eligible)
                            elig.confidence = llm_conf
                except Exception as e:
                    logger.warning(f"LLM eligibility check failed for {opp.get('id')}: {e}")

            if elig.eligible:
                eligible_count += 1

            matches.append({
                "opportunity_id": opp.get("id", opp.get("title", "unknown")),
                "title": opp.get("title", "Unknown Scheme"),
                "provider": opp.get("provider"),
                "url": opp.get("url"),
                "amount": opp.get("amount"),
                "deadline": opp.get("deadline"),
                "category": opp.get("category"),
                "description": opp.get("description"),
                "eligible": elig.eligible,
                "score": elig.score,
                "confidence": elig.confidence,
                "reasons": elig.reasons,
                "unmet": elig.unmet,
                "documents": opp.get("documents", []),
                "roadmap": [],
                "source": opp.get("source", "curated"),
            })

        # Sort: eligible first → highest score → soonest deadline
        from datetime import date
        def _sort_key(m):
            dl = m.get("deadline")
            try:
                days = (date.fromisoformat(dl) - date.today()).days if dl else 9999
            except ValueError:
                days = 9999
            return (not m["eligible"], -m["score"], days)

        matches.sort(key=_sort_key)
        state.matches = matches

        avg_conf = round(sum(m["confidence"] for m in matches) / max(len(matches), 1), 2)
        state.add_log(
            agent=self.name,
            message=f"Evaluated {len(matches)} opportunities: {eligible_count} eligible, "
                    f"{len(matches) - eligible_count} partial/ineligible. "
                    f"Average confidence: {avg_conf}.",
            confidence=avg_conf,
        )
        return state

    def _llm_evaluate(self, profile: dict, opp: dict, elig) -> dict | None:
        prompt = _ELIGIBILITY_PROMPT.format(
            profile_json=json.dumps(profile, indent=2, default=str),
            title=opp.get("title", ""),
            description=opp.get("description", ""),
            criteria_json=json.dumps(opp.get("criteria", {}), indent=2),
            rule_eligible=elig.eligible,
            rule_score=elig.score,
            reasons="; ".join(elig.reasons[:3]),
            unmet="; ".join(elig.unmet[:3]),
        )
        return self.llm.generate_json(
            prompt,
            system="You are a government scheme eligibility expert. Respond only with valid JSON."
        )
