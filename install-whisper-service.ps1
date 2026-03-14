param(
    [switch]$SkipFirewallRule,
    [switch]$PreloadMedium
)

$ErrorActionPreference = "Stop"

function Get-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$Default = ""
    )

    if (-not (Test-Path $Path)) {
        return $Default
    }

    $match = Select-String -Path $Path -Pattern "^$Name=(.*)$" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $match) {
        return $Default
    }

    return $match.Matches[0].Groups[1].Value.Trim()
}

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvPath = Join-Path $ProjectRoot ".env"
$PythonExe = "C:\Users\dhaup\AppData\Local\Programs\Python\Python313\python.exe"
$VenvPath = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
$Port = Get-DotEnvValue -Path $EnvPath -Name "SERVICE_PORT" -Default "8765"
$RuleName = "Whisper PTT HTTP Service ($Port)"

if (-not (Test-Path $PythonExe)) {
    throw "Python not found at $PythonExe"
}

if (-not (Test-Path $VenvPython)) {
    & $PythonExe -m venv $VenvPath
}

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
& $VenvPython -c "import service; service.preload_from_env()"

if ($PreloadMedium) {
    $env:WHISPER_MODEL = "medium"
    & $VenvPython -c "import service; service.preload_from_env()"
    Remove-Item Env:WHISPER_MODEL
}

if (-not $SkipFirewallRule) {
    try {
        if (-not (Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue)) {
            New-NetFirewallRule -DisplayName $RuleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port | Out-Null
        }
        Write-Host "Firewall rule ready: $RuleName"
    } catch {
        Write-Warning "Firewall rule could not be created automatically. Re-run this script as Administrator if the VM cannot reach the service."
    }
}

Write-Host ""
Write-Host "Installation complete."
Write-Host "Start with:"
Write-Host "  .\\start-whisper-service.ps1"
