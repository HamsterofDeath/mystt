#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: open_in_firefox.sh [--copy-only] <local-file-or-url>

Copies local files to the Windows Startup folder, then opens the copied file in
Windows Firefox. URLs are opened directly in Firefox and are not copied.
EOF
}

copy_only=0
if [[ "${1:-}" == "--copy-only" ]]; then
  copy_only=1
  shift
fi

if [[ $# -ne 1 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 2
fi

target="$1"
ps_dir="/mnt/c/Windows/System32"

run_powershell() {
  local command="$1"
  if [[ -d "$ps_dir" ]]; then
    (cd "$ps_dir" && powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$command") | tr -d '\r'
  else
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$command" | tr -d '\r'
  fi
}

ps_single_quote() {
  printf "%s" "$1" | sed "s/'/''/g"
}

windows_firefox_path() {
  run_powershell '
    $candidates = @(
      "$env:ProgramFiles\Mozilla Firefox\firefox.exe",
      "${env:ProgramFiles(x86)}\Mozilla Firefox\firefox.exe",
      "$env:LocalAppData\Mozilla Firefox\firefox.exe"
    )
    $found = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if ($found) {
      $found
    } else {
      $cmd = Get-Command firefox.exe -ErrorAction SilentlyContinue
      if ($cmd) { $cmd.Source }
    }
  ' | sed -n '1p'
}

open_firefox() {
  local firefox_win="$1"
  local open_target="$2"
  local firefox_ps target_ps
  firefox_ps="$(ps_single_quote "$firefox_win")"
  target_ps="$(ps_single_quote "$open_target")"
  run_powershell "\$firefox = '$firefox_ps'; \$target = '$target_ps'; \$escapedTarget = \$target.Replace('\"', '\\\"'); \$psi = New-Object System.Diagnostics.ProcessStartInfo; \$psi.FileName = \$firefox; \$psi.UseShellExecute = \$false; \$psi.Arguments = '\"' + \$escapedTarget + '\"'; [void][System.Diagnostics.Process]::Start(\$psi)" >/dev/null
}

is_url=0
case "$target" in
  http://*|https://*) is_url=1 ;;
esac

firefox_win="$(windows_firefox_path)"
if [[ -z "$firefox_win" ]]; then
  echo "Firefox executable not found in standard Windows locations or PATH." >&2
  exit 1
fi

echo "Firefox: $firefox_win"

if [[ "$is_url" -eq 1 ]]; then
  if [[ "$copy_only" -eq 1 ]]; then
    echo "--copy-only cannot be used with URLs because URLs are not copied." >&2
    exit 2
  fi
  open_firefox "$firefox_win" "$target"
  echo "Opened URL: $target"
  exit 0
fi

if [[ ! -e "$target" ]]; then
  echo "File does not exist: $target" >&2
  exit 1
fi

source_abs="$(realpath "$target")"
startup_win="$(run_powershell "[Environment]::GetFolderPath('Startup')" | sed -n '1p')"
if [[ -z "$startup_win" ]]; then
  echo "Could not resolve the Windows Startup folder." >&2
  exit 1
fi

startup_wsl="$(wslpath -u "$startup_win")"
mkdir -p "$startup_wsl"

base_name="$(basename "$source_abs")"
safe_base="$(printf "%s" "$base_name" | tr -c 'A-Za-z0-9._-' '_')"
if [[ -z "$safe_base" || "$safe_base" == "_" ]]; then
  safe_base="file"
fi

copy_wsl="$startup_wsl/codex-firefox-$safe_base"
if [[ "$source_abs" != "$copy_wsl" ]]; then
  cp -f "$source_abs" "$copy_wsl"
fi

copy_win="$(wslpath -w "$copy_wsl")"

echo "Source: $source_abs"
echo "Windows Startup folder: $startup_win"
echo "Windows copy: $copy_win"

if [[ "$copy_only" -eq 1 ]]; then
  echo "Copy-only mode: Firefox was not opened."
  exit 0
fi

open_firefox "$firefox_win" "$copy_win"
echo "Opened in Firefox: $copy_win"
