@echo off
chcp 65001 > nul
title CallWrapped - Discord Voice Bot (Hackathon Edition)

echo ===================================================
echo   CallWrapped - Discord Voice Bot Launcher
echo   Powered by AssemblyAI Universal-3.5 Pro + Groq LPU
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
    echo Please ensure the virtualenv is set up properly.
    pause
    exit /b 1
)

echo Starting Discord Voice Bot...
"%PY_EXE%" -m bot.main

pause
