$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    throw "Virtual environment not found. Run .\install-whisper-service.ps1 first."
}

$ExistingProcess = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -like "*service.py*" } |
    Select-Object -First 1

if ($ExistingProcess) {
    Write-Host "Whisper service is already running (PID $($ExistingProcess.ProcessId))."
    exit 0
}

Push-Location $ProjectRoot
try {
    $env:PYTHONUNBUFFERED = "1"
    & $VenvPython (Join-Path $ProjectRoot "service.py")
} finally {
    Pop-Location
}
