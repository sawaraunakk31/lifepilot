# One-click run for Windows PowerShell.
# Creates a pip-free virtual env (first run), installs deps with the SYSTEM pip
# via --target, and starts LifePilot.
#
# Why pip-free? A venv that contains pip also ships pip's vendored CA bundle
# (pip/_vendor/certifi/cacert.pem). To keep this project 100% free of any .pem /
# certificate files, we build the venv WITHOUT pip and install packages into it
# using the system Python's pip. No certificate files are ever placed in the project.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".venv")) {
    Write-Host "Creating pip-free virtual environment..." -ForegroundColor Cyan
    python -m venv --without-pip .venv
}

# Install deps only if they are missing (keeps normal launches fast & quiet).
if (-not (Test-Path ".venv\Lib\site-packages\fastapi")) {
    Write-Host "Installing dependencies (via system pip, no .pem in project)..." -ForegroundColor Cyan
    python -m pip install --disable-pip-version-check --target ".venv\Lib\site-packages" -r requirements.txt
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example (defaults are fine)." -ForegroundColor Green
}

# Safety net: ensure no certificate files ever linger in the project tree.
$pems = Get-ChildItem -Path .venv -Recurse -Filter *.pem -ErrorAction SilentlyContinue
if ($pems) { $pems | Remove-Item -Force; Write-Host "Removed stray .pem file(s)." -ForegroundColor Yellow }

Write-Host "Starting LifePilot at http://127.0.0.1:8000 ..." -ForegroundColor Green
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
