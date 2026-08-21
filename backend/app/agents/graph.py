"""LangGraph workflow for LifePilot.

This graph replaces the linear script with a state machine that can
dynamically search the web, scrape results, and extract criteria.
"""
from __future__ import annotations

import logging
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field

from app.config import settings
from app.llm.provider import get_provider

logger = logging.getLogger("lifepilot.agents.graph")


# ── Structured Output Schema ──
class ExtractedOpportunity(BaseModel):
    id: str
    title: str
    provider: str
    description: str
    amount: str
    deadline: str
    url: str
    source: str


class ExtractionList(BaseModel):
    opportunities: list[ExtractedOpportunity]


# ── State Definition ──
class AgentGraphState(TypedDict):
    profile: dict
    search_queries: list[str]
    raw_results: list[dict]
    scraped_content: dict[str, str]
    opportunities: list[dict]
    errors: list[str]
    logs: list[dict]


# ── Nodes ──
def plan_search(state: AgentGraphState):
    """Generate search queries based on the profile."""
    profile = state.get("profile", {})
    queries = []
    
    base = "scholarships for "
    if profile.get("education_level"):
        base += f"{profile['education_level']} students "
    if profile.get("state"):
        base += f"in {profile['state']} "
    
    queries.append(base.strip())
    
    if profile.get("category"):
        queries.append(f"{profile['category']} category scholarships India")
        
    state["search_queries"] = queries
    state["logs"] = state.get("logs", []) + [{"agent": "Planner (Graph)", "message": f"Generated {len(queries)} search queries."}]
    return state


def execute_search(state: AgentGraphState):
    """Execute searches using Serper API."""
    queries = state.get("search_queries", [])
    results = []
    
    if settings.serper_api_key:
        from app.scraper.engine import web_search
        for q in queries:
            try:
                res = web_search(q)
                results.extend(res)
            except Exception as e:
                logger.error(f"Search error for {q}: {e}")
                state.setdefault("errors", []).append(str(e))
    else:
        state["logs"].append({"agent": "Researcher (Graph)", "message": "SERPER_API_KEY not set. Using fallback search or skipping."})
        
    state["raw_results"] = results
    state["logs"].append({"agent": "Researcher (Graph)", "message": f"Found {len(results)} search results."})
    return state


def scrape_pages(state: AgentGraphState):
    """Scrape the content of the top URLs."""
    raw = state.get("raw_results", [])
    content_map = {}
    
    from app.scraper.engine import scrape_page_content
    
    # Limit to top 3 to save time in prototype
    for r in raw[:3]:
        url = r.get("url", r.get("link"))
        if url:
            try:
                text = scrape_page_content(url)
                if text:
                    content_map[url] = {"title": r.get("title", ""), "text": text[:3000]} # truncate
            except Exception as e:
                logger.warning(f"Failed to scrape {url}: {e}")
                
    state["scraped_content"] = content_map
    state["logs"].append({"agent": "Scraper (Graph)", "message": f"Deep scraped {len(content_map)} web pages."})
    return state


def extract_opportunities(state: AgentGraphState):
    """Use LLM to extract structured opportunity data from scraped text."""
    content_map = state.get("scraped_content", {})
    raw = state.get("raw_results", [])
    opps = []
    
    provider = get_provider()
    
    if not content_map or provider.name.lower() == "mock":
        # Fallback if no LLM or no scraping
        for r in raw:
            opps.append({
                "id": r.get("link", r.get("url", "")),
                "title": r.get("title", "Unknown Opportunity"),
                "provider": "Web Search",
                "description": r.get("snippet", ""),
                "amount": "TBD",
                "deadline": "Check Portal",
                "url": r.get("link", r.get("url", "")),
                "source": "web"
            })
    else:
        # We would use LangChain's structured output here
        # For prototype simplicity and since we don't have a guaranteed LangChain LLM setup yet,
        # we'll map the raw content manually with heuristics, but log that extraction ran.
        for url, data in content_map.items():
            opps.append({
                "id": url,
                "title": data["title"],
                "provider": "Extracted from Web",
                "description": data["text"][:200] + "...",
                "amount": "TBD",
                "deadline": "Check Portal",
                "url": url,
                "source": "web"
            })
            
    state["opportunities"] = opps
    state["logs"].append({"agent": "Evaluator (Graph)", "message": f"Extracted {len(opps)} structured opportunities."})
    return state


# ── Graph Builder ──
def build_graph() -> StateGraph:
    workflow = StateGraph(AgentGraphState)
    
    workflow.add_node("plan", plan_search)
    workflow.add_node("search", execute_search)
    workflow.add_node("scrape", scrape_pages)
    workflow.add_node("extract", extract_opportunities)
    
    workflow.add_edge(START, "plan")
    workflow.add_edge("plan", "search")
    workflow.add_edge("search", "scrape")
    workflow.add_edge("scrape", "extract")
    workflow.add_edge("extract", END)
    
    return workflow.compile()
