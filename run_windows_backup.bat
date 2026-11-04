@echo off
TITLE GNC Live News Engine - Local Windows Failover Server
COLOR 0A

echo =======================================================================
echo          GLOBAL NEWS FEED ROOM (GNC) - WINDOWS BACKUP SERVER          
echo                    Failover Engine for D:\News Engine                  
echo =======================================================================
echo.

:: Ensure running from D:\News Engine or current script directory
cd /d "%~dp0"
echo [1/4] Current Workspace Directory: %CD%

:: Locate Python executable
set "PYTHON_EXE="
if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
) else (
    for /f "tokens=*" %%i in ('where python 2^>nul') do (
        if not defined PYTHON_EXE set "PYTHON_EXE=%%i"
    )
)

if not defined PYTHON_EXE (
    echo [ERROR] Python was not automatically located.
    pause
    exit /b 1
)

echo [INFO] Using Python: %PYTHON_EXE%

echo [2/4] Verifying Virtual Environment...
if not exist "venv\Scripts\activate.bat" (
    echo Creating virtual environment in venv...
    "%PYTHON_EXE%" -m venv venv
)

echo [3/4] Ensuring Database Indexes & Security Configs...
"venv\Scripts\python.exe" seed_rich_stock_history.py

echo.
echo [4/4] Starting Uvicorn High-Performance Server on http://0.0.0.0:7860 ...
echo [INFO] Health probe available at: http://localhost:7860/healthz
echo.

"venv\Scripts\python.exe" -m uvicorn app:app --host 0.0.0.0 --port 7860 --workers 1

pause
