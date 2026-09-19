@echo off
title AI Third Participant - Discord Voice Bot
color 0B
chcp 65001 >nul

echo ===================================================
echo   AI Third Participant - Discord Voice Bot Launcher
echo ===================================================
echo.

cd /d "%~dp0\.."

set PYTHON_EXE=backend\venv\Scripts\python.exe

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Virtual environment not found at backend\venv!
    echo Please ensure Python virtual environment is set up.
    pause
    exit /b 1
)

echo Starting Discord Voice Bot...
echo.
"%PYTHON_EXE%" -m discord_bot.bot

pause
