@echo off
chcp 65001 > nul
title AI Third Participant - Live Web Dashboard Server

echo ===================================================
echo   AI Third Participant - Live Dashboard Server
echo   FastAPI + Real-time Sync API on port 8000
echo ===================================================
echo.

cd /d "%~dp0backend"
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Python virtual environment not found in backend\venv!
    pause
    exit /b 1
)

echo Starting Live Server at http://127.0.0.1:8000 ...
venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
