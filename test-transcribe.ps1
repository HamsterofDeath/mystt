param(
    [string]$AudioPath = (Join-Path $PSScriptRoot "sample.wav"),
    [string]$BaseUrl,
    [string]$Language = "de"
)

$ErrorActionPreference = "Stop"

function Get-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$Default = ""
    )

    $match = Select-String -Path $Path -Pattern "^$Name=(.*)$" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $match) {
        return $Default
    }

    return $match.Matches[0].Groups[1].Value.Trim()
}

function New-SilenceWav {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [int]$SampleRate = 16000,
        [int]$Seconds = 1
    )

    $numSamples = $SampleRate * $Seconds
    $dataBytes = $numSamples * 2
    $encoding = [System.Text.Encoding]::ASCII
    $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write)
    $writer = New-Object System.IO.BinaryWriter($stream)

    try {
        $writer.Write($encoding.GetBytes("RIFF"))
        $writer.Write([int](36 + $dataBytes))
        $writer.Write($encoding.GetBytes("WAVE"))
        $writer.Write($encoding.GetBytes("fmt "))
        $writer.Write([int]16)
        $writer.Write([int16]1)
        $writer.Write([int16]1)
        $writer.Write([int]$SampleRate)
        $writer.Write([int]($SampleRate * 2))
        $writer.Write([int16]2)
        $writer.Write([int16]16)
        $writer.Write($encoding.GetBytes("data"))
        $writer.Write([int]$dataBytes)

        for ($i = 0; $i -lt $numSamples; $i++) {
            $writer.Write([int16]0)
        }
    } finally {
        $writer.Dispose()
        $stream.Dispose()
    }
}

$EnvPath = Join-Path $PSScriptRoot ".env"
$Token = Get-DotEnvValue -Path $EnvPath -Name "PTT_TOKEN"
$Port = Get-DotEnvValue -Path $EnvPath -Name "SERVICE_PORT" -Default "8765"
$HostIp = Get-DotEnvValue -Path $EnvPath -Name "HOST_ACCESSIBLE_IP" -Default "192.168.56.1"

if (-not $BaseUrl) {
    $BaseUrl = "http://$HostIp`:$Port"
}

if (-not (Test-Path $AudioPath)) {
    New-SilenceWav -Path $AudioPath
}

& curl.exe -s -X POST "$BaseUrl/transcribe" `
    -H "X-PTT-Token: $Token" `
    -F "audio=@$AudioPath" `
    -F "language=$Language"
