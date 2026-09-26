@echo off
chcp 65001 > nul
title CallWrapped - Full System Launcher

echo ===================================================
echo   CallWrapped - Launching All Services
echo   1. FastAPI Backend + Live Dashboard (Port 8000)
echo   2. Discord Voice Bot (Silent Referee)
echo ===================================================
echo.

start "CallWrapped - Backend" cmd /k "%~dp0start_backend.bat"
timeout /t 3 /nobreak > nul

start "CallWrapped - Discord Bot" cmd /k "%~dp0start_bot.bat"

echo Opening Live Dashboard in browser...
start http://localhost:8000

echo.
echo All services launched!
echo Press any key to close this launcher window (services will stay open).
pause > nul
