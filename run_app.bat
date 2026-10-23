@echo off
title PlanPulse AI — Intelligent Schedule & Productivity Platform
cd /d "%~dp0"
echo ===================================================
echo Starting PlanPulse AI Platform...
echo Demo User: bandayash11@gmail.com / yash123
echo Local URL: http://127.0.0.1:5000
echo ===================================================
if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe app.py
) else (
    python app.py
)
pause
