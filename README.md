# LifePilot — AI Chief of Staff for Citizens

LifePilot takes a citizen's profile (e.g. *"final-year engineering student in Karnataka, family income ₹3 lakh"*)
and autonomously **discovers scholarships/grants, checks eligibility, builds a document checklist,
tracks deadlines, and generates a personalised roadmap** — using a small team of cooperating agents.

This repository is a **working prototype**: intentionally simple, 100% free & open-source, and it runs
**offline with no API keys and no Docker**.

---

## What is built and working right now

| Area | Status | Notes |
|------|--------|-------|
| Multi-agent pipeline | ✅ Working | Planner → Research → Eligibility → Document → Tracking → Roadmap → Insight agents, each with confidence scores |
| Rule-based eligibility engine | ✅ Working | Deterministic, explainable (gives *reasons* and *gaps*), no LLM needed |
| Curated opportunity dataset | ✅ Working | 10 real Indian schemes (NSP, INSPIRE, AICTE Pragati, YASASVI, Vidyasiri, PMKVY, Startup India, etc.) |
| **Benefit estimator** | ✅ Working | Parses scheme amounts → *"you could unlock ₹X/year"* |
| **What-If Simulator** | ✅ Working | Change income/category/state → eligibility & benefits recompute live (never saved) |
| **AI Assistant** | ✅ Working | Chat grounded on *your real matches* — no hallucinated schemes |
| **Application readiness engine** | ✅ Working | De-duplicated master document checklist across schemes + readiness % |
| Analytics & charts | ✅ Working | Eligibility donut, value-by-scheme bar, deadline radar, animated counters |
| Personalised roadmap | ✅ Working | Step-by-step; LLM only *enhances* wording when available |
| Pluggable LLM layer | ✅ Working | `mock` (offline, default) or `ollama` (local, free). Never a paid API |
| FastAPI backend + SQLite | ✅ Working | Auto-creates a local `lifepilot.db`, zero setup |
| Redesigned dark web UI | ✅ Working | Glassmorphism, animations, sidebar SPA: Dashboard, Discover, Simulator, Assistant, Documents, Activity, Profile |
| Data persistence | ✅ Working | Profiles + agent runs in SQLite; document vault in browser localStorage |

### Intentionally deferred (for later iterations)
- **Live browser scraping (Playwright / Browser Use)** — the prototype uses a **curated local dataset**
  instead of navigating unknown websites. This is a deliberate **security/privacy choice** for the prototype
  and keeps it fast and reproducible. Real scraping can be added behind the same `ResearchAgent` interface.
- **OCR (PaddleOCR/Tesseract)** — heavy dependency; document *checklists* work, document *scanning* is future.
- **Next.js/Shadcn frontend** — replaced by a lightweight built-in UI so it runs with zero Node/npm setup.
  The API is clean and CORS-ready, so a Next.js frontend can be added later without backend changes.

---

## Security & privacy (by design)

- **No paid APIs, no license keys, no cloud accounts** required to run.
- **Zero certificate/key material anywhere — no `.pem`, `.key`, `.crt`, `.pfx`.**
  We deliberately avoid `httpx`/`requests` (they bundle `certifi`'s `cacert.pem`) and use Python's
  stdlib `urllib` instead. The virtual environment is built **without pip** (`python -m venv --without-pip`)
  so pip's own vendored `cacert.pem` never lands in the project. `run.ps1` also scans and strips any stray
  `.pem` as a safety net, and `.gitignore` blocks all cert/key extensions.
- **Only reputable, free CDNs** for the UI (Tailwind, Google Fonts, Chart.js via jsDelivr, Lucide via unpkg) —
  all swappable for local files. No unknown/random remote resources.
- **No secrets in code.** Config comes from a local `.env` (git-ignored). A `.env.example` documents every option.
- **All data stays on your machine** — SQLite file + browser localStorage. Nothing is uploaded anywhere.
- Inputs are validated with Pydantic; all rendered text in the UI is HTML-escaped to prevent injection.
- No automatic account creation or form submission — the agent only *researches and prepares*.

---

## Tech stack (all free & open-source)

- **Backend:** FastAPI, SQLAlchemy, Pydantic (networking via stdlib `urllib` only — no HTTP-client cert bundles)
- **Database:** SQLite (default) — swappable to PostgreSQL via one `.env` line
- **LLM:** pluggable — offline `mock` engine (default) or local **Ollama** (Qwen/Llama/Gemma) — no paid keys
- **Frontend:** built-in dark SPA — vanilla JS + Tailwind + Chart.js + Lucide (all free CDNs)

---

## Run it (Windows, ~1 minute)

```powershell
cd backend
./run.ps1
```

Then open **http://127.0.0.1:8000**, go to **Profile & Settings** → **Example** → **Save & run LifePilot**.
Explore the **Dashboard, Discover, What-If Simulator, AI Assistant, Documents** and **Agent Activity** views.

<details>
<summary>Manual steps (any OS) — pem-free venv</summary>

```bash
cd backend
# Build the venv WITHOUT pip so no cacert.pem is ever placed in the project:
python -m venv --without-pip .venv
# Install deps into it using your system pip (its cert bundle lives outside the project):
python -m pip install --target .venv/Lib/site-packages -r requirements.txt   # Windows
# macOS/Linux target path: .venv/lib/python3.11/site-packages
cp .env.example .env        # Windows: copy .env.example .env
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000            # Windows
# macOS/Linux: .venv/bin/python -m uvicorn app.main:app --reload --port 8000
```
</details>

- Interactive API docs: **http://127.0.0.1:8000/docs**

---

## Project structure

```
backend/
├─ app/
│  ├─ main.py               # FastAPI app, serves API + built-in UI
│  ├─ config.py             # env-based settings (no hard-coded secrets)
│  ├─ database.py           # SQLite/Postgres via SQLAlchemy
│  ├─ models.py             # Profiles, AgentRun, AgentLog, MatchResult
│  ├─ schemas.py            # Pydantic request/response models
│  ├─ agents/
│  │  └─ orchestrator.py    # multi-agent pipeline (Planner…Insight)
│  ├─ services/
│  │  ├─ eligibility.py     # rule-based, explainable eligibility scoring
│  │  ├─ analytics.py       # benefit estimator, readiness, urgency, master checklist
│  │  └─ assistant.py       # grounded Q&A over your matches
│  ├─ llm/
│  │  └─ provider.py        # pluggable LLM (mock / ollama) — stdlib urllib only
│  ├─ routers/              # profiles, opportunities, agent (run/simulate/assistant)
│  └─ data/scholarships.json# curated opportunity dataset
├─ frontend/                # built-in dark SPA (index.html + app.js + styles.css)
├─ requirements.txt
├─ .env.example
└─ run.ps1
```

### Key API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/profiles` | Create a profile |
| POST | `/api/agent/run/{id}` | Run the agent pipeline (saves run + returns insights) |
| POST | `/api/agent/simulate` | What-if evaluation, **not saved** |
| POST | `/api/agent/assistant` | Grounded Q&A about your matches |
| GET | `/api/opportunities` | Browse the raw dataset |
| GET | `/api/health` | Status + active LLM provider |

---

## What keys / accounts do you need?

**To run the prototype as shown: none.** It works fully offline with the `mock` engine.

Optional free upgrades (only if you want real generative text):

| Want | What to install/set | Cost |
|------|--------------------|------|
| Real local LLM roadmaps | Install [Ollama](https://ollama.com), run `ollama pull qwen2.5:3b`, set `LLM_PROVIDER=ollama` in `.env` | Free, offline |
| PostgreSQL instead of SQLite | Set `DATABASE_URL=postgresql+psycopg://user:pass@host:5432/lifepilot` | Free (local Postgres) |

Everything remains free and local. There is **no paid key to buy**.

---

## Roadmap (next iterations)

1. **Live discovery:** add Playwright-based `ResearchAgent` for a *whitelist* of official government portals.
2. **Document intelligence:** PaddleOCR/Tesseract to read uploaded certificates and auto-verify eligibility.
3. **Notifications & deadline reminders** (email via a free SMTP or local scheduler).
4. **Advanced agent skills:** reflection loops, self-consistency, confidence aggregation (LangGraph).
5. **Next.js + Shadcn frontend** consuming the existing API.
