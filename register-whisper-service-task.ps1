param(
    [string]$TaskName = "Whisper PTT Service"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartScript = Join-Path $ProjectRoot "start-whisper-service.ps1"

if (-not (Test-Path $StartScript)) {
    throw "Start script not found at $StartScript"
}

$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$StartScript`""
$Trigger = New-ScheduledTaskTrigger -AtLogOn

Register-ScheduledTask `
    -TaskName $TaskName `
    -Description "Start the local Whisper HTTP transcription service at logon." `
    -Action $Action `
    -Trigger $Trigger `
    -Force | Out-Null

Write-Host "Scheduled task created: $TaskName"
