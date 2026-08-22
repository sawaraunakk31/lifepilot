"""Agent state — typed data container flowing through the agent pipeline.

Every agent reads from and writes to this shared state object. This is
the single source of truth for the entire pipeline run.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentLog:
    """A single agent's execution log entry."""
    agent: str
    message: str
    confidence: float = 0.0
    duration_ms: int = 0
    status: str = "success"  # success | error | skipped


@dataclass
class OpportunityMatch:
    """An opportunity evaluated against the user's profile."""
    opportunity_id: str
    title: str
    provider: str | None = None
    url: str | None = None
    amount: str | None = None
    deadline: str | None = None
    category: str | None = None
    description: str | None = None
    eligible: bool = False
    score: float = 0.0
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    unmet: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    roadmap: list[str] = field(default_factory=list)
    source: str = "curated"  # curated | scraped | vector


@dataclass
class AgentState:
    """Shared state flowing through all agents in the pipeline."""

    # Input
    profile: dict = field(default_factory=dict)
    owned_documents: list[str] = field(default_factory=list)

    # PlannerAgent output
    search_plan: dict = field(default_factory=dict)

    # ResearchAgent output
    raw_opportunities: list[dict] = field(default_factory=list)

    # EligibilityAgent output
    matches: list[dict] = field(default_factory=list)

    # DocumentAgent output
    master_documents: list[dict] = field(default_factory=list)

    # TrackingAgent output
    deadline_summary: dict = field(default_factory=dict)

    # RoadmapAgent output
    roadmap_intro: str = ""

    # Cross-cutting
    logs: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    insights: dict = field(default_factory=dict)

    def add_log(self, agent: str, message: str, confidence: float = 0.0,
                duration_ms: int = 0, status: str = "success") -> None:
        self.logs.append({
            "agent": agent,
            "message": message,
            "confidence": round(confidence, 2),
            "duration_ms": duration_ms,
            "status": status,
        })

    def to_dict(self) -> dict:
        return {
            "profile": self.profile,
            "search_plan": self.search_plan,
            "matches": self.matches,
            "logs": self.logs,
            "insights": self.insights,
            "roadmap_intro": self.roadmap_intro,
            "errors": self.errors,
        }
