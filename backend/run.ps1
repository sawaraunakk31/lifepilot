# LifePilot — Setup & Run Script (Windows PowerShell)
# Usage: cd backend && ./run.ps1

$ErrorActionPreference = "Stop"
Write-Host "`n🚀 LifePilot v2.0 — AI Chief of Staff for Citizens" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`n"

# Check Python
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { Write-Host "❌ Python not found. Install from python.org" -ForegroundColor Red; exit 1 }
$ver = python --version 2>&1
Write-Host "✅ $ver" -ForegroundColor Green

# Create .env if missing
if (-not (Test-Path ".env")) {
    Write-Host "📋 Creating .env from .env.example..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
}

# Create virtual environment
if (-not (Test-Path ".venv")) {
    Write-Host "📦 Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
}

# Activate and install dependencies
Write-Host "📦 Installing dependencies..." -ForegroundColor Yellow
& .\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet 2>$null
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt --quiet

# Check if Groq API key is set
$envContent = Get-Content ".env" -Raw
if ($envContent -match "GROQ_API_KEY=\s*$" -or $envContent -notmatch "GROQ_API_KEY") {
    Write-Host "`n⚠️  No GROQ_API_KEY set. The app will use mock LLM (no real AI)." -ForegroundColor Yellow
    Write-Host "   Get a FREE key at: https://console.groq.com" -ForegroundColor Yellow
    Write-Host "   Then add it to .env: GROQ_API_KEY=your_key_here`n" -ForegroundColor Yellow
}

# Run the server
Write-Host "`n✨ Starting LifePilot..." -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
Write-Host "🌐 Open: http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "📚 API Docs: http://127.0.0.1:8000/docs" -ForegroundColor Green
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`n"

& .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
