$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    throw "Virtual environment not found. Run .\install-whisper-service.ps1 first."
}

Push-Location $ProjectRoot
try {
    $env:PYTHONUNBUFFERED = "1"
    & $VenvPython (Join-Path $ProjectRoot "service.py")
} finally {
    Pop-Location
}

