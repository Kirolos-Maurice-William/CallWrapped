@echo off
chcp 65001 > nul
title AI Third Participant - Discord Voice Bot (Hackathon Edition)

echo ===================================================
echo   AI Third Participant - Discord Voice Bot Launcher
echo   Powered by AssemblyAI Universal-3.5 Pro & Groq LPU
echo ===================================================
echo.

if not exist backend\venv\Scripts\python.exe (
    echo [ERROR] Python virtual environment not found in backend\venv!
    echo Please ensure the virtualenv is set up properly.
    pause
    exit /b 1
)

echo Starting Discord Voice Bot...
backend\venv\Scripts\python.exe -m bot.main

pause
