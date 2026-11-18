$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[1/4] Creating virtual environment..."
    py -3.11 -m venv .venv
    Write-Host "[2/4] Installing dependencies..."
    & ".venv\Scripts\python.exe" -m pip install -r requirements.txt
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example. Please fill in your API keys."
}

if ((-not (Test-Path "models\bge-base-zh-v1.5\config.json")) -or (-not (Test-Path "models\bge-reranker-base\config.json"))) {
    Write-Host "[3/4] Downloading local models, this can take a few minutes..."
    & ".venv\Scripts\python.exe" scripts\download_models.py
}

Write-Host "[4/4] Preparing Unstructured NLP model and starting 知库 RAG..."
& ".venv\Scripts\python.exe" scripts\setup_spacy.py
Write-Host "Open http://127.0.0.1:8000"
& ".venv\Scripts\python.exe" run.py