"""ResearchAgent — discovers opportunities from multiple sources.

Sources (in priority order):
1. Curated local dataset (always available, instant)
2. Web scraping of known government portals (if enabled)
3. Vector database semantic search (if ChromaDB has data)
4. Web search via Serper API (if configured)

Results are merged and de-duplicated before passing to EligibilityAgent.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.agents.base import BaseAgent
from app.agents.state import AgentState
from app.config import settings

logger = logging.getLogger("lifepilot.agents.research")

from app.agents.graph import build_graph, AgentGraphState

class ResearchAgent(BaseAgent):
    name = "ResearchAgent"
    description = "Discovers opportunities dynamically via LangGraph web search and scraping"

    def execute(self, state: AgentState) -> AgentState:
        # 1. Sources: Curated local dataset from scholarships.json
        curated_schemes = []
        try:
            from app.knowledge.vectorstore import DATA_FILE
            if DATA_FILE.exists():
                with open(DATA_FILE, encoding="utf-8") as f:
                    curated_schemes = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load curated scholarships: {e}")

        # If running in What-If Simulation mode, skip slow live web search and return curated schemes immediately
        if state.profile.get("name") == "Simulation":
            state.raw_opportunities = curated_schemes
            state.add_log(
                agent=self.name,
                message=f"Discovered {len(curated_schemes)} curated opportunities (fast simulation mode).",
                confidence=1.0
            )
            return state

        # 2. Build and run the LangGraph workflow for web discovery
        graph = build_graph()
        
        # Initial state for the sub-graph
        initial_state: AgentGraphState = {
            "profile": state.profile,
            "search_queries": [],
            "raw_results": [],
            "scraped_content": [],
            "opportunities": [],
            "errors": [],
            "logs": []
        }
        
        scraped_opps = []
        try:
            logger.info("Starting LangGraph research workflow...")
            result_state = graph.invoke(initial_state)
            scraped_opps = result_state.get("opportunities", [])
            
            for log in result_state.get("logs", []):
                state.add_log(
                    agent=log.get("agent", "LangGraph"),
                    message=log.get("message", ""),
                    confidence=0.9
                )
            
            if result_state.get("errors"):
                state.errors.extend(result_state["errors"])
                
        except Exception as e:
            logger.error(f"LangGraph execution failed: {e}")
            state.errors.append(f"LangGraph failure: {e}")
            
        # 3. Merge & de-duplicate opportunities
        seen = set()
        merged = []
        garbage_titles = {
            "find schemes based", 
            "for government schemes", 
            "find schemes based on your eligibility",
            "search schemes"
        }
        for item in curated_schemes + scraped_opps:
            title = item.get("title", "").strip()
            title_lower = title.lower()
            if not title or title_lower in seen:
                continue
            if title_lower in garbage_titles or any(g in title_lower for g in ("based on your eligibility", "discover schemes")):
                continue
            seen.add(title_lower)
            merged.append(item)
            
        state.raw_opportunities = merged
        state.add_log(
            agent=self.name,
            message=f"Discovered {len(merged)} total opportunities ({len(curated_schemes)} curated, {len(scraped_opps)} discovered).",
            confidence=0.95
        )
        return state
