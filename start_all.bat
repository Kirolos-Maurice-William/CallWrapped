@echo off
chcp 65001 > nul
title CallWrapped - Full System Launcher

echo ===================================================
echo   CallWrapped - Launching All Services
echo   1. FastAPI Backend + Live Dashboard (Port 8000)
echo   2. Discord Voice Bot (Silent Referee)
echo ===================================================
echo.

rem Pre-flight: Check frontend build status
if not exist "%~dp0frontend\out\index.html" (
    echo [NOTICE] Frontend build not found in frontend\out.
    echo Launching Next.js development server on port 3000...
    start "CallWrapped - Frontend (Dev)" cmd /k "%~dp0start_frontend.bat"
) else (
    echo [OK] Frontend static export found in frontend\out.
)

start "CallWrapped - Backend" cmd /k "%~dp0start_backend.bat"
timeout /t 3 /nobreak > nul

start "CallWrapped - Discord Bot" cmd /k "%~dp0start_bot.bat"

echo Opening Live Dashboard in browser...
if exist "%~dp0frontend\out\index.html" (
    start http://localhost:8000
) else (
    start http://localhost:3000
)

echo.
echo All services launched!
echo Press any key to close this launcher window (services will stay open).
pause > nul
