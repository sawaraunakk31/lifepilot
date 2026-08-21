"""Multi-agent orchestrator — the real pipeline.

Chains agents in sequence: Planner → Research → Eligibility → Document →
Tracking → Roadmap. Each agent reads from and writes to the shared AgentState.

The pipeline is resilient: if one agent fails, the pipeline continues with
whatever data is available. Every agent has built-in retry logic.
"""
from __future__ import annotations

import logging
import time

from app.agents.state import AgentState
from app.agents.planner import PlannerAgent
from app.agents.research import ResearchAgent
from app.agents.eligibility_agent import EligibilityAgent
from app.agents.document_agent import DocumentAgent
from app.agents.tracking_agent import TrackingAgent
from app.agents.roadmap_agent import RoadmapAgent
from app.llm.provider import get_provider

logger = logging.getLogger("lifepilot.orchestrator")


def _profile_to_dict(profile) -> dict:
    """Convert ORM model or SimpleNamespace to dict."""
    if isinstance(profile, dict):
        return profile
    return {
        "name": getattr(profile, "name", ""),
        "age": getattr(profile, "age", None),
        "gender": getattr(profile, "gender", None),
        "state": getattr(profile, "state", None),
        "category": getattr(profile, "category", None),
        "education_level": getattr(profile, "education_level", None),
        "field_of_study": getattr(profile, "field_of_study", None),
        "annual_income": getattr(profile, "annual_income", None),
        "disability": getattr(profile, "disability", False),
        "goals": getattr(profile, "goals", None),
    }


class Orchestrator:
    """Runs the full agent pipeline."""

    def __init__(self) -> None:
        self.llm = get_provider()

    def run(self, profile, owned_documents: list[str] | None = None) -> dict:
        start = time.perf_counter()
        pdict = _profile_to_dict(profile)
        owned = list(owned_documents or getattr(profile, "owned_documents", None) or [])

        # Initialize state
        state = AgentState(
            profile=pdict,
            owned_documents=owned,
            matches=[],
            insights={},
        )

        # Build the agent pipeline
        agents = [
            PlannerAgent(self.llm),
            ResearchAgent(self.llm),
            EligibilityAgent(self.llm),
            DocumentAgent(self.llm),
            TrackingAgent(self.llm),
            RoadmapAgent(self.llm),
        ]

        # Execute pipeline
        for agent in agents:
            try:
                state = agent.run(state)
            except Exception as e:
                logger.error(f"Critical failure in {agent.name}: {e}")
                state.errors.append(f"{agent.name} critical failure: {e}")
                # Continue pipeline even on critical failure

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        eligible_count = sum(1 for m in state.matches if m.get("eligible"))

        summary = (
            f"Found {eligible_count} eligible and {len(state.matches) - eligible_count} "
            f"partial matches for {pdict.get('name', 'user')}. "
            f"Pipeline ran {len(agents)} agents in {elapsed_ms}ms. "
            f"LLM: {self.llm.name}."
        )

        # Ensure insights have required fields
        state.insights.setdefault("total_opportunities", len(state.matches))
        state.insights.setdefault("eligible_count", eligible_count)
        state.insights.setdefault("partial_count", len(state.matches) - eligible_count)
        state.insights.setdefault("estimated_benefit_label", "₹0")
        state.insights.setdefault("readiness_percent", 0)
        state.insights.setdefault("avg_confidence",
            round(sum(m.get("confidence", 0) for m in state.matches) / max(len(state.matches), 1), 2)
        )

        # Add top pick
        eligible = [m for m in state.matches if m.get("eligible")]
        partial = [m for m in state.matches if not m.get("eligible")]
        state.insights.setdefault("top_pick",
            eligible[0] if eligible else (partial[0] if partial else None)
        )

        return {
            "summary": summary,
            "logs": state.logs,
            "matches": state.matches,
            "insights": state.insights,
            "roadmap_intro": state.roadmap_intro,
            "errors": state.errors,
            "elapsed_ms": elapsed_ms,
        }
