# Implementation Plan — Live Job Discovery & Simulator Fix

This updated plan details the design for:
1. **Instant What-If Simulator**: Making the simulator run locally and instantly, avoiding rate limits.
2. **AI-Powered Live Job Discovery**: Integrating live, personalized job search from LinkedIn, Indeed, and company career pages using the user's resume, desired role, and skills.

---

## User Review Required

> [!IMPORTANT]
> **Live Job Discovery Methodology**:
> To get direct, clean links to job profiles (avoiding Cloudflare blocking on Indeed and LinkedIn auth walls):
> 1. We will implement a **LinkedIn Guest Portal Scraper** that hits LinkedIn's public seeMoreJobPostings endpoint (`/jobs-guest/jobs/api/seeMoreJobPostings/search`). This runs unauthenticated and yields direct job page links.
> 2. We will implement a **Serper Google Search Portal** to discover live job listings on Indeed, Glassdoor, and company career sites (e.g., searching for `"{desired_role}" "{skills[0]}" jobs remote OR India 2026`).
> 3. We will cross-reference the live job listings with the user's uploaded resume text and skills to compute a personalized **Fit Score** and dynamic matching reasons.

---

## Proposed Changes

### 1. What-If Simulator Fixes

#### [MODIFY] [research.py](file:///e:/project%201/backend/app/agents/research.py)
- Bypass the LangGraph web scraping/search nodes during simulation runs (`state.profile.get("name") == "Simulation"`).
- Instantly load the curated local scholarship list from `scholarships.json`.

#### [MODIFY] [eligibility_agent.py](file:///e:/project%201/backend/app/agents/eligibility_agent.py)
- Skip calling the Groq LLM agent for eligibility evaluation during simulations.
- Use only the rules-based, deterministic `elig_engine.evaluate` for instant UI updates.

#### [MODIFY] [app.js](file:///e:/project%201/frontend/app.js)
- Modify line 441 to format the delta using a pipe separator:
  - `${sign(dE)}${dE} schemes | ${dB < 0 ? '-' : dB > 0 ? '+' : ''}${fmtINR(Math.abs(dB))}` (e.g. `+1 schemes | +₹59,950`).

---

### 2. Live Job Discovery

#### [MODIFY] [opportunities.py](file:///e:/project%201/backend/app/routers/opportunities.py)
- **Implement `scrape_linkedin_jobs(keywords: str, location: str)`**:
  - Connect to LinkedIn's public `jobs-guest/jobs/api/seeMoreJobPostings/search` endpoint.
  - Parse the HTML response using BeautifulSoup to extract job title, company, URL (cleaned of tracking params), and location.
- **Implement `search_serper_jobs(q: str, skills: list[str], location: str)`**:
  - Build a targeted search query: e.g., `"Data Analyst" "python" "sql" remote jobs 2026`.
  - Fetch organic links from Google (Indeed, Glassdoor, company careers pages).
- **Update `get_jobs`**:
  - Perform live scraping via both the LinkedIn Guest Scraper and the Serper Search Scraper based on the user's inputs.
  - De-duplicate and merge results with the curated Indian jobs in the DB.
- **Update `match_jobs`**:
  - Call the live job search using the `desired_role` and `skills` provided in the request payload.
  - Scan the job descriptions against the uploaded resume text and skills to compute the fit score and generate specific reasoning (e.g., "Matched 3 skills: python, sql, tableau").

---

## Verification Plan

### Automated Tests
- Test live job fetching for any role (e.g., Data Analyst):
  ```powershell
  Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/api/opportunities/jobs?q=data+analyst"
  ```
- Test job matching endpoint with resume payload, desired role, and skills:
  ```powershell
  Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/opportunities/jobs/match" -ContentType "application/json" -Body '{"profile":{"field_of_study":"Computer Science"},"resume_text":"Data Analyst with Python and SQL experience","desired_role":"Data Analyst","skills":["python","sql"]}'
  ```

### Manual Verification
- Go to the **Discover Jobs** tab in the UI.
- Paste/upload a CV, enter "Data Analyst" as the desired role, and input skills: "python, sql".
- Click **Scan Jobs & Check Eligibility** and verify that live Data Analyst jobs from LinkedIn, Indeed, etc., are loaded with direct links and personalized match scores.
