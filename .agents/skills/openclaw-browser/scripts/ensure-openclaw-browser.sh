#!/usr/bin/env bash
set -euo pipefail

OPENCLAW_BIN="${OPENCLAW_BIN:-/home/hod/.openclaw/bin/openclaw}"
BRIDGE_UNIT="${OPENCLAW_BROWSER_BRIDGE_UNIT:-openclaw-windows-browser.service}"
GATEWAY_UNIT="${OPENCLAW_GATEWAY_UNIT:-openclaw-gateway.service}"
WINDOWS_CHROME_PORT="${OPENCLAW_WINDOWS_CHROME_CDP_PORT:-18802}"
WINDOWS_RELAY_PORT="${OPENCLAW_WINDOWS_RELAY_PORT:-18812}"
WINDOWS_BROWSER_PROFILE="${OPENCLAW_WINDOWS_BROWSER_PROFILE:-winchrome}"
HEALTH_TIMEOUT="${OPENCLAW_HEALTH_TIMEOUT:-2}"
COMMAND_TIMEOUT="${OPENCLAW_COMMAND_TIMEOUT:-30}"
DOCTOR_TIMEOUT="${OPENCLAW_DOCTOR_TIMEOUT:-30}"
STARTUP_ATTEMPTS="${OPENCLAW_STARTUP_ATTEMPTS:-30}"
DOCTOR_ATTEMPTS="${OPENCLAW_DOCTOR_ATTEMPTS:-3}"
GATEWAY_PORT="${OPENCLAW_GATEWAY_PORT:-}"

if [[ -z "$GATEWAY_PORT" && -f "${HOME}/.openclaw/openclaw.json" ]] && command -v node >/dev/null 2>&1; then
  GATEWAY_PORT="$(node -e 'const fs = require("fs"); try { const cfg = JSON.parse(fs.readFileSync(`${process.env.HOME}/.openclaw/openclaw.json`, "utf8")); process.stdout.write(String(cfg.gateway?.port || 18789)); } catch { process.stdout.write("18789"); }' 2>/dev/null || true)"
fi
GATEWAY_PORT="${GATEWAY_PORT:-18789}"

# Browser policy:
# - Use a project-specific Chrome profile and CDP port for normal project work.
#   Multiple agents may run in parallel, so shared browser tabs/state should not
#   be used for automation, screenshots, or local previews.
# - Use the default/main OpenClaw profile only when login or account state is the
#   point of the task, or as a source for copying session state into the project
#   profile.

if [[ ! -x "$OPENCLAW_BIN" ]]; then
  echo "OpenClaw CLI not found or not executable: $OPENCLAW_BIN" >&2
  exit 1
fi

run_bounded() {
  local seconds="$1"
  shift

  if command -v timeout >/dev/null 2>&1; then
    timeout --kill-after=5s "$seconds" "$@"
  else
    "$@"
  fi
}

start_gateway_detached() {
  local log_dir="${HOME}/.openclaw/logs"
  local pid_file="${HOME}/.openclaw/gateway.pid"
  mkdir -p "$log_dir"

  if command -v setsid >/dev/null 2>&1; then
    setsid env PATH="$(dirname "$OPENCLAW_BIN"):${PATH}" "$OPENCLAW_BIN" gateway run --force --auth token \
      >"${log_dir}/gateway-run.log" 2>&1 < /dev/null &
  else
    nohup env PATH="$(dirname "$OPENCLAW_BIN"):${PATH}" "$OPENCLAW_BIN" gateway run --force --auth token \
      >"${log_dir}/gateway-run.log" 2>&1 < /dev/null &
  fi
  echo $! > "$pid_file"
}

gateway_reachable() {
  curl -fsS --max-time "$HEALTH_TIMEOUT" "http://127.0.0.1:${GATEWAY_PORT}/health" >/dev/null 2>&1
}

configure_remote_profile() {
  local relay_url="$1"
  command -v node >/dev/null 2>&1 || return 0

  node - "$relay_url" "$WINDOWS_BROWSER_PROFILE" <<'NODE' >/dev/null 2>&1 || true
const fs = require("fs");
const [relayUrl, profileName] = process.argv.slice(2);
const configPath = `${process.env.HOME}/.openclaw/openclaw.json`;
const cfg = fs.existsSync(configPath) ? JSON.parse(fs.readFileSync(configPath, "utf8")) : {};
cfg.browser = cfg.browser || {};
cfg.browser.defaultProfile = profileName;
cfg.browser.profiles = cfg.browser.profiles || {};
cfg.browser.profiles[profileName] = {
  ...(cfg.browser.profiles[profileName] || {}),
  driver: "openclaw",
  cdpUrl: relayUrl,
  attachOnly: true,
  color: "#1A73E8"
};
fs.writeFileSync(configPath, JSON.stringify(cfg, null, 2) + "\n");
NODE
}

start_windows_browser_bridge() {
  command -v powershell.exe >/dev/null 2>&1 || return 0
  command -v wslpath >/dev/null 2>&1 || return 0
  command -v node >/dev/null 2>&1 || return 0

  local win_host
  win_host="$(ip route 2>/dev/null | awk '/default/ {print $3; exit}')"
  [[ -n "$win_host" ]] || return 0

  local relay_url="http://${win_host}:${WINDOWS_RELAY_PORT}"
  if curl -fsS --max-time 2 "${relay_url}/json/version" >/dev/null 2>&1; then
    configure_remote_profile "$relay_url"
    return 0
  fi

  local script_dir="${HOME}/.openclaw/scripts"
  local chrome_script="${script_dir}/start-windows-chrome-cdp.ps1"
  local relay_script="${script_dir}/windows-cdp-relay.ps1"
  [[ -f "$chrome_script" && -f "$relay_script" ]] || return 0

  local win_temp win_temp_wsl staged_dir chrome_win relay_win
  win_temp="$(run_bounded "$COMMAND_TIMEOUT" cmd.exe /c 'echo %TEMP%' 2>/dev/null | tr -d '\r' || true)"
  [[ -n "$win_temp" ]] || return 0
  win_temp_wsl="$(wslpath "$win_temp" 2>/dev/null || true)"
  [[ -n "$win_temp_wsl" ]] || return 0
  staged_dir="${win_temp_wsl}/openclaw"
  mkdir -p "$staged_dir"
  cp "$chrome_script" "${staged_dir}/start-windows-chrome-cdp.ps1"
  cp "$relay_script" "${staged_dir}/windows-cdp-relay.ps1"
  chrome_win="$(wslpath -w "${staged_dir}/start-windows-chrome-cdp.ps1")"
  relay_win="$(wslpath -w "${staged_dir}/windows-cdp-relay.ps1")"

  run_bounded "$COMMAND_TIMEOUT" powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$chrome_win" \
    -Port "$WINDOWS_CHROME_PORT" -ProfileName "ChromeProfile" -Url "about:blank" >/dev/null 2>&1 || true

  if ! curl -fsS --max-time 2 "${relay_url}/json/version" >/dev/null 2>&1; then
    nohup powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$relay_win" \
      -ListenAddress "0.0.0.0" -ListenPort "$WINDOWS_RELAY_PORT" \
      -TargetAddress "127.0.0.1" -TargetPort "$WINDOWS_CHROME_PORT" \
      >"/tmp/openclaw-windows-relay-${WINDOWS_RELAY_PORT}.log" 2>&1 < /dev/null &
    for _ in $(seq 1 10); do
      curl -fsS --max-time 2 "${relay_url}/json/version" >/dev/null 2>&1 && break
      sleep 1
    done
  fi

  if ! curl -fsS --max-time 2 "${relay_url}/json/version" >/dev/null 2>&1; then
    echo "Warning: Windows Chrome CDP relay is not reachable at ${relay_url}" >&2
    tail -n 40 "/tmp/openclaw-windows-relay-${WINDOWS_RELAY_PORT}.log" >&2 2>/dev/null || true
  fi

  configure_remote_profile "$relay_url"
}

start_windows_browser_bridge

if command -v systemctl >/dev/null 2>&1; then
  run_bounded "$COMMAND_TIMEOUT" systemctl --user start "$BRIDGE_UNIT" "$GATEWAY_UNIT" >/dev/null 2>&1 || true
fi

if ! gateway_reachable; then
  start_gateway_detached
  for _ in $(seq 1 "$STARTUP_ATTEMPTS"); do
    gateway_reachable && break
    sleep 1
  done
fi

if ! gateway_reachable; then
  echo "OpenClaw gateway did not become healthy after ${STARTUP_ATTEMPTS} checks." >&2
  tail -n 80 "${HOME}/.openclaw/logs/gateway-run.log" >&2 2>/dev/null || true
  exit 1
fi

last_output=""
if last_output="$(run_bounded "$DOCTOR_TIMEOUT" "$OPENCLAW_BIN" browser doctor 2>&1)"; then
  printf '%s\n' "$last_output"
  exit 0
fi

run_bounded "$COMMAND_TIMEOUT" "$OPENCLAW_BIN" plugins registry --refresh >/dev/null 2>&1 || true
run_bounded "$COMMAND_TIMEOUT" "$OPENCLAW_BIN" browser start >/dev/null 2>&1 || true

for _ in $(seq 1 "$DOCTOR_ATTEMPTS"); do
  if last_output="$(run_bounded "$DOCTOR_TIMEOUT" "$OPENCLAW_BIN" browser doctor 2>&1)"; then
    printf '%s\n' "$last_output"
    exit 0
  fi
  sleep 1
done

printf '%s\n' "$last_output" >&2
if command -v systemctl >/dev/null 2>&1; then
  run_bounded "$COMMAND_TIMEOUT" systemctl --user --no-pager status "$BRIDGE_UNIT" "$GATEWAY_UNIT" >&2 || true
fi
exit 1
