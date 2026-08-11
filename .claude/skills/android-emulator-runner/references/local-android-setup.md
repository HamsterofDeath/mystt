# Local Android Emulator Setup

## Defaults

- Android SDK root: `/home/hod/Android/Sdk`
- Emulator binary: `/home/hod/Android/Sdk/emulator/emulator`
- Preferred emulator AVD for phone-sized smoke tests: `rrr_api36`
- Secondary AVD: `tab10`
- Preferred emulator ADB: `/home/hod/Android/Sdk/platform-tools/adb` when present, otherwise `adb`
- Expected default serial for the first emulator: `emulator-5554`

## Known Reliable Launch Pattern

Use a headless, software-rendered, cold-ish boot for repeatable automation:

```bash
/home/hod/Android/Sdk/emulator/emulator \
  -avd rrr_api36 \
  -no-window \
  -gpu swiftshader_indirect \
  -no-audio \
  -no-boot-anim \
  -no-snapshot-load \
  -read-only
```

If the command exits before ADB sees a device, rerun with `-verbose` and inspect whether QEMU starts. A good launch logs `control console listening on port 5554, ADB on port 5555`.

## Boot Checks

```bash
adb devices -l
adb -s emulator-5554 shell getprop sys.boot_completed
adb -s emulator-5554 shell wm size
adb -s emulator-5554 shell wm density
```

Do not install or launch the target app until `sys.boot_completed` returns `1`.

## Common Blockers

- Android fullscreen education overlay may appear on first app launch. Dismiss the `Got it` button before timed automation.
- Google UMP or consent dialogs can take focus and consume an autoplay start delay. Launch once without autoplay, dismiss consent, then relaunch with the replay/autoplay intent.
- AVDs with CI-like config can start more reliably with `-read-only` and software graphics than with default windowed graphics.
- `adb wait-for-device` can wait forever when the emulator process already died. Poll `adb devices -l` and `pgrep -af 'emulator|qemu-system'` together.
