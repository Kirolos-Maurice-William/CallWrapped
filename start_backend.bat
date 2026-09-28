@echo off
chcp 65001 > nul
title CallWrapped - FastAPI Event Hub & Dashboard Server

echo ===================================================
echo   CallWrapped - FastAPI Server & Dashboard
echo   Listening on http://localhost:8000
echo ===================================================
echo.

set "PY_EXE="
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0.venv\Scripts\python.exe"
) else if exist "%~dp0backend\venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0backend\venv\Scripts\python.exe"
)

if "%PY_EXE%"=="" (
    echo [ERROR] Python virtual environment not found in .venv or backend\venv!
    pause
    exit /b 1
)

echo Starting Server...
cd /d "%~dp0backend"
"%PY_EXE%" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
