@echo off
chcp 65001 > nul
title CallWrapped - Next.js Development Server

echo ===================================================
echo   CallWrapped - Next.js Dev Server (Port 3000)
echo   Note: Production build is auto-served at port 8000
echo ===================================================
echo.

cd /d "%~dp0frontend"
npm run dev
pause
