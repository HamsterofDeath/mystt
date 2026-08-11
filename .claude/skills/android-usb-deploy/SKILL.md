---
name: android-usb-deploy
description: Use when an Android phone is connected over USB or wireless debugging and you need to build, install, launch, capture, or inspect apps from this Linux/WSL workspace, OR whenever the user mentions a target phone by name/alias — including "S9", "S20", "S20 FE", "S23", "A52", or their model numbers (SM-G960F, SM-G780F, SM-S911x, SM-A528B). Phones with the adb_beacon app installed (A52, S20 FE) self-announce their IP:port; reconnect them with adb-autoconnect.sh instead of port scans or re-pairing. Use Windows adb.exe only for phone transport and keep devices awake.
---

# Android USB Deploy

Use this skill for Android phone work from this machine. Keep builds native on Linux, but use Windows `adb.exe` only for all device transport and device commands because phones are attached to Windows rather than WSL.

## Hard Rules

- Do not use Linux `adb` for phones. Do not run Linux `adb devices`, `adb kill-server`, `adb start-server`, `adb pair`, `adb connect`, `adb shell`, `adb install`, `adb logcat`, `adb screenrecord`, or any other Linux adb command.
- Use Windows `adb.exe` for device discovery, pairing, connect, install, launch, shell, logcat, screenrecord, pulls, and pushes.
- Default every deploy to the S23. If the S23 is not visible to Windows ADB, stop and report that instead of falling back to S9, S20, S20 FE, or any other connected device. Use a non-S23 target only when the user explicitly names that target in the current request.
- Keep connected phones active and awake. Never intentionally lock a phone, turn off its screen, reduce screen timeout, or disable stay-awake settings.
- Do not send sleep/lock commands such as `input keyevent POWER`, `KEYCODE_POWER`, `KEYCODE_SLEEP`, `svc power stayon false`, or settings that re-enable/shorten locking.
- When touching a phone, preserve or apply awake settings: high `screen_off_timeout`, `stay_on_while_plugged_in=7`, and high `lock_screen_lock_after_timeout`.
- If a secure lock cannot be disabled without the user's PIN, leave the device awake and report that Android requires the credential. Do not try to force it.
- Always deploy through a helper script, never ad-hoc one-off commands. If no helper covers the deploy you need (e.g. a release/non-debug build, a new product, a new option), create or extend one and commit it to the shared deploy scripts in the marketing repo so every product reuses it. See "Shared Deploy Helpers" below.

## Shared Deploy Helpers

Deploy helper scripts are shared across all product repos and live in the marketing repo, not in individual game repos:

- Directory: `/home/hod/IdeaProjects/marketing/scripts/deploy/`
- `android-deploy.sh` — single-device build → install → launch → verify for one product. Supports both `debug` and `release` (non-debug) builds, resolves Windows adb and phone aliases (`s23`, `s20`, `s20fe`, `a52`, `s9`), stages the APK for Windows adb, keeps the phone awake, and verifies foreground. A `release` build requires the target repo's upload keystore to be present.
- `adb-autoconnect.sh <selector>` — reconnects phones whose wireless-debugging port changed (it changes on every toggle/reboot and pairing can drop). Uses the phone-side **adb_beacon** app (repo `/home/hod/IdeaProjects/adb_beacon`, package `de.dhaup.adbbeacon`): the app broadcasts its current IP + adbd port(s) via UDP 47110 every ~25 s. The script reads the beacon registry when fresh, otherwise does a one-shot capture of the next broadcast (`phone-beacon-capture.ps1`), then runs Windows `adb connect` on the candidate ports newest-first. No daemon needed; prefer this over port scans.
- `phone-beacon-listener.ps1` / `phone-beacon-kill.ps1` — optional persistent registry listener and its cleanup. Run the listener only in WSL-wrapper mode (plain `powershell.exe -File` from bash); a `Start-Process`-spawned hidden instance receives nothing. Never kill the wrapper with TaskStop/kill from WSL — the Windows child survives and holds UDP 47110; always use `phone-beacon-kill.ps1`. When counting listener processes, subtract the counting process itself (its own CommandLine matches the pattern).

```bash
/home/hod/IdeaProjects/marketing/scripts/deploy/android-deploy.sh \
  --repo /home/hod/IdeaProjects/drop_the_ball \
  --package de.dhaup.droptheball \
  --build release \
  --phone s9 \
  --activity de.dhaup.droptheball/.MainActivity
```

Rules for these helpers:

- Every phone deploy must go through a helper script here (or a repo-local script that this skill already documents, such as screwdriver's `scripts/default-deploy.sh`). Do not paste ad-hoc build/install/launch command chains as the deploy path.
- When you find yourself running deploy steps by hand, capture them by improving `android-deploy.sh` (or adding a sibling script) in the marketing repo, then run through it. Update the shared script itself rather than forking per-repo copies.
- Keep the transport rule intact: builds run natively on Linux, all device commands use Windows `adb.exe`.

## Known Local Setup

- Phones connect over wireless debugging from the home subnet `192.168.178.*` (e.g. `192.168.178.102`). The pairing port shown in Wireless debugging differs from the connect port; after pairing, find the open adbd port with a TCP scan (`for p in $(seq 30000 65535); do (echo > /dev/tcp/<ip>/$p) >/dev/null 2>&1 && echo open:$p; done`) and `adb connect <ip>:<port>`.
- Linux JDK: `/usr/bin/java`
- Linux sdkmanager: `/usr/bin/sdkmanager`
- Android SDK root: `/home/hod/Android/Sdk`
- Windows adb, first-choice phone transport:
  - `adb.exe` when it is on PATH
  - `/mnt/c/Users/dhaup/AppData/Local/Android/platform-tools/adb.exe` when PATH lookup fails
- Common repos:
  - `/home/hod/IdeaProjects/battle_of_chchritz`
  - `/home/hod/IdeaProjects/screwdriver_2026`
  - `/home/hod/IdeaProjects/roguerocketriot`
- All Android games deploy helper: `/home/hod/IdeaProjects/deploy-all-android-games.sh`

## Transport Preflight

Run this before every phone deploy or phone command. Use the resulting `$WIN_ADB` for all device work:

```bash
WIN_ADB="$(command -v adb.exe || true)"
if [ -z "$WIN_ADB" ] && [ -x /mnt/c/Users/dhaup/AppData/Local/Android/platform-tools/adb.exe ]; then
  WIN_ADB=/mnt/c/Users/dhaup/AppData/Local/Android/platform-tools/adb.exe
fi
if [ -z "$WIN_ADB" ] && command -v cmd.exe >/dev/null 2>&1; then
  WIN_ADB_WIN="$(cmd.exe /C where adb 2>/dev/null | tr -d '\r' | sed -n '1p')"
  [ -n "$WIN_ADB_WIN" ] && WIN_ADB="$(wslpath -u "$WIN_ADB_WIN" 2>/dev/null || true)"
fi

if [ -z "$WIN_ADB" ]; then
  echo "Windows adb not found; stop and ask the user to restore Windows adb."
  exit 1
fi
"$WIN_ADB" devices -l
```

Use that same `$WIN_ADB` for install, launch, `logcat`, `dumpsys`, `screenrecord`, pairing, and all shell commands.

## All Games Deploy Flow

When the user asks to deploy all local Android games/prototypes, use the parent-directory helper. It takes exactly one parameter: the phone selector.

```bash
cd /home/hod/IdeaProjects
./deploy-all-android-games.sh s23
```

The phone selector may be a full adb serial, serial prefix, model such as `SM_S918B`, or a friendly alias such as `s23`, `s20`, `s20fe`, or `s9`. Do not add extra script parameters; update the helper itself if the game list or behavior must change.

The helper builds, installs, launches, and verifies each native Android game checkout. It intentionally excludes utility apps such as Meal Calculator. It already resolves and uses Windows `adb.exe`, stages APKs for Windows adb transport, keeps the target phone awake, and verifies foreground focus after each launch.

## Full Deploy Flow

For `/home/hod/IdeaProjects/screwdriver_2026`, use the repository script by default:

```bash
cd /home/hod/IdeaProjects/screwdriver_2026
scripts/default-deploy.sh
```

That script runs `:app:predeployCheck` and `:app:assembleDebug` on Linux, installs `app-debug.apk`, launches `de.dhaup.screwdriver2026/.app.MainActivity`, and verifies the app reached the foreground. Before trusting the script's transport behavior, run the Transport Preflight above so missing PATH entries for `adb.exe` do not hide the Windows adb installation.

Use the script options when appropriate:

```bash
scripts/default-deploy.sh --dry-run
scripts/default-deploy.sh --skip-check
```

## Manual Flow

Use this only when the deploy script is missing or unsuitable.

1. Run the Transport Preflight and keep `$WIN_ADB` for all phone commands:

```bash
"$WIN_ADB" devices -l
```

2. Build and run the checked gate natively on Linux:

```bash
./gradlew -Dscrewdriver.predeployCheckTimeoutSeconds=300 :app:predeployCheck :app:assembleDebug --console=plain
```

3. Install the debug APK through Windows adb:

```bash
"$WIN_ADB" install -r "$(wslpath -w app/build/outputs/apk/debug/app-debug.apk)"
```

4. Launch the app and inspect the foreground state:

```bash
"$WIN_ADB" shell am start -S -n de.dhaup.screwdriver2026/de.dhaup.screwdriver2026.app.MainActivity
"$WIN_ADB" shell dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'
```

5. Keep the device awake when appropriate, without waking it if the user specifically says not to:

```bash
"$WIN_ADB" shell settings put system screen_off_timeout 2147483647
"$WIN_ADB" shell settings put global stay_on_while_plugged_in 7
"$WIN_ADB" shell settings put secure lock_screen_lock_after_timeout 2147483647 || true
"$WIN_ADB" shell settings put secure lockscreen.disabled 1 || true
"$WIN_ADB" shell settings put secure lock_screen_locking_enabled 0 || true
"$WIN_ADB" shell svc power stayon true || true
```

## SDK Rules

- Keep `local.properties` pointed at `/home/hod/Android/Sdk`.
- If the repo needs platform or build tools, install them into that Linux SDK root with `sdkmanager`.
- If `sdkmanager` asks for licenses, accept them once in the Linux SDK root and reuse that state.
- Do not switch the repo back to a root-owned SDK path just because a system package exists.

## Transport Rule

For all phone work, use Windows adb only with the Transport Preflight. Keep Gradle, tests, and build work on Linux. If Windows adb is unavailable or cannot see the device, stop and ask for repair information rather than using Linux adb.
