@echo off
echo Starting AI Third Participant Backend (FastAPI)...
cd /d "%~dp0backend"
if not exist "venv\Scripts\python.exe" (
    echo Error: Python virtual environment not found in backend\venv.
    pause
    exit /b 1
)
if not exist ".env" (
    echo Warning: .env not found. Copying .env.example to .env
    copy .env.example .env
)
venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
