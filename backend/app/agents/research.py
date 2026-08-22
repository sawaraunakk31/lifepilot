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
        # Build and run the LangGraph workflow
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
        
        try:
            logger.info("Starting LangGraph research workflow...")
            result_state = graph.invoke(initial_state)
            
            # Transfer opportunities and logs to the main pipeline state
            state.raw_opportunities = result_state.get("opportunities", [])
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
            
        return state
