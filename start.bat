@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto create_venv
".venv\Scripts\python.exe" -c "import fastapi, llama_index.core, chromadb" >nul 2>nul
if errorlevel 1 goto install_deps
goto venv_ready

:create_venv
echo [1/4] Creating virtual environment...
where py >nul 2>nul
if errorlevel 1 (
  python -m venv .venv
) else (
  py -3.11 -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
  echo Failed to create .venv. Please install Python 3.11 and try again.
  pause
  exit /b 1
)

:install_deps
echo [2/4] Installing dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Dependency installation failed.
  pause
  exit /b 1
)

:venv_ready
if exist ".env" goto env_ready
copy ".env.example" ".env" >nul
echo Created .env from .env.example. Please fill in your API keys.

:env_ready
set NEED_MODELS=0
if not exist "models\bge-base-zh-v1.5\config.json" set NEED_MODELS=1
if not exist "models\bge-reranker-base\config.json" set NEED_MODELS=1
if "%NEED_MODELS%"=="0" goto models_ready
echo [3/4] Downloading local models, this can take a few minutes...
".venv\Scripts\python.exe" scripts\download_models.py
if errorlevel 1 (
  echo Model download failed. Please run scripts\download_models.py manually.
  pause
  exit /b 1
)

:models_ready
echo [4/4] Preparing models and starting Zhiku RAG at http://127.0.0.1:8000
".venv\Scripts\python.exe" scripts\setup_spacy.py
".venv\Scripts\python.exe" run.py
pause