"""DocumentAgent — builds a personalized, de-duplicated document checklist.

Analyzes all eligible schemes and produces a master list of required
documents, ranked by how many schemes need each document.
"""
from __future__ import annotations

import logging

from app.agents.base import BaseAgent
from app.agents.state import AgentState

logger = logging.getLogger("lifepilot.agents.document")


class DocumentAgent(BaseAgent):
    name = "DocumentAgent"
    description = "Generates a personalized document checklist across all eligible schemes"

    def execute(self, state: AgentState) -> AgentState:
        matches = state.matches
        owned = {d.strip().lower() for d in state.owned_documents if d.strip()}
        eligible = [m for m in matches if m.get("eligible")]

        # Build de-duplicated master checklist
        doc_map: dict[str, dict] = {}
        for m in eligible:
            for doc in m.get("documents", []):
                key = doc.strip().lower()
                if key not in doc_map:
                    doc_map[key] = {
                        "document": doc,
                        "schemes": [],
                        "owned": key in owned,
                    }
                doc_map[key]["schemes"].append(m["title"])

        master_documents = sorted(
            [
                {
                    "document": v["document"],
                    "used_by": len(v["schemes"]),
                    "schemes": v["schemes"],
                    "owned": v["owned"],
                }
                for v in doc_map.values()
            ],
            key=lambda d: (-d["used_by"], d["document"].lower()),
        )

        total = len(master_documents)
        owned_count = sum(1 for d in master_documents if d["owned"])
        readiness = round(100 * owned_count / total) if total else 0

        state.master_documents = master_documents
        state.insights["documents_total"] = total
        state.insights["documents_owned"] = owned_count
        state.insights["readiness_percent"] = readiness
        state.insights["master_documents"] = master_documents

        state.add_log(
            agent=self.name,
            message=f"Built master document checklist: {total} unique documents needed "
                    f"across {len(eligible)} eligible schemes. "
                    f"You have {owned_count}/{total} ({readiness}% ready).",
            confidence=0.92,
        )
        return state
