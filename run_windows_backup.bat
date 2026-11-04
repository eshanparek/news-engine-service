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

:: Check Python installation
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.10 or 3.11 from python.org and tick "Add Python to PATH".
    pause
    exit /b 1
)

echo [2/4] Verifying Python Dependencies...
if not exist "venv" (
    echo Creating virtual environment in venv...
    python -m venv venv
)

call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet

echo.
echo [3/4] Ensuring Database Indexes & Security Configs...
python -c "import sqlite3; conn = sqlite3.connect('stock_news.db'); conn.execute('CREATE INDEX IF NOT EXISTS idx_stock_ticker ON stock_disclosures(ticker)'); conn.close(); print('Stock DB Ready.')"

echo.
echo [4/4] Starting Uvicorn High-Performance Server on http://0.0.0.0:7860 ...
echo [INFO] Health probe available at: http://localhost:7860/healthz
echo [INFO] Press CTRL+C to safely terminate the backup server.
echo.

uvicorn app:app --host 0.0.0.0 --port 7860 --workers 1

pause
