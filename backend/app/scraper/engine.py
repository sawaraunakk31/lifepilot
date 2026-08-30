"""Web scraping engine — fetches real scholarship data from government portals.

Uses httpx + BeautifulSoup for lightweight, reliable scraping.
Also supports Serper API for web search when configured.

Scraped data is cached in SQLite to avoid hitting portals too frequently.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from app.config import settings

logger = logging.getLogger("lifepilot.scraper")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}

# ── Known portal scrapers ────────────────────────────────────

_PORTAL_SCRAPERS = {}


def _register(domain: str):
    def decorator(fn):
        _PORTAL_SCRAPERS[domain] = fn
        return fn
    return decorator


@_register("scholarships.gov.in")
def _scrape_nsp(url: str) -> list[dict]:
    """Scrape National Scholarship Portal for scheme listings."""
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True, headers=_HEADERS) as client:
            resp = client.get("https://scholarships.gov.in/public/schemeList")
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.text, "lxml")
            schemes = []
            # Try to find scheme cards or table rows
            for card in soup.select(".scholarship-card, .scheme-item, tr[data-id]"):
                title_el = card.select_one("h3, h4, .title, td:first-child")
                if title_el:
                    title = title_el.get_text(strip=True)
                    link = card.select_one("a[href]")
                    href = link["href"] if link else url
                    schemes.append({
                        "id": f"nsp-scraped-{hashlib.md5(title.encode()).hexdigest()[:8]}",
                        "title": title,
                        "provider": "National Scholarship Portal",
                        "url": href if href.startswith("http") else f"https://scholarships.gov.in{href}",
                        "source": "scraped",
                        "category": "scholarship",
                    })
            return schemes[:20]
    except Exception as e:
        logger.warning(f"NSP scrape failed: {e}")
        return []


@_register("ssp.postmatric.karnataka.gov.in")
def _scrape_karnataka_ssp(url: str) -> list[dict]:
    """Scrape Karnataka SSP portal."""
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True, headers=_HEADERS) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.text, "lxml")
            schemes = []
            for item in soup.select(".scheme, .card, li a"):
                text = item.get_text(strip=True)
                if len(text) > 10:
                    schemes.append({
                        "id": f"ka-scraped-{hashlib.md5(text.encode()).hexdigest()[:8]}",
                        "title": text[:120],
                        "provider": "Government of Karnataka",
                        "url": url,
                        "source": "scraped",
                        "category": "scholarship",
                        "criteria": {"state": ["Karnataka"]},
                    })
            return schemes[:10]
    except Exception as e:
        logger.warning(f"Karnataka SSP scrape failed: {e}")
        return []


@_register("myscheme.gov.in")
def _scrape_myscheme(url: str) -> list[dict]:
    """Scrape MyScheme portal (uses dynamic generic scraping + API fallback concepts)."""
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True, headers=_HEADERS) as client:
            # MyScheme is highly dynamic (React/Next), so we fallback to generic scraping if API is hidden
            resp = client.get(url)
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.text, "lxml")
            schemes = []
            for item in soup.select("h2, h3, a.scheme-card, .text-xl"):
                text = item.get_text(strip=True)
                if len(text) < 15 or len(text) > 150:
                    continue
                # Skip generic page headers/buttons
                text_lower = text.lower()
                if any(x in text_lower for x in ("find schemes", "search schemes", "eligibility", "government schemes", "sign in", "about us")):
                    continue
                if "scheme" in text_lower or "yojana" in text_lower:
                    schemes.append({
                        "id": f"myscheme-{hashlib.md5(text.encode()).hexdigest()[:8]}",
                        "title": text,
                        "provider": "Government of India",
                        "url": url,
                        "source": "scraped",
                        "category": "scheme",
                    })
            return schemes[:15]
    except Exception as e:
        logger.warning(f"MyScheme scrape failed: {e}")
        return []


def _scrape_rss_jobs(url: str) -> list[dict]:
    """Scrape Job Portals via standard RSS/XML feeds (Upwork, Indeed, LinkedIn standard feeds)."""
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True, headers=_HEADERS) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return []
            # Parse as XML using BeautifulSoup
            soup = BeautifulSoup(resp.content, "xml")
            jobs = []
            # RSS items
            for item in soup.find_all("item"):
                title = item.find("title")
                link = item.find("link")
                desc = item.find("description")
                if title and link:
                    title_text = title.get_text(strip=True)
                    raw_desc = desc.get_text(strip=True) if desc else ""
                    if "<" in raw_desc and ">" in raw_desc:
                        try:
                            raw_desc = BeautifulSoup(raw_desc, "html.parser").get_text(separator=" ", strip=True)
                        except Exception:
                            pass
                    jobs.append({
                        "id": f"job-rss-{hashlib.md5(title_text.encode()).hexdigest()[:8]}",
                        "title": title_text,
                        "provider": "Job Portal",
                        "url": link.get_text(strip=True),
                        "description": raw_desc[:300].strip(),
                        "source": "scraped_rss",
                        "category": "job",
                    })
            return jobs[:20]
    except Exception as e:
        logger.warning(f"Job RSS scrape failed for {url}: {e}")
        return []


def _scrape_generic(url: str) -> list[dict]:
    """Generic scraper for any government portal — extracts scheme-like content."""
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True, headers=_HEADERS) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.text, "lxml")
            schemes = []
            # Look for any scheme/scholarship mentions
            keywords = re.compile(
                r"scholarship|scheme|yojana|grant|fellowship|stipend|fund",
                re.IGNORECASE,
            )
            for el in soup.select("h1, h2, h3, h4, .title, .card-title, td"):
                text = el.get_text(strip=True)
                if keywords.search(text) and 10 < len(text) < 200:
                    parent_link = el.find_parent("a") or el.find("a")
                    href = parent_link["href"] if parent_link and parent_link.get("href") else url
                    if not href.startswith("http"):
                        href = f"{url.rstrip('/')}/{href.lstrip('/')}"
                    schemes.append({
                        "id": f"scraped-{hashlib.md5(text.encode()).hexdigest()[:8]}",
                        "title": text,
                        "url": href,
                        "source": "scraped",
                        "category": "scholarship",
                    })
            # De-dup by title
            seen = set()
            unique = []
            for s in schemes:
                if s["title"] not in seen:
                    seen.add(s["title"])
                    unique.append(s)
            return unique[:15]
    except Exception as e:
        logger.warning(f"Generic scrape of {url} failed: {e}")
        return []


# ── Public API ────────────────────────────────────────────────

def scrape_portals(portals: list[str], keywords: list[str] | None = None) -> list[dict]:
    """Scrape a list of portal domains/URLs and return discovered schemes."""
    all_results = []
    for portal in portals:
        # Normalize to URL
        url = portal if portal.startswith("http") else f"https://{portal}"
        domain = portal.replace("https://", "").replace("http://", "").split("/")[0]

        # Use specific scraper if available, else generic
        # Check if it's an RSS feed (ends with .xml or /rss)
        if url.endswith(".xml") or "/rss" in url.lower():
            scraper = _scrape_rss_jobs
        else:
            scraper = _PORTAL_SCRAPERS.get(domain, _scrape_generic)
            
        try:
            results = scraper(url)
            all_results.extend(results)
            logger.info(f"Scraped {len(results)} items from {domain}")
        except Exception as e:
            logger.warning(f"Failed to scrape {domain}: {e}")

    # BACKUP SYSTEM: If no results found, fallback to Serper API search
    if not all_results and keywords:
        logger.info("Scraping returned 0 results. Activating Serper API Fallback.")
        fallback_query = " ".join(keywords)
        fallback_results = web_search(fallback_query)
        all_results.extend(fallback_results)

    return all_results


def web_search(query: str) -> list[dict]:
    """Search the web via Serper API (free tier: 2500 searches)."""
    if not settings.serper_api_key:
        return []

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                "https://google.serper.dev/search",
                headers={
                    "X-API-KEY": settings.serper_api_key,
                    "Content-Type": "application/json",
                },
                json={"q": f"{query} India government scheme 2025 2026", "num": 10},
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            for item in data.get("organic", [])[:5]:
                title = item.get("title", "")
                link = item.get("link", "")
                snippet = item.get("snippet", "")
                results.append({
                    "id": f"search-{hashlib.md5(link.encode()).hexdigest()[:8]}",
                    "title": title,
                    "description": snippet,
                    "url": link,
                    "source": "web_search",
                    "category": "scholarship",
                })
            return results
    except Exception as e:
        logger.warning(f"Web search failed: {e}")
        return []


def scrape_page_content(url: str) -> str:
    """Fetch and extract main text content from a URL (for RAG ingestion)."""
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True, headers=_HEADERS) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return ""
            soup = BeautifulSoup(resp.text, "lxml")
            # Remove script/style
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            return soup.get_text(separator="\n", strip=True)[:10000]
    except Exception as e:
        logger.warning(f"Failed to scrape content from {url}: {e}")
        return ""
