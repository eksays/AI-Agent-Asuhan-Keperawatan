@echo off
title CDSS Backend (FastAPI)
cd /d "%~dp0"
echo === CDSS AI Keperawatan - Backend (port 8000) ===
where python >nul 2>nul
if %errorlevel%==0 (
  python -m uvicorn api:app --host 127.0.0.1 --port 8000 --reload
) else (
  "E:\Program\Instalan\Python 3.12.8\python.exe" -m uvicorn api:app --host 127.0.0.1 --port 8000 --reload
)
pause
