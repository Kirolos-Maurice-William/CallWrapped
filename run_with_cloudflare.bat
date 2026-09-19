@echo off
echo ===================================================
echo   AI Third Participant - Cloudflare Live Tunnel
echo ===================================================
cd /d "%~dp0"

echo [1/2] Starting Backend Server (serving UI + AI Audio Engine on Port 8000)...
start "AI Call Agent Backend" cmd /k "cd /d %~dp0backend && .\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

timeout /t 3 >nul

echo [2/2] Starting Cloudflare HTTPS Tunnel...
echo.
echo ========================================================
echo   LOOK BELOW FOR YOUR PUBLIC HTTPS LINK:
echo   It will look like: https://xxxx.trycloudflare.com
echo   Open that link and share it with your friend!
echo ========================================================
echo.
cloudflared tunnel --url http://localhost:8000
