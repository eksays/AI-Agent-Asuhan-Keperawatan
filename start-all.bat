@echo off
title CDSS AI Keperawatan - Launcher
echo Menjalankan Backend dan Frontend...
start "CDSS Backend"  "%~dp0backend\run.bat"
start "CDSS Frontend" "%~dp0frontend\run.bat"
echo.
echo   Backend  : http://127.0.0.1:8000   (dokumentasi: /docs)
echo   Frontend : http://localhost:3000
echo.
echo Dua jendela terminal baru telah dibuka. Tutup keduanya untuk menghentikan aplikasi.
timeout /t 6 >nul
