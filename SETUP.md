# LifePilot — Team Setup & Contribution Guide

This guide gets a new teammate from **nothing installed** to **running LifePilot locally** and **pushing changes** — in about 10 minutes. Follow it top to bottom.

> TL;DR (Windows): install **Python 3.11+** and **Git**, then:
> ```powershell
> git clone https://github.com/sawaraunakk31/lifepilot.git
> cd lifepilot/backend
> ./run.ps1
> ```
> Open <http://127.0.0.1:8000>. That's it — no keys, no Docker, no Node.

---

## 0. What you're setting up

- **Backend:** Python + FastAPI (serves both the API and the web UI).
- **Database:** SQLite — a single local file, created automatically. No DB install.
- **Frontend:** built into the backend (plain HTML/JS + Tailwind via CDN). **No Node/npm needed.**
- **AI:** works **offline** out of the box (a deterministic engine). Optional local LLM via Ollama.

**You do NOT need:** Docker, Node.js, any paid API key, any account, or any certificate/`.pem` file.

---

## 1. Prerequisites (install these once)

| Tool | Version | Windows | macOS | Linux |
|------|---------|---------|-------|-------|
| **Python** | 3.11 or newer | [python.org/downloads](https://www.python.org/downloads/) — **tick "Add Python to PATH"** during install | `brew install python@3.11` | `sudo apt install python3 python3-venv` |
| **Git** | any recent | [git-scm.com](https://git-scm.com/download/win) | `brew install git` | `sudo apt install git` |
| **VS Code** (recommended editor) | latest | [code.visualstudio.com](https://code.visualstudio.com/) | same | same |
| **GitHub CLI** (easiest login) | latest | [cli.github.com](https://cli.github.com/) | `brew install gh` | see site |

**Verify the installs** (open a new terminal after installing):

```powershell
python --version      # should print Python 3.11.x or newer
git --version
```

> On Windows, if `python` opens the Microsoft Store instead of printing a version, reinstall Python from python.org and ensure **"Add Python to PATH"** is checked.

---

## 2. Get the code

```powershell
git clone https://github.com/sawaraunakk31/lifepilot.git
cd lifepilot
```

This creates a `lifepilot` folder. All commands below assume you are inside it.

---

## 3. Run it

### Windows (recommended — one command)

```powershell
cd backend
./run.ps1
```

`run.ps1` automatically:
1. Creates a **pip-free** virtual environment (so no certificate/`.pem` files ever land in the project — a project rule).
2. Installs the Python dependencies.
3. Creates your local `.env` from `.env.example` (defaults work as-is).
4. Starts the server at **<http://127.0.0.1:8000>**.

> **If PowerShell blocks the script** with an execution-policy error, run this once and try again:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```
> Or run without changing settings: `powershell -ExecutionPolicy Bypass -File run.ps1`

### macOS / Linux (manual steps)

```bash
cd backend
python3 -m venv --without-pip .venv
# Install deps into the venv using your system pip (adjust python3.11 to your version if needed):
python3 -m pip install --target ".venv/lib/python3.11/site-packages" -r requirements.txt
cp .env.example .env
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

> Not sure of your Python version folder? Run `ls .venv/lib` after creating the venv and use whatever `pythonX.Y` you see.

### Open the app

Go to **<http://127.0.0.1:8000>** in your browser.
Click **Enter LifePilot** → **Profile & Settings** → **Example** → **Save & run LifePilot**.
You should see the dashboard populate with matched schemes.

**To stop the server:** press `Ctrl + C` in the terminal.

---

## 4. Verify everything works

- Interactive API docs: **<http://127.0.0.1:8000/docs>**
- Health check: **<http://127.0.0.1:8000/api/health>** should return `{"status":"ok", ...}`
- In the UI, the **AI Assistant** tab should answer questions like *"How much can I unlock?"*

---

## 5. (Optional) Enable a real local AI model — still free

The app works fully without this. If you want richer generated text:

1. Install **[Ollama](https://ollama.com)** (free, runs offline on your machine).
2. Pull a small model:
   ```powershell
   ollama pull qwen2.5:3b
   ```
3. Edit `backend/.env` and set:
   ```
   LLM_PROVIDER=ollama
   ```
4. Restart the server. That's it — no API key, nothing leaves your machine.

---

## 6. Day-to-day: making changes and pushing

### 6.1 First-time Git setup (once per machine)

```powershell
git config --global user.name  "Your Name"
git config --global user.email "you@example.com"
```

Sign in to GitHub so you can push (easiest with GitHub CLI):

```powershell
gh auth login
# choose: GitHub.com → HTTPS → Login with a web browser, then follow the prompts
```

> You must be added as a **collaborator** on the repo to push. Ask the repo owner (sawaraunakk31) to invite your GitHub username via **Settings → Collaborators**.

### 6.2 The workflow for every change

Always work on a **branch**, then open a Pull Request. This keeps `main` stable.

```powershell
# 1. Get the latest main
git checkout main
git pull origin main

# 2. Create a branch for your task
git checkout -b feature/short-description       # e.g. feature/onboarding-wizard

# 3. ...make your changes, run ./run.ps1, test in the browser...

# 4. Stage and commit with a clear message
git add -A
git commit -m "Add onboarding wizard to profile flow"

# 5. Push your branch
git push -u origin feature/short-description
```

Then on GitHub: open a **Pull Request** from your branch into `main`, add a short description, and request a review. Merge after approval.

> Prefer pushing straight to `main` in a tiny team? You can — just **always `git pull origin main` before you push** to avoid conflicts. Branches + PRs are safer once more than one person is committing.

### 6.3 Keeping your branch up to date

```powershell
git checkout main
git pull origin main
git checkout your-branch
git merge main            # resolve any conflicts, then commit
```

---

## 7. Ground rules (please read — these are strict)

These protect users' privacy and keep the project clean. PRs that break them will be reverted.

1. **No certificate or key files, ever** — no `.pem`, `.key`, `.crt`, `.pfx`. Avoid libraries that bundle them (that's why we use a pip-free venv and stdlib networking).
2. **No paid services or API keys.** Everything must be free and run locally.
3. **Never commit secrets.** `.env`, the database (`*.db`), and `.venv/` are git-ignored — don't force-add them. Check `git status` before committing.
4. **Only reputable, free resources** (the current CDNs: Tailwind, Google Fonts, Chart.js, Lucide). Don't add random/unknown remote scripts.
5. **Keep data local.** The app must never send user data anywhere except its own backend.

Quick self-check before every push:

```powershell
git status                       # make sure no .env / .db / .venv / .pem is staged
```

---

## 8. Project structure (where things live)

```
lifepilot/
├─ README.md                 # project overview & features
├─ SETUP.md                  # this guide
└─ backend/
   ├─ run.ps1                # one-command setup + run (Windows)
   ├─ requirements.txt       # Python dependencies
   ├─ .env.example           # config template (copy to .env)
   └─ app/
      ├─ main.py             # FastAPI app + serves the UI
      ├─ config.py           # settings from .env
      ├─ database.py         # SQLite via SQLAlchemy
      ├─ models.py           # DB tables
      ├─ schemas.py          # request/response models
      ├─ security.py         # security headers, CSP, rate limiting
      ├─ agents/orchestrator.py   # the multi-agent pipeline
      ├─ services/           # eligibility, analytics, assistant, calendar
      ├─ llm/provider.py     # pluggable LLM (mock / ollama)
      ├─ routers/            # API endpoints
      ├─ data/scholarships.json   # the scheme dataset
      └─ frontend/           # index.html, app.js, styles.css (the UI)
```

Want a feature overview instead? See [README.md](README.md).

---

## 9. Troubleshooting

| Problem | Fix |
|---------|-----|
| `python` not recognized | Reinstall Python from python.org with **"Add to PATH"** checked; open a new terminal. |
| `run.ps1 cannot be loaded ... execution policy` | `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` (or `powershell -ExecutionPolicy Bypass -File run.ps1`). |
| `Port 8000 is already in use` | Start on another port: `.venv\Scripts\python -m uvicorn app.main:app --port 8001` and open that port. |
| Page loads but looks unstyled | You're offline — the UI uses free CDNs (Tailwind/fonts). Reconnect and refresh. |
| `git push` rejected / auth failed | Run `gh auth login`, and make sure you were added as a repo collaborator. |
| Changes not showing | Hard-refresh the browser (`Ctrl + F5`) or restart the server. |
| Reset a broken environment | Delete the `backend/.venv` folder and re-run `./run.ps1`. |

---

## 10. Quick command reference

```powershell
# Start the app (Windows)
cd backend; ./run.ps1

# Start on a custom port
cd backend; .venv\Scripts\python -m uvicorn app.main:app --reload --port 8001

# Update your local copy
git pull origin main

# Save & share your work
git checkout -b feature/my-change
git add -A
git commit -m "Describe what you changed"
git push -u origin feature/my-change
```

Welcome to the team — happy building! 🚀
