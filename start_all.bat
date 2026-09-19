@echo off
chcp 65001 > nul
title Voice Arbitrator - Full System Launcher

echo ===================================================
echo   Voice Arbitrator - Launching All Services
echo   1. FastAPI Backend + Live Dashboard (Port 8000)
echo   2. Discord Voice Bot (Silent Referee)
echo ===================================================
echo.

start "Voice Arbitrator - Backend" cmd /k "%~dp0start_backend.bat"
timeout /t 3 /nobreak > nul

start "Voice Arbitrator - Discord Bot" cmd /k "%~dp0start_bot.bat"

echo Opening Live Dashboard in browser...
start http://localhost:8000

echo.
echo All services launched!
echo Press any key to close this launcher window (services will stay open).
pause > nul
