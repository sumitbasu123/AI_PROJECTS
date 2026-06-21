@echo off
setlocal
for %%I in ("%~dp0..") do set "PROJECT_ROOT=%%~fI"
set "USERPROFILE=%PROJECT_ROOT%\.runtime"
set "VIBE_TRADING_PORTFOLIO_FILE=%PROJECT_ROOT%\portfolio_holdings.xlsx"
set "VIBE_TRADING_SKIP_PREFLIGHT=1"
if not exist "%USERPROFILE%" mkdir "%USERPROFILE%"

where python >nul 2>&1
if errorlevel 1 (
  echo Python was not found on PATH. Install Python 3.11 or newer first.
  exit /b 1
)

python "%PROJECT_ROOT%\agent\api_server.py" --host 127.0.0.1 --port 8000
