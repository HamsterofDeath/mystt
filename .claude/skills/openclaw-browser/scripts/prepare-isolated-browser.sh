#!/usr/bin/env bash
# Provision an isolated, PERSISTENT OpenClaw Chrome profile for a single agent.
#
# What it does:
#   1. (optional) Clones a master Windows Chrome profile dir into a per-agent copy
#      so the agent inherits SETTINGS / extensions / bookmarks.
#   2. Launches Windows Chrome on that dir with its own --remote-debugging-port.
#   3. Starts a Windows-side CDP relay so WSL can reach that loopback port.
#   4. Registers the profile in ~/.openclaw/openclaw.json so the agent can drive
#      it with:  openclaw browser --browser-profile <name> <cmd>
#
# Each agent gets its own profile dir + port + tab set => zero interference with
# the shared browser or with other agents. Because Chrome locks a user-data-dir,
# every concurrent instance MUST use a distinct --name and --port.
#
# LOGIN (verified 2026-07-01): a profile-dir copy does NOT carry a Google login.
# Chrome's App-Bound Encryption makes the copied cookie DB undecryptable, and
# Google's device-bound sessions (DBSC) won't authenticate copied cookies anyway.
# The reliable pattern is PERSISTENCE: this profile dir survives restarts, so sign
# in ONCE interactively in the launched window and the session stays put across
# runs (long-lived + auto-refreshed) -- no re-login "every time", only the first.
# Cookie top-up (sync-openclaw-session.sh) restores non-Google logins and pre-fills
# the Google account chooser, but cannot deliver a working Google session.
#
# Usage:
#   prepare-isolated-browser.sh --name agent1 --port 18822 [--url URL] [--fresh]
#
# Options:
#   --name <id>     Agent id. Chrome dir = ChromeProfile-<id>; openclaw profile = <id>.
#   --port <n>      Chrome remote-debugging port (default 18822). Relay port = port+10.
#   --relay-port n  Override relay port (default port+10).
#   --url <url>     Initial tab URL (default about:blank).
#   --source <name> Master profile dir under %LOCALAPPDATA%\OpenClaw to clone
#                   (default ChromeProfile — the shared logged-in OpenClaw profile).
#   --fresh         Delete an existing clone first (re-inherit the master's latest session).
#   --no-clone      Skip cloning (reuse/create an empty dir — agent starts logged out).
#   --color <hex>   Profile color in openclaw config (default derived from name).
#   -h | --help
#
# Env knobs (same spirit as ensure-openclaw-browser.sh):
#   OPENCLAW_BIN (default /home/hod/.openclaw/bin/openclaw)
#   OPENCLAW_COMMAND_TIMEOUT (default 60), OPENCLAW_DOCTOR_TIMEOUT (default 30)
set -euo pipefail

OPENCLAW_BIN="${OPENCLAW_BIN:-/home/hod/.openclaw/bin/openclaw}"
COMMAND_TIMEOUT="${OPENCLAW_COMMAND_TIMEOUT:-60}"
DOCTOR_TIMEOUT="${OPENCLAW_DOCTOR_TIMEOUT:-30}"

NAME=""
PORT="18822"
RELAY_PORT=""
URL="about:blank"
SOURCE="ChromeProfile"
FRESH="0"
CLONE="1"
COLOR=""

die() { echo "error: $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name) NAME="${2:-}"; shift 2 ;;
    --port) PORT="${2:-}"; shift 2 ;;
    --relay-port) RELAY_PORT="${2:-}"; shift 2 ;;
    --url) URL="${2:-}"; shift 2 ;;
    --source) SOURCE="${2:-}"; shift 2 ;;
    --fresh) FRESH="1"; shift ;;
    --no-clone) CLONE="0"; shift ;;
    --color) COLOR="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

[[ -n "$NAME" ]] || die "--name is required (e.g. --name agent1)"
[[ "$NAME" =~ ^[A-Za-z0-9._-]+$ ]] || die "--name must be [A-Za-z0-9._-]"
[[ "$PORT" =~ ^[0-9]+$ ]] || die "--port must be numeric"
[[ -n "$RELAY_PORT" ]] || RELAY_PORT="$((PORT + 10))"
[[ "$RELAY_PORT" != "$PORT" ]] || die "relay port must differ from chrome port"
[[ -x "$OPENCLAW_BIN" ]] || die "OpenClaw CLI not found/executable: $OPENCLAW_BIN"

for req in powershell.exe wslpath curl node; do
  command -v "$req" >/dev/null 2>&1 || die "required tool missing: $req"
done

PROFILE_DIR_NAME="ChromeProfile-${NAME}"

run_bounded() {
  local seconds="$1"; shift
  if command -v timeout >/dev/null 2>&1; then
    timeout --kill-after=5s "$seconds" "$@"
  else
    "$@"
  fi
}

# WSL-facing Windows host IP (default-route gateway), same detection as ensure-*.sh.
WIN_HOST="$(ip route 2>/dev/null | awk '/default/ {print $3; exit}')"
[[ -n "$WIN_HOST" ]] || die "could not determine Windows host IP from default route"
RELAY_URL="http://${WIN_HOST}:${RELAY_PORT}"

# --- 1. Clone the logged-in master profile into a per-agent copy -----------------
if [[ "$CLONE" == "1" ]]; then
  echo "[1/4] cloning %LOCALAPPDATA%\\OpenClaw\\${SOURCE} -> ${PROFILE_DIR_NAME} (carries session)"
  run_bounded "$COMMAND_TIMEOUT" powershell.exe -NoProfile -Command "
    \$root = Join-Path \$env:LOCALAPPDATA 'OpenClaw'
    \$src  = Join-Path \$root '${SOURCE}'
    \$dst  = Join-Path \$root '${PROFILE_DIR_NAME}'
    if (-not (Test-Path \$src)) { Write-Error \"source profile not found: \$src\"; exit 2 }
    if ('${FRESH}' -eq '1' -and (Test-Path \$dst)) { Remove-Item \$dst -Recurse -Force }
    New-Item -ItemType Directory -Force \$dst | Out-Null
    # /E all subdirs, /R:1 /W:1 minimal retry on locked files (Chrome may hold Cookies),
    # skip caches and single-instance lock files so the copy is launchable.
    robocopy \$src \$dst /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP /XD 'Crash Reports' 'ShaderCache' 'GrShaderCache' 'GraphiteDawnCache' /XF 'Singleton*' 'LOCK' 'lockfile' | Out-Null
    # robocopy exit codes are a bitmask: 0-7 = success, 8+ = some files could not be
    # copied (normal when the live master Chrome holds locks on a few files), 16 = fatal.
    \$rc = \$LASTEXITCODE
    if (\$rc -ge 16) { Write-Error \"robocopy fatal (\$rc)\"; exit 3 }
    if (\$rc -ge 8)  { Write-Warning \"robocopy skipped some locked files (\$rc); session may still be intact\" }
    exit 0
  " 2>&1 || die "profile clone failed (is the --source name correct?)"
else
  echo "[1/4] --no-clone: agent will use a fresh/empty ${PROFILE_DIR_NAME} (logged out)"
fi

# --- 2 & 3. Launch Chrome on the clone + start the WSL relay ---------------------
# Stage the vetted helper scripts into a Windows-local temp dir (running .ps1 from
# a \\wsl path via -File is unreliable), mirroring ensure-openclaw-browser.sh.
SCRIPT_DIR="${HOME}/.openclaw/scripts"
CHROME_PS1="${SCRIPT_DIR}/start-windows-chrome-cdp.ps1"
RELAY_PS1="${SCRIPT_DIR}/windows-cdp-relay.ps1"
[[ -f "$CHROME_PS1" && -f "$RELAY_PS1" ]] || die "helper ps1 scripts missing under $SCRIPT_DIR"

WIN_TEMP="$(run_bounded "$COMMAND_TIMEOUT" cmd.exe /c 'echo %TEMP%' 2>/dev/null | tr -d '\r')"
[[ -n "$WIN_TEMP" ]] || die "could not resolve Windows %TEMP%"
STAGE_WSL="$(wslpath "$WIN_TEMP")/openclaw"
mkdir -p "$STAGE_WSL"
cp "$CHROME_PS1" "$STAGE_WSL/start-windows-chrome-cdp.ps1"
cp "$RELAY_PS1"  "$STAGE_WSL/windows-cdp-relay.ps1"
CHROME_WIN="$(wslpath -w "$STAGE_WSL/start-windows-chrome-cdp.ps1")"
RELAY_WIN="$(wslpath -w "$STAGE_WSL/windows-cdp-relay.ps1")"

echo "[2/4] launching Windows Chrome (profile ${PROFILE_DIR_NAME}, cdp port ${PORT})"
run_bounded "$COMMAND_TIMEOUT" powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$CHROME_WIN" \
  -Port "$PORT" -ProfileName "$PROFILE_DIR_NAME" -Url "$URL" >/dev/null 2>&1 \
  || die "chrome launch failed"

echo "[3/4] starting WSL relay ${RELAY_URL} -> 127.0.0.1:${PORT}"
if ! curl -fsS --max-time 2 "${RELAY_URL}/json/version" >/dev/null 2>&1; then
  nohup powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$RELAY_WIN" \
    -ListenAddress "0.0.0.0" -ListenPort "$RELAY_PORT" \
    -TargetAddress "127.0.0.1" -TargetPort "$PORT" \
    >"/tmp/openclaw-isolated-relay-${RELAY_PORT}.log" 2>&1 < /dev/null &
  for _ in $(seq 1 15); do
    curl -fsS --max-time 2 "${RELAY_URL}/json/version" >/dev/null 2>&1 && break
    sleep 1
  done
fi
curl -fsS --max-time 3 "${RELAY_URL}/json/version" >/dev/null 2>&1 \
  || die "relay not reachable at ${RELAY_URL} (see /tmp/openclaw-isolated-relay-${RELAY_PORT}.log)"

# --- 4. Register the profile in openclaw.json ------------------------------------
[[ -n "$COLOR" ]] || COLOR="#$(printf '%s' "$NAME" | cksum | awk '{printf "%06X", $1 % 16777216}')"
echo "[4/4] registering openclaw profile '${NAME}' -> ${RELAY_URL}"
node - "$NAME" "$RELAY_URL" "$COLOR" <<'NODE'
const fs = require("fs");
const [name, cdpUrl, color] = process.argv.slice(2);
const p = `${process.env.HOME}/.openclaw/openclaw.json`;
const cfg = fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, "utf8")) : {};
cfg.browser = cfg.browser || {};
cfg.browser.profiles = cfg.browser.profiles || {};
cfg.browser.profiles[name] = {
  ...(cfg.browser.profiles[name] || {}),
  driver: "openclaw",
  cdpUrl,
  attachOnly: true,   // never kill this Chrome from the CLI
  color,
};
fs.writeFileSync(p, JSON.stringify(cfg, null, 2) + "\n");
NODE

# --- Verify (without dumping cookie values) --------------------------------------
echo
echo "ready. drive it with:  ${OPENCLAW_BIN} browser --browser-profile ${NAME} <cmd>"
TABS="$(run_bounded "$DOCTOR_TIMEOUT" "$OPENCLAW_BIN" browser --browser-profile "$NAME" tabs 2>&1 | grep -c 'use: t' || true)"
echo "profile '${NAME}': ${TABS} tab(s) visible, cdp ${RELAY_URL}"
echo
echo "LOGIN: this profile starts logged OUT of Google (copy can't carry the session)."
echo "Sign in ONCE in the launched Chrome window; the login then persists across runs."
echo "For non-Google sites you can top up cookies from the shared profile without re-login:"
echo "  $(dirname "$0")/sync-openclaw-session.sh --from winchrome --to ${NAME} --domains 'itch.io'"
