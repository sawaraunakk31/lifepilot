"""Opportunities endpoints - scraping, semantic search, and job listings."""
from __future__ import annotations

import logging
import io
import urllib.parse
import hashlib
import re
from typing import List, Optional
import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Query
import pypdf
from pydantic import BaseModel

from app.config import settings
from app.scraper.engine import scrape_portals, _scrape_rss_jobs
from app.knowledge.vectorstore import search as vector_search, add_schemes
from app.auth import get_current_user

logger = logging.getLogger("lifepilot.routers.opportunities")

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


@router.get("")
def list_opportunities():
    """Return all opportunities in the knowledge base (or empty list if using dynamic search)."""
    return []


class ScrapeRequest(BaseModel):
    urls: List[str]
    keywords: Optional[List[str]] = None


@router.get("/search")
def search_opportunities(q: str):
    """Semantic search over the ChromaDB vector store of schemes."""
    if not q.strip():
        return []
    try:
        results = vector_search(q, n_results=10)
        return results
    except Exception as e:
        logger.error(f"Failed to search opportunities: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scrape")
def scrape_and_index(payload: ScrapeRequest):
    """Scrape government portals and save newly discovered schemes to ChromaDB."""
    if not payload.urls:
        raise HTTPException(status_code=400, detail="At least one portal URL is required.")
    
    try:
        scraped = scrape_portals(payload.urls, payload.keywords)
        added_count = 0
        if scraped:
            added_count = add_schemes(scraped)
        return {
            "status": "success",
            "scraped_count": len(scraped),
            "indexed_count": added_count,
            "opportunities": scraped
        }
    except Exception as e:
        logger.error(f"Failed to scrape portals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def scrape_linkedin_jobs(keywords: str, location: str = "India") -> list[dict]:
    """Fetch live job postings from LinkedIn's public Guest seeMoreJobPostings endpoint."""
    jobs = []
    url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    params = {
        "keywords": keywords,
        "location": location,
        "start": 0
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
    }
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True, headers=headers) as client:
            resp = client.get(url, params=params)
            if resp.status_code != 200:
                logger.warning(f"LinkedIn seeMoreJobPostings failed with status {resp.status_code}")
                return []
            
            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.find_all("li")
            for card in cards:
                title_el = card.find(class_=re.compile("title")) or card.find("h3") or card.find("h4")
                company_el = card.find(class_=re.compile("subtitle")) or card.find(class_=re.compile("company")) or card.find("h4")
                location_el = card.find(class_=re.compile("location"))
                link_el = card.find("a", href=True)
                
                if not title_el or not link_el:
                    continue
                
                title = title_el.get_text(strip=True)
                company = company_el.get_text(strip=True) if company_el else "Unknown Company"
                loc = location_el.get_text(strip=True) if location_el else location
                href = link_el["href"]
                
                # Clean tracking parameters from URL
                parsed_url = urllib.parse.urlparse(href)
                clean_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
                
                jobs.append({
                    "id": f"linkedin-{hashlib.md5(clean_url.encode()).hexdigest()[:8]}",
                    "title": title,
                    "company": company,
                    "location": loc,
                    "country": "India" if "india" in loc.lower() else "Global",
                    "job_type": "Remote" if "remote" in loc.lower() or "remote" in title.lower() else "On-location",
                    "description": f"Live job opening for {title} at {company} in {loc}.",
                    "url": clean_url,
                    "salary": "Not specified",
                    "salary_num": 0,
                    "category": "job",
                    "source": "LinkedIn"
                })
    except Exception as e:
        logger.warning(f"LinkedIn scraping failed: {e}")
    return jobs


def search_serper_jobs(q: str, skills: list[str] = None, location: str = "India") -> list[dict]:
    """Search for jobs on Google via Serper API (Indeed, Glassdoor, company careers pages)."""
    if not settings.serper_api_key:
        logger.info("SERPER_API_KEY is not configured. Skipping Serper job search.")
        return []
    
    # Build query
    skills_part = " ".join(f'"{s}"' for s in skills[:3]) if skills else ""
    loc_part = f"({location} OR remote)" if location else "remote"
    query = f'"{q}" {skills_part} jobs {loc_part} 2026'
    
    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": settings.serper_api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "q": query,
        "num": 10
    }
    
    jobs = []
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                logger.warning(f"Serper search failed with status {resp.status_code}")
                return []
            
            data = resp.json()
            for item in data.get("organic", [])[:8]:
                title = item.get("title", "")
                link = item.get("link", "")
                snippet = item.get("snippet", "")
                
                company = "Hiring Company"
                if " at " in title:
                    parts = title.split(" at ", 1)
                    title_role = parts[0].strip()
                    company_part = parts[1].split("-", 1)[0].split("|", 1)[0].strip()
                    company = company_part
                elif " - " in title:
                    parts = title.split(" - ", 1)
                    if len(parts[1]) < len(parts[0]):
                        company = parts[1].split("|", 1)[0].strip()
                
                jobs.append({
                    "id": f"serper-{hashlib.md5(link.encode()).hexdigest()[:8]}",
                    "title": title,
                    "company": company,
                    "location": location,
                    "country": "India" if "india" in location.lower() or "india" in snippet.lower() else "Global",
                    "job_type": "Remote" if "remote" in snippet.lower() or "remote" in title.lower() else "On-location",
                    "description": snippet,
                    "url": link,
                    "salary": "Not specified",
                    "salary_num": 0,
                    "category": "job",
                    "source": "Google Search"
                })
    except Exception as e:
        logger.warning(f"Serper job search failed: {e}")
    return jobs


@router.get("/jobs")
def get_jobs(q: str = "fresher", skills: Optional[List[str]] = Query(None), location: str = "India"):
    """Search remote and portal job listings via RSS feeds."""
    jobs = []
    
    # 1. Target feeds list (combining general and programming-specific feeds)
    feeds = [
        "https://weworkremotely.com/categories/remote-programming-jobs.rss",
        "https://weworkremotely.com/remote-jobs.rss",
        "https://www.python.org/jobs/feed/rss/"
    ]
    
    # 2. Query expansion for related programming/tech keywords
    q_clean = q.strip().lower()
    search_terms = [q_clean]
    
    # Expand tech queries if any keyword in the search query matches technology patterns
    tech_keywords = {"developer", "engineer", "sde", "programmer", "software", "coder", "coding", "tech", "development"}
    query_words = set(q_clean.split())
    if query_words.intersection(tech_keywords):
        search_terms.extend(["developer", "engineer", "programmer", "software", "sde", "coding", "coder", "development"])
        
    for url in feeds:
        try:
            results = _scrape_rss_jobs(url)
            # Tag RSS results with default global locations
            for j in results:
                j["country"] = "Global"
                j["job_type"] = "Remote"
                j["location"] = "Remote (Global)"
                # Set dynamic USD numeric salary
                j["salary_num"] = 80000
                
            # Filter results to match any of the expanded search terms
            if q_clean:
                filtered = []
                for j in results:
                    title_l = j.get("title", "").lower()
                    desc_l = j.get("description", "").lower()
                    if any(term in title_l or term in desc_l for term in search_terms):
                        filtered.append(j)
                results = filtered
            jobs.extend(results)
        except Exception as e:
            logger.warning(f"Failed to fetch job RSS feed {url}: {e}")
            
    # 3. Fetch from LinkedIn Guest Scraper
    if q_clean:
        try:
            linkedin_results = scrape_linkedin_jobs(q, location=location)
            jobs.extend(linkedin_results)
        except Exception as e:
            logger.warning(f"LinkedIn jobs scraping failed: {e}")

    # 4. Fetch from Serper Search Scraper
    if q_clean:
        try:
            serper_results = search_serper_jobs(q, skills=skills, location=location)
            jobs.extend(serper_results)
        except Exception as e:
            logger.warning(f"Serper jobs searching failed: {e}")
            
    # Load curated Indian jobs from database
    curated_india = []
    try:
        from app.database import SessionLocal
        from app.models import JobOpportunity
        
        db = SessionLocal()
        try:
            db_jobs = db.query(JobOpportunity).all()
            curated_india = [{
                "id": j.id,
                "title": j.title,
                "company": j.company,
                "location": j.location,
                "job_type": j.job_type,
                "country": j.country,
                "salary_num": j.salary_num,
                "salary": j.salary,
                "description": j.description,
                "url": j.url,
                "category": j.category,
                "source": j.source
            } for j in db_jobs]
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Failed to query database JobOpportunity list: {e}")

    # Filter curated Indian jobs by query
    filtered_india = []
    if q_clean:
        for j in curated_india:
            title_l = j.get("title", "").lower()
            company_l = j.get("company", "").lower()
            desc_l = j.get("description", "").lower()
            if any(term in title_l or term in company_l or term in desc_l for term in search_terms):
                filtered_india.append(j)
    else:
        filtered_india = curated_india

    # Combine everything and de-duplicate
    all_jobs = filtered_india + jobs
    seen = set()
    unique_jobs = []
    for job in all_jobs:
        url = job.get("url", "")
        # De-duplicate on URL and/or title+company
        title_company = f"{job.get('title', '').strip().lower()} @ {job.get('company', '').strip().lower()}"
        if url and url in seen:
            continue
        if title_company in seen:
            continue
        if url:
            seen.add(url)
        seen.add(title_company)
        unique_jobs.append(job)
        
    return unique_jobs[:50]


class JobMatchRequest(BaseModel):
    profile: dict
    resume_text: Optional[str] = ""
    desired_role: Optional[str] = ""
    expected_salary: Optional[int] = None
    skills: Optional[List[str]] = None


@router.post("/jobs/match")
def match_jobs(payload: JobMatchRequest):
    profile = payload.profile or {}
    resume = (payload.resume_text or "").lower()
    desired = (payload.desired_role or "").lower()
    skills = [s.lower().strip() for s in (payload.skills or []) if s.strip()]
    
    # 1. Fetch raw jobs
    search_q = payload.desired_role or profile.get("field_of_study") or "fresher"
    location = profile.get("state") or "India"
    raw_jobs = get_jobs(q=search_q, skills=skills, location=location)
    
    matched_jobs = []
    
    for job in raw_jobs:
        title = job.get("title", "")
        company = job.get("company", "")
        role = title
        if not company:
            # Parse company and role from scraped titles "Company: Role"
            title_parts = title.split(":", 1)
            if len(title_parts) > 1:
                company = title_parts[0].strip()
                role = title_parts[1].strip()
            else:
                company = "Remote Company"
                role = title
            
        desc = job.get("description", "")
        desc_lower = desc.lower()
        role_lower = role.lower()
        
        # 2. Calculate Fit Score
        fit_score = 0.50 # Base score
        
        reasons = []
        unmet = []
        skills_matched = []
        
        # Match desired role
        if desired:
            if desired in role_lower:
                fit_score += 0.20
                reasons.append(f"Matches your desired role: '{payload.desired_role}'")
            elif desired in desc_lower:
                fit_score += 0.10
                reasons.append(f"Mentioned in job description: '{payload.desired_role}'")
                
        # Match field of study
        fos = profile.get("field_of_study")
        if fos:
            fos_lower = fos.lower()
            if fos_lower in role_lower or fos_lower in desc_lower:
                fit_score += 0.15
                reasons.append(f"Matches your field of study: '{fos}'")
                
        # Match skills (from preferences or extracted from resume)
        combined_text = resume + " " + " ".join(skills)
        for s in skills:
            if s in desc_lower:
                skills_matched.append(s)
                fit_score += 0.05
        
        # Also check standard skills in resume if no preferences skills
        standard_skills = ["python", "javascript", "react", "node", "sql", "excel", "sales", "marketing", "office", "word", "design"]
        for s in standard_skills:
            if s in combined_text and s in desc_lower:
                if s not in skills_matched:
                    skills_matched.append(s)
                    fit_score += 0.05
                    
        if skills_matched:
            reasons.append(f"Matched {len(skills_matched)} skills: {', '.join(skills_matched)}")
            
        # Match education level
        edu = profile.get("education_level")
        eligible = True
        if edu:
            edu_lower = edu.lower()
            if "phd" in desc_lower or "p.h.d" in desc_lower:
                if edu_lower not in ("postgraduate", "phd"):
                    eligible = False
                    unmet.append("Requires PhD (your education: " + edu + ")")
            elif "master" in desc_lower:
                if edu_lower not in ("postgraduate", "phd"):
                    eligible = False
                    unmet.append("Requires Master's degree (your education: " + edu + ")")
            elif "bachelor" in desc_lower or "degree" in desc_lower or "undergraduate" in desc_lower:
                if edu_lower in ("9th", "10th", "11th", "12th"):
                    eligible = False
                    unmet.append("Requires Bachelor's/Undergraduate degree (your education: " + edu + ")")
                    
        if eligible:
            reasons.append("Your education level aligns with job requirements")
        else:
            fit_score -= 0.20
            
        # Limit fit score to 1.0 (100%) and 0.10 (10%)
        fit_score = max(0.10, min(1.0, fit_score))
        
        # Mock salary generation based on role/field
        if "$" in desc:
            salary = "Estimated $80,000 - $120,000 / year"
        else:
            if "engineer" in role_lower or "developer" in role_lower or "ai" in role_lower or "tech" in role_lower:
                salary = "₹8,00,000 - ₹15,00,000 / year"
            elif "manager" in role_lower or "lead" in role_lower:
                salary = "₹12,00,000 - ₹20,00,000 / year"
            else:
                salary = "₹4,00,000 - ₹8,00,000 / year"
                
        matched_jobs.append({
            "id": job.get("id"),
            "title": role,
            "company": company,
            "description": desc,
            "url": job.get("url"),
            "fit_score": fit_score,
            "eligible": eligible,
            "reasons": reasons,
            "unmet": unmet,
            "salary": job.get("salary", salary),
            "salary_num": job.get("salary_num", 80000 if "$" in desc else 400000),
            "job_type": job.get("job_type", "Remote"),
            "country": job.get("country", "Global"),
            "location": job.get("location", "Remote (Global)"),
            "skills_matched": skills_matched
        })
        
    matched_jobs.sort(key=lambda x: x["fit_score"], reverse=True)
    return matched_jobs


@router.post("/jobs/parse-resume")
async def parse_resume(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf") and not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only PDF and TXT files are supported.")
        
    if file.filename.endswith(".txt"):
        try:
            content = await file.read()
            text = content.decode("utf-8", errors="ignore")
            return {"text": text}
        except Exception as e:
            logger.error(f"Failed to read TXT resume: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to read TXT file: {str(e)}")
            
    # Parse PDF
    try:
        content = await file.read()
        pdf_file = io.BytesIO(content)
        reader = pypdf.PdfReader(pdf_file)
        text_parts = []
        for page in reader.pages:
            text_parts.append(page.extract_text() or "")
        text = "\n".join(text_parts).strip()
        if not text:
            raise HTTPException(status_code=422, detail="Could not extract text from PDF. Ensure the file is not scanned or empty.")
        return {"text": text}
    except Exception as e:
        logger.error(f"Failed to parse PDF resume: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to parse PDF: {str(e)}")


