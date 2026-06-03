@echo off
title CDSS Frontend (Next.js)
cd /d "%~dp0"
echo === CDSS AI Keperawatan - Frontend (http://localhost:3000) ===
if not exist "node_modules" (
  echo Menginstal dependency pertama kali...
  call npm install
)
call npm run dev
pause
