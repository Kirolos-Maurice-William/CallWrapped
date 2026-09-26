@echo off
chcp 65001 > nul
title CallWrapped - FastAPI Event Hub & Dashboard Server

echo ===================================================
echo   CallWrapped - FastAPI Server & Dashboard
echo   Listening on http://localhost:8000
echo ===================================================
echo.

cd /d "%~dp0backend"
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Python virtual environment not found in backend\venv!
    pause
    exit /b 1
)

echo Starting Server...
venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
