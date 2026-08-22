"""TrackingAgent — analyzes deadlines, urgency, and timeline insights."""
from __future__ import annotations

import logging
from datetime import date

from app.agents.base import BaseAgent
from app.agents.state import AgentState

logger = logging.getLogger("lifepilot.agents.tracking")


def _days_left(deadline: str | None) -> int | None:
    if not deadline:
        return None
    try:
        return (date.fromisoformat(deadline) - date.today()).days
    except ValueError:
        return None


def _urgency(days: int | None) -> str:
    if days is None:
        return "unknown"
    if days < 0:
        return "closed"
    if days <= 14:
        return "critical"
    if days <= 45:
        return "soon"
    return "comfortable"


class TrackingAgent(BaseAgent):
    name = "TrackingAgent"
    description = "Tracks deadlines and urgency across all opportunities"

    def execute(self, state: AgentState) -> AgentState:
        matches = state.matches
        urgency_list = []

        for m in matches:
            days = _days_left(m.get("deadline"))
            urgency_list.append({
                "title": m["title"],
                "deadline": m.get("deadline"),
                "days_left": days,
                "level": _urgency(days),
                "eligible": m.get("eligible", False),
            })

        urgency_list.sort(key=lambda u: (
            u["days_left"] is None,
            u["days_left"] if u["days_left"] is not None else 9999
        ))

        open_count = sum(1 for u in urgency_list if (u["days_left"] or -1) >= 0)
        critical = [u for u in urgency_list if u["level"] == "critical" and u["eligible"]]

        state.deadline_summary = {
            "urgency": urgency_list,
            "open_count": open_count,
            "critical_count": len(critical),
        }
        state.insights["urgency"] = urgency_list
        state.insights["open_count"] = open_count
        state.insights["critical_count"] = len(critical)

        critical_msg = ""
        if critical:
            names = ", ".join(c["title"] for c in critical[:2])
            critical_msg = f" ⚠️ URGENT: {names} closing within 14 days!"

        state.add_log(
            agent=self.name,
            message=f"Tracked {len(urgency_list)} deadlines. "
                    f"{open_count} still open for application.{critical_msg}",
            confidence=0.93,
        )
        return state
