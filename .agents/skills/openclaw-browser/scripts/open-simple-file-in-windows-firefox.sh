#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  open-simple-file-in-windows-firefox.sh <file>

Copies a simple local file into the Windows Downloads folder, then opens the
copied file directly in the user's default Windows browser (Firefox if installed,
otherwise the system default browser). This intentionally uses no HTTP server
and no OpenClaw/Chrome CDP bridge.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -ne 1 ]]; then
  usage >&2
  exit 2
fi

source_path="$1"
if [[ ! -f "$source_path" ]]; then
  echo "Not a regular file: $source_path" >&2
  exit 1
fi

source_abs="$(realpath "$source_path")"
downloads_win="$(
  powershell.exe -NoProfile -Command '[Console]::Out.Write((Join-Path $env:USERPROFILE "Downloads"))' \
    | tr -d '\r'
)"

if [[ -z "$downloads_win" ]]; then
  echo "Could not resolve Windows Downloads folder." >&2
  exit 1
fi

downloads_wsl="$(wslpath -u "$downloads_win")"
mkdir -p "$downloads_wsl"

base_name="$(basename "$source_abs")"
stem="${base_name%.*}"
extension=""
if [[ "$base_name" == *.* && "$stem" != "$base_name" ]]; then
  extension=".${base_name##*.}"
fi

dest_wsl="$downloads_wsl/$base_name"
if [[ "$source_abs" == "$(realpath -m "$dest_wsl")" ]]; then
  :
elif [[ -e "$dest_wsl" ]]; then
  stamp="$(date +%Y%m%d-%H%M%S)"
  dest_wsl="$downloads_wsl/${stem}-codex-${stamp}${extension}"
fi

if [[ "$source_abs" != "$(realpath -m "$dest_wsl")" ]]; then
  cp "$source_abs" "$dest_wsl"
fi
dest_win="$(wslpath -w "$dest_wsl")"

CODEX_OPEN_FILE_PATH="$dest_win" powershell.exe -NoProfile -Command '
  $target = $env:CODEX_OPEN_FILE_PATH
  if (-not $target -or -not (Test-Path $target)) {
    Write-Error "Target file does not exist: $target"
    exit 1
  }

  $firefox = $null
  foreach ($key in @(
    "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe",
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe"
  )) {
    try {
      $candidate = (Get-ItemProperty -Path $key -ErrorAction Stop)."(default)"
      if ($candidate -and (Test-Path $candidate)) {
        $firefox = $candidate
        break
      }
    } catch {}
  }

  if (-not $firefox) {
    foreach ($candidate in @(
      "$env:ProgramFiles\Mozilla Firefox\firefox.exe",
      "${env:ProgramFiles(x86)}\Mozilla Firefox\firefox.exe"
    )) {
      if ($candidate -and (Test-Path $candidate)) {
        $firefox = $candidate
        break
      }
    }
  }

  if ($firefox) {
    Start-Process -FilePath $firefox -ArgumentList @($target)
  } else {
    Start-Process $target
  }
'

echo "Copied to: $dest_win"
echo "Opened in Windows Firefox."
