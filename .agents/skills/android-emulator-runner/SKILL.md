---
name: android-emulator-runner
description: Reliable Android emulator launch, boot waiting, APK install, app launch, screenshot/video capture, log collection, and teardown workflows from Linux or WSL. Use when Codex needs to start an AVD, recover from emulator launch failures, run headless or visible emulator smoke tests, prove an Android game/app interaction on an emulator, or create and maintain emulator automation scripts.
---

# Android Emulator Runner

## Overview

Use this skill for Android emulator runtime checks from Linux/WSL. Prefer deterministic scripts over one-off emulator commands, because launch behavior depends on AVD config, graphics backend, boot state, and first-run system/app overlays.

## Quick Flow

1. Inspect before starting:

```bash
adb devices -l || true
/home/hod/Android/Sdk/emulator/emulator -list-avds
/home/hod/Android/Sdk/emulator/emulator -accel-check
pgrep -af 'emulator|qemu-system' || true
```

2. Start and wait with the bundled helper:

```bash
~/.codex/skills/android-emulator-runner/scripts/emulator-runner.sh start --avd rrr_api36
```

3. Build/install/launch the app from the repository, then capture evidence:

```bash
./gradlew :app:assembleDebug --console=plain
adb -s emulator-5554 install -r app/build/outputs/apk/debug/app-debug.apk
adb -s emulator-5554 shell am start -S -n package.name/package.name.MainActivity
~/.codex/skills/android-emulator-runner/scripts/emulator-runner.sh screenshot --out artifacts/emulator/current.png
```

4. Stop the emulator when the user does not need it visible:

```bash
~/.codex/skills/android-emulator-runner/scripts/emulator-runner.sh stop
```

## Reliable Launch Rules

- Use the local SDK at `/home/hod/Android/Sdk` unless the repo has a stricter local rule.
- Prefer Linux `adb` for emulator work. Reserve `adb.exe` for Windows-attached physical phones.
- Prefer headless startup for repeatable smoke tests: `-no-window -gpu swiftshader_indirect -no-audio -no-boot-anim -no-snapshot-load -read-only`.
- If a background launch exits before ADB sees it, retry with `-verbose` and keep the process attached long enough to inspect output. Look for `control console listening on port 5554, ADB on port 5555`.
- Wait for both ADB device state and `sys.boot_completed=1` before installing or launching.
- Capture screenshots with `adb exec-out screencap -p`; capture video with `adb shell screenrecord --time-limit N`.
- Clear logcat immediately before a replay when the pass/fail evidence depends on app logs.
- First-run overlays can block app automation. Dismiss Android's fullscreen education overlay and app consent dialogs before starting an autoplay or timed replay.

## Bundled Resources

- `scripts/emulator-runner.sh`: reusable start/wait/screenshot/record/stop helper.
- `references/local-android-setup.md`: local SDK, AVD, and troubleshooting notes. Read it when the emulator fails to start, ADB does not see the device, or a repo needs machine-specific defaults.
