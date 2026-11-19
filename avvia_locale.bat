@echo off
title FinanceTool - IPO & Micro-Cap AI Scouter
echo ============================================================
echo   Avvio di IPO & Micro-Cap AI Scouter (Modalita Full-Live)
echo   Backend FastAPI (Porta 8000) + Frontend Vite (Porta 5173)
echo ============================================================

echo [1/2] Avvio del backend FastAPI in background...
start "FinanceTool - Backend FastAPI" cmd /k "cd backend && .venv\Scripts\python -m uvicorn api:app --reload --port 8000"

timeout /t 3 /nobreak >nul

echo [2/2] Avvio del frontend Vite...
start "FinanceTool - Frontend Vite" cmd /k "cd frontend && npm run dev"

timeout /t 2 /nobreak >nul

echo Apertura dell'applicazione nel browser...
start http://localhost:5173

echo.
echo Tutto pronto! La dashboard interattiva e aperta su http://localhost:5173
echo In modalita locale tutti i tasti (Scansiona live, Salva regole, Auto-Pilot)
echo sono attivi in tempo reale al 100%%.
echo.
pause
