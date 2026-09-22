$ErrorActionPreference = "Stop"

# Per-user logon autostart that needs no administrator rights.
# Register-ScheduledTask is frequently access-denied on locked-down hosts, so
# this writes a hidden launcher into the current user's Startup folder instead.

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartScript = Join-Path $ProjectRoot "start-whisper-service.ps1"

if (-not (Test-Path $StartScript)) {
    throw "Start script not found at $StartScript"
}

$StartupDir = [Environment]::GetFolderPath("Startup")
$Launcher = Join-Path $StartupDir "WhisperPTT.vbs"

$inner = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""' + $StartScript + '""'
$vbs = 'Set sh = CreateObject("WScript.Shell")' + "`r`n" +
       'sh.Run "' + $inner + '", 0, False' + "`r`n"

Set-Content -Path $Launcher -Value $vbs -Encoding ASCII

Write-Host "Startup launcher created: $Launcher"
Write-Host "The service starts hidden at the next logon for the current user."
