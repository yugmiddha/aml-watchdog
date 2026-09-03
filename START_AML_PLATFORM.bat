@echo off
title AML Watchdog Enterprise Platform
cd /d "%~dp0"
cls
echo ===================================================================
echo   [AML WATCHDOG ENTERPRISE] - FINANCIAL CRIME SURVEILLANCE
echo ===================================================================
echo [*] Database   : 500,000 Indexed Records (SQLite WAL Mode)
echo [*] ML Model   : Deep 600-Tree XGBoost (99.20%% ROC-AUC)
echo [*] UI Modules : Executive Dashboard, SQL Studio, Alert Triage,
echo                  Network Graph, 360 Dossier, Scenario Sandbox
echo ===================================================================
echo Starting FastAPI Compliance Engine on http://127.0.0.1:8000 ...
echo.

where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    python run_dashboard.py
) else (
    "C:\Program Files\Python314\python.exe" run_dashboard.py
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Server encountered an issue.
    pause
)
