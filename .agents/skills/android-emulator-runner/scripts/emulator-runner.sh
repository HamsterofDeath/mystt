#!/usr/bin/env bash
set -euo pipefail

SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-/home/hod/Android/Sdk}}"
USER_ADB_SET=false
if [[ -n "${ADB:-}" ]]; then
    USER_ADB_SET=true
fi
ADB="${ADB:-}"
EMULATOR="${EMULATOR:-$SDK_ROOT/emulator/emulator}"
AVD="${AVD:-rrr_api36}"
SERIAL="${SERIAL:-emulator-5554}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-180}"
LOG_FILE="${LOG_FILE:-/tmp/android-emulator-runner-$AVD.log}"
PID_FILE="${PID_FILE:-/tmp/android-emulator-runner-$AVD.pid}"
HEADLESS=true
READ_ONLY=true
VERBOSE=false
WIPE_DATA=false

select_adb() {
    if [[ -x "$SDK_ROOT/platform-tools/adb" ]]; then
        ADB="$SDK_ROOT/platform-tools/adb"
    else
        ADB="adb"
    fi
}

if [[ "$USER_ADB_SET" == false ]]; then
    select_adb
fi

usage() {
    cat <<'EOF'
Usage: emulator-runner.sh <command> [options]

Commands:
  list                  List AVDs and adb devices.
  start                 Start the AVD and wait for sys.boot_completed=1.
  wait                  Wait for an already-started emulator to boot.
  screenshot --out P    Capture a PNG screenshot.
  record --out P        Record an MP4 from the emulator.
  stop                  Kill the emulator via adb emu kill.

Options:
  --avd NAME            AVD name. Default: rrr_api36.
  --serial SERIAL       Emulator serial. Default: emulator-5554.
  --sdk-root PATH       Android SDK root. Default: /home/hod/Android/Sdk.
  --timeout SECONDS     Boot wait timeout. Default: 180.
  --log PATH            Emulator launch log path.
  --visible             Launch with a visible window.
  --no-read-only        Do not pass -read-only.
  --verbose             Pass -verbose to emulator.
  --wipe-data           Pass -wipe-data.
  --duration SECONDS    screenrecord duration. Default: 30.
EOF
}

command="${1:-}"
if [[ -z "$command" || "$command" == "-h" || "$command" == "--help" ]]; then
    usage
    exit 0
fi
shift || true

out=""
duration=30
while [[ $# -gt 0 ]]; do
    case "$1" in
        --avd) AVD="$2"; shift 2 ;;
        --serial) SERIAL="$2"; shift 2 ;;
        --sdk-root)
            SDK_ROOT="$2"
            EMULATOR="$SDK_ROOT/emulator/emulator"
            [[ "$USER_ADB_SET" == false ]] && select_adb
            shift 2
            ;;
        --timeout) TIMEOUT_SECONDS="$2"; shift 2 ;;
        --log) LOG_FILE="$2"; shift 2 ;;
        --visible) HEADLESS=false; shift ;;
        --no-read-only) READ_ONLY=false; shift ;;
        --verbose) VERBOSE=true; shift ;;
        --wipe-data) WIPE_DATA=true; shift ;;
        --out) out="$2"; shift 2 ;;
        --duration) duration="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

ensure_tools() {
    command -v "$ADB" >/dev/null || { echo "adb not found: $ADB" >&2; exit 1; }
    [[ -x "$EMULATOR" ]] || { echo "emulator not executable: $EMULATOR" >&2; exit 1; }
}

device_seen() {
    "$ADB" devices | awk -v serial="$SERIAL" '$1 == serial && $2 == "device" { found = 1 } END { exit found ? 0 : 1 }'
}

boot_completed() {
    [[ "$("$ADB" -s "$SERIAL" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == "1" ]]
}

wait_boot() {
    local deadline=$((SECONDS + TIMEOUT_SECONDS))
    while (( SECONDS < deadline )); do
        if device_seen && boot_completed; then
            "$ADB" -s "$SERIAL" shell input keyevent 82 >/dev/null 2>&1 || true
            echo "Emulator ready: $SERIAL"
            return 0
        fi
        sleep 2
    done
    echo "Timed out waiting for $SERIAL. Devices:" >&2
    "$ADB" devices -l >&2 || true
    echo "Emulator log tail ($LOG_FILE):" >&2
    tail -80 "$LOG_FILE" >&2 || true
    return 1
}

start_emulator() {
    ensure_tools
    if device_seen && boot_completed; then
        echo "Emulator already ready: $SERIAL"
        return 0
    fi

    mkdir -p "$(dirname "$LOG_FILE")"
    : > "$LOG_FILE"
    local flags=(-avd "$AVD" -gpu swiftshader_indirect -no-audio -no-boot-anim -no-snapshot-load)
    [[ "$HEADLESS" == true ]] && flags=(-no-window "${flags[@]}")
    [[ "$READ_ONLY" == true ]] && flags+=(-read-only)
    [[ "$VERBOSE" == true ]] && flags=(-verbose "${flags[@]}")
    [[ "$WIPE_DATA" == true ]] && flags+=(-wipe-data)

    echo "Starting emulator: $EMULATOR ${flags[*]}"
    nohup "$EMULATOR" "${flags[@]}" >>"$LOG_FILE" 2>&1 &
    echo "$!" > "$PID_FILE"
    wait_boot
}

case "$command" in
    list)
        ensure_tools
        "$EMULATOR" -list-avds || true
        "$ADB" devices -l || true
        ;;
    start)
        start_emulator
        ;;
    wait)
        wait_boot
        ;;
    screenshot)
        [[ -n "$out" ]] || { echo "--out is required for screenshot" >&2; exit 2; }
        mkdir -p "$(dirname "$out")"
        "$ADB" -s "$SERIAL" exec-out screencap -p > "$out"
        echo "$out"
        ;;
    record)
        [[ -n "$out" ]] || { echo "--out is required for record" >&2; exit 2; }
        mkdir -p "$(dirname "$out")"
        remote="/sdcard/$(basename "$out")"
        "$ADB" -s "$SERIAL" shell rm -f "$remote" >/dev/null 2>&1 || true
        "$ADB" -s "$SERIAL" shell screenrecord --time-limit "$duration" "$remote"
        "$ADB" -s "$SERIAL" pull "$remote" "$out" >/dev/null
        echo "$out"
        ;;
    stop)
        "$ADB" -s "$SERIAL" emu kill || true
        ;;
    *)
        echo "Unknown command: $command" >&2
        usage >&2
        exit 2
        ;;
esac
