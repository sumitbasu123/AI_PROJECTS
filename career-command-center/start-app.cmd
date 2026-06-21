@echo off
setlocal
set "APP_DIR=%~dp0"

where python >nul 2>&1
if errorlevel 1 (
  echo Python was not found on PATH. Install Python 3.11 or newer first.
  pause
  exit /b 1
)

python -c "import streamlit" >nul 2>&1
if errorlevel 1 (
  echo Installing the app requirements...
  python -m pip install -r "%APP_DIR%requirements.txt"
  if errorlevel 1 (
    echo Dependency installation failed.
    pause
    exit /b 1
  )
)

python -m streamlit run "%APP_DIR%app.py" --server.address 127.0.0.1 --server.port 8501
