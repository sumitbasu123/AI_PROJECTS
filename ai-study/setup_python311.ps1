$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPath = Join-Path $projectRoot ".venv311"

Push-Location $projectRoot
try {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw "Python Launcher not found. Install Python 3.11 from python.org with 'py launcher' enabled."
    }

    py -3.11 -m venv $venvPath
    $python = Join-Path $venvPath "Scripts\python.exe"
    & $python -m pip install --upgrade pip setuptools wheel
    & $python -m pip install -r requirements-paddle.txt

    Write-Host ""
    Write-Host "AI Study Python 3.11 environment is ready."
    Write-Host "Activate: .\.venv311\Scripts\Activate.ps1"
    Write-Host "Ingest:   python ingest.py --pdf-converter docling"
    Write-Host "Run app:  python -m streamlit run app.py"
}
finally {
    Pop-Location
}
