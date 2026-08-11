# Lights 2026 Case Study

Use this as a concrete example of the first BrainLiftGames optional rewarded skip integration.

## Product Rule

- Ads are optional only.
- The placement is "watch a rewarded ad to skip this level".
- Normal progression remains available by solving the puzzle.
- The reward is one skip in the current game mode.
- Rewarded skip is separate from solve/hint/cheat behavior.

## Play Console Facts

- Developer account: BrainLiftGames.
- Developer account ID: `5159712856446346925`.
- App: `Lights - Neon Switch Puzzle`.
- Package: `de.dhaup.lights2026`.
- Play app numeric ID observed in Console URL: `4973090782448987540`.
- App status observed during setup: draft.
- Advertising ID declaration saved as yes.
- Advertising ID reasons selected:
  - Ads or marketing.
  - Analytics.
  - Fraud prevention, security, and compliance.
- Ads declaration changed from no ads to contains ads.
- Privacy policy URL already present: `https://brainliftgames.com/privacy/lights`.
- Data Safety was updated for Google Mobile Ads SDK use:
  - App collects/shares required user data: yes.
  - Data encrypted in transit: yes.
  - No account creation in app.
  - No external sign-in.
  - No deletion request option.
  - Data types selected: approximate location, app interactions, diagnostics, other app performance data, device or other IDs.
  - Per-type handling: collected and shared, not session-only, user can choose whether collected, purposes are analytics, ads/marketing, fraud prevention/security/compliance.
- Saved Play changes still needed submission from Publishing overview.

## AdMob Facts

- Account was approved and ad serving was enabled.
- Setup checklist still showed app-store linking/review work.
- Created an unpublished Android AdMob app entry because the Play app was still draft.
- AdMob app name: `Lights - Neon Switch Puzzle`.
- AdMob internal URL ID: `7656845349`.
- Production AdMob app ID: `ca-app-pub-5488189430254918~7656845349`.
- Rewarded ad unit:
  - Format: rewarded (`Mit Praemie`), not rewarded interstitial.
  - Name: `rewarded_skip_level`.
  - Reward amount: `1`.
  - Reward item: `level_skip`.
  - Production ad unit ID: `ca-app-pub-5488189430254918/7894164432`.
- AdMob warned new ad units can take up to one hour before serving.
- AdMob app still needed Play Store link/review when the listing became eligible.

## Android Implementation

Files changed in `lights_2026`:

- `app/build.gradle.kts`
- `app/src/main/AndroidManifest.xml`
- `app/src/main/java/de/dhaup/lights2026/app/MainActivity.kt`
- `app/src/main/java/de/dhaup/lights2026/app/RewardedSkipAdManager.kt`
- `app/src/main/java/de/dhaup/lights2026/scene/SceneController.kt`
- `app/src/main/java/de/dhaup/lights2026/render/Hud.kt`
- `app/src/main/java/de/dhaup/lights2026/render/LightsRenderer.kt`
- `design/store/listing.md`
- `design/ad_strategy_notes.txt`

Gradle choices:

- Google Mobile Ads SDK: `com.google.android.gms:play-services-ads:25.3.0`.
- UMP SDK: `com.google.android.ump:user-messaging-platform:4.0.0`.
- Debug AdMob app ID: `ca-app-pub-3940256099942544~3347511713`.
- Debug rewarded ad unit ID: `ca-app-pub-3940256099942544/5224354917`.
- Release AdMob app ID: `ca-app-pub-5488189430254918~7656845349`.
- Release rewarded skip ad unit ID: `ca-app-pub-5488189430254918/7894164432`.

Code shape:

- `RewardedSkipAdManager` is Activity-owned.
- It shows a native confirmation dialog before any consent/ad request.
- It runs UMP `requestConsentInfoUpdate` and `loadAndShowConsentFormIfRequired`.
- It lazily initializes `MobileAds`.
- It uses `RewardedAd.load`.
- It grants progress only from the rewarded callback.
- It shows short Toast messages for loading, unavailable, canceled, and earned states.
- `SceneController` exposes `ctrlSkip(state)` and `onRewardedSkipEarned(mode)`.
- `Hud.Button.SKIP` sits beside solve.
- The renderer dispatches the HUD skip button to the controller.

Persistence note:

- Lights 2026 only had `maxSolvedLevel`.
- The implementation reused it as highest cleared-or-skipped level.
- Future games should prefer `maxUnlockedLevel` or `maxProgressLevel`.

## Verification Done

- `./gradlew :app:assembleDebug` passed.
- `./gradlew :app:testDebugUnitTest` passed.
- `./gradlew :app:assembleRelease` passed, including `lintVitalRelease`.
- Debug merged manifest used test app ID `ca-app-pub-3940256099942544~3347511713`.
- Release merged manifest used production app ID `ca-app-pub-5488189430254918~7656845349`.
- Debug `BuildConfig` used rewarded test unit `ca-app-pub-3940256099942544/5224354917`.
- Release `BuildConfig` used rewarded production unit `ca-app-pub-5488189430254918/7894164432`.
- Merged manifests included `INTERNET`, `ACCESS_NETWORK_STATE`, and `com.google.android.gms.permission.AD_ID`.
- Debug APK installed and launched on `emulator-5554`; process stayed alive and recent logcat showed no fatal startup crash or missing AdMob application ID crash.

## Remaining Production Items

- Link the AdMob app to the Play Store app when eligible.
- Confirm AdMob Privacy and Messaging/GDPR setup for EEA users before production release.
- If UMP reports that a privacy options entry point is required, add a visible in-game privacy/settings entry point.
- Submit saved Play Console changes from Publishing overview during release preparation.
