---
name: android-admob-ads
description: Add, audit, or update Google AdMob ads in Android apps and games. Use when Codex needs to choose a friendly, annoying, or maximum-monetization ad strategy; integrate Google Mobile Ads SDK, UMP consent, banners, interstitials, rewarded ads, rewarded level gates, rewarded interstitials, app-open ads, native ads; verify debug/test versus production ad IDs; or update Play Console declarations, Data Safety, and ad-related release state.
---

# Android AdMob Ads

## Goal

Implement AdMob in Android projects without surprising users, breaking Play
policy, or mixing test and production IDs. Use `admob-settings` for live AdMob
account configuration; use this skill for local Android code, Gradle, manifest,
policy-copy, and verification work.

Maintain a project-local notes file, preferably `design/ad_strategy_notes.txt`,
with every account, policy, SDK, ad-unit, consent, and implementation fact learned
during the task.

For Brain Lift Games products, also check the sibling marketing repository's
`MAXIMUM_MONETIZATION.md`. It is the canonical product, economics, policy, and
measurement playbook for the rewarded-level-gate strategy. Update the product's
`products/<slug>/PRODUCT.md` and `LAUNCH_STATE.md` after implementation; never
record a planned console price or setting as live until it has been verified.

## Source Checks

Before editing, inspect:

- Package/application ID, Gradle/AGP versions, manifest, Activity/Compose/View setup,
  navigation/controller/state, persistence, and build variants.
- Existing dependencies for `play-services-ads`, UMP, billing, analytics, and in-app
  review.
- Store/listing/privacy copy for claims like "no ads", "no tracking", or "no data
  collected"; update wording if ads or SDK disclosures make those claims false.
- Existing UI conventions and gameplay/app flow. Ads belong near deliberate UX
  placements, not inside pure model, level-definition, parser, generator, or
  renderer-only classes.

## Choose The Ad Format

Choose the format from the product goal and user interruption cost:

- Banner/adaptive banner: persistent low-friction monetization for menus,
  dashboards, or non-immersive screens. Avoid covering controls or gameplay.
- Interstitial: full-screen break between natural transitions only, such as after
  a completed level or before returning to a menu. Never show at launch, on every
  tap, or mid-action.
- Rewarded: user explicitly opts in for a benefit, such as extra currency, hints,
  retries, unlocks, or level skips. Grant the reward only from the earned-reward
  callback.
- Rewarded interstitial: use only when the app can explain the reward clearly
  before the ad and handle the user declining.
- App-open: use sparingly for utility/session-return flows; avoid games unless the
  UX case is explicit.
- Native: use for feeds or content cards where an ad can be clearly labeled and
  visually integrated without imitating app content.

Prefer one AdMob ad unit per app, format, and placement, named by purpose, such as
`main_menu_banner`, `level_complete_interstitial`, or `rewarded_hint`.

## Brain Lift Games Strategy Modes

Choose and record one primary strategy before writing ad code:

- **Friendly ads**: opt-in rewarded assists only, such as hint, undo, skip,
  revive, or optional content unlock. No forced interstitials. This is the
  default for calm puzzle games when the owner has not selected another mode.
- **Annoying ads**: one regular interstitial after every third genuine campaign
  solve at the post-solve boundary, plus optional rewarded assists and a
  one-time no-ads/full-unlock purchase. Navigation, app launch, daily puzzles,
  restarts, replays, failed moves, and rewarded skips do not advance the
  cadence. If an interstitial is unavailable at the third solve, consume the
  slot and begin a new three-solve cycle rather than showing it unexpectedly
  later. Chroma Shift is the reference implementation.
- **Maximum monetization**: a substantial standard campaign stays free; each
  hard/expert/mastery level requires one explicitly chosen rewarded ad for its
  permanent first-play unlock, with a one-time full unlock as the alternative.
  Use the detailed contract below. Sticks, Stones and Screws is the reference
  implementation.

Do not blend the modes accidentally. In particular, the maximum-monetization
gated catalog has no forced completion interstitial, because one level must not
produce a rewarded-ad-plus-interstitial double charge.

## Maximum Monetization: Rewarded Level Gate + Full Unlock

Use this model only when the game has a complete, useful free campaign and a
distinct hard, expert, or mastery catalog. Do not apply it to a token tutorial,
very short game, rapidly repeating session, or flow where every failed attempt
would demand another ad.

The player contract is:

- Standard/core content remains a real playable free game.
- Before the first play of each gated premium level, show a native prompt with
  `Watch one ad`, `Unlock all · <localized price>`, and `Cancel`.
- The prompt clearly says that one completed rewarded ad permanently unlocks
  exactly that level.
- Grant the unlock only from `onUserEarnedReward`, persist it immediately, and
  never ask for another level-unlock ad on retry or replay.
- A non-consumable full-unlock purchase opens all gated content, restores across
  supported installs, and bypasses every gated-level ad plus every forced ad the
  product promises to remove.
- Do not show a forced interstitial on completion of an ad-gated level. Never
  create a rewarded-ad-plus-interstitial double charge around one level.
- If the ad is unavailable or consent is declined, leave Cancel and the usable
  free campaign intact; offer purchase when Billing is available and allow retry
  later.

Implementation requirements:

- Use a stable ID for each gated level and persist a set of permanently
  rewarded-unlocked level IDs.
- Migrate old saves so previously completed premium levels remain accessible.
- Keep content progression, completion, and rewarded access as distinct state
  unless the game's existing model safely unifies them.
- Read the localized full-unlock price from Google Play. A hard-coded amount is
  only a temporary fallback while product details are unavailable.
- Handle ad load failure, show failure, dismissal, process restart, offline use,
  pending purchase, restore, refund/revocation, and unavailable Billing without
  trapping the player or granting unearned access.
- Instrument first-gate reach, Watch / Buy / Cancel selection, rewarded
  availability and completion, unlock persistence, purchase conversion,
  retention by gated level, revenue per gated player, and access complaints.

For internal revenue planning:

```text
maximum ad-path revenue per completing player
  = gated level count × net revenue per completed rewarded ad
```

Treat this as a maximum, not a forecast: most players will not complete every
gated level, and eCPM varies by geography, consent, fill, mediation, and season.
Price the full unlock for immediate permanent access, convenience, and ad
removal, then validate it with cohort data.

Before release, recheck the current official
[Google Play ads policy](https://support.google.com/googleplay/android-developer/answer/9857753)
and
[Google rewarded-ad inventory requirements](https://support.google.com/admanager/answer/7496282).
The rewarded ad must be a fresh, affirmative opt-in with a clear, accurate,
conspicuous reward disclosure and a decline path.

## Console And Policy

Use `openclaw-browser` for Play Console or AdMob browser work. Use an isolated
copied Chrome profile when possible. Never print cookies, recovery data, tokens,
or other secrets.

In Google Play Console:

- Set the Ads declaration to "contains ads" when any ad format is present.
- Set the Advertising ID declaration to yes when the Google Mobile Ads SDK or
  AD_ID permission is present. Typical reasons are ads/marketing, analytics, and
  fraud prevention/security/compliance.
- Update Data Safety for Google Mobile Ads SDK collection/sharing. Re-check
  current official Google docs because SDK disclosures can change.
- Confirm the privacy policy URL is present and compatible with ad/analytics SDK
  use.
- Remember that saved Play Console changes still need submission from Publishing
  overview before release.

In AdMob:

- Create or verify the AdMob app and app ID.
- Create ad units for each required placement/format. Confirm the format exactly:
  banner, interstitial, rewarded, rewarded interstitial, app-open, or native.
- Record app ID, ad unit IDs, reward details if any, app-linking status, and review
  status in the project notes.
- Expect new apps/ad units to take time before serving production ads.

## Android Implementation

Use current official Google docs for SDK versions, initialization behavior, UMP,
test IDs, and Data Safety facts. Treat these as time-sensitive.

Implementation requirements:

- Add Google Mobile Ads SDK and UMP SDK through the project's existing Gradle
  style.
- Use Google test app/ad unit IDs in debug builds and production IDs only in
  release builds.
- Add the AdMob application ID manifest metadata under `application` via a Gradle
  placeholder: `com.google.android.gms.ads.APPLICATION_ID`.
- Do not put ad unit IDs in the manifest.
- Ensure `INTERNET`, `ACCESS_NETWORK_STATE`, and AD_ID permission behavior match
  the SDK and Play declarations.
- Keep ad services Activity/UI-layer owned. Inject small callbacks into controllers
  instead of making game/app logic depend directly on Mobile Ads SDK classes.
- Run UMP consent update before requesting personalized ads. Add a visible privacy
  options entry point when required.
- Load ads lazily enough to match the Data Safety answer. If collection is declared
  optional, do not initialize/load at startup before the user reaches an ad path.
- Handle load failure, show failure, dismissal, and lifecycle events without
  granting rewards, blocking progress, or crashing.

## Format Notes

- Banners: use adaptive banner sizing, reserve layout space, and avoid layout shift
  after load. Remove/destroy views with the screen lifecycle.
- Interstitials: preload before natural breaks, show only after an explicit app
  event, then clear the consumed ad and load the next one.
- Rewarded ads: show a native confirmation or equivalent opt-in before loading or
  showing. Grant benefits only from `onUserEarnedReward`.
- Rewarded level gates: persist the exact level unlock permanently, preserve
  completed premium levels during save migration, and never gate retries or
  replays. Do not attach a forced completion interstitial to the gated catalog.
- Rewarded level skips: keep solved progress separate from unlocked/skipped
  progress when possible, e.g. `maxSolvedLevel` and `maxUnlockedLevel`.
- Native ads: use Google-provided ad assets, visible ad attribution, and click
  handling through the SDK rather than custom click behavior.
- App-open ads: guard against showing over another ad, over onboarding/consent, or
  during sensitive flows.

## Release Minification (R8) — required keep rules

`com.google.android.gms:play-services-ads` transitively pulls
`androidx.work:work-runtime` → `androidx.room:room-runtime`, even if the app never
uses WorkManager. WorkManager auto-initializes a Room `WorkDatabase` at startup via
`androidx.startup.InitializationProvider`. Room instantiates the generated
`<Database>_Impl` class **reflectively**
(`Class.forName(...).getDeclaredConstructor().newInstance()`), so when the release
build has `isMinifyEnabled = true`, R8 shrinking removes that no-arg constructor as
"unused" and the app **crashes on launch**:

```text
java.lang.RuntimeException: Unable to get provider androidx.startup.InitializationProvider:
  Failed to create an instance of androidx.work.impl.WorkDatabase
```

This only manifests in **minified release builds** — debug builds (minify off) run fine,
so it ships unnoticed. (Real example: Screwdriver 2026 was rejected by Google Play in
June 2026 under the Broken Functionality policy for exactly this crash.)

**Fix:** whenever a project enables `isMinifyEnabled` AND depends on `play-services-ads`
(or Play Billing, which also pulls WorkManager), add to `app/proguard-rules.pro`:

```proguard
# Room (transitive via AdMob/Billing -> androidx.work -> androidx.room).
# R8 strips the reflectively-instantiated generated <Database>_Impl constructor.
-keep class * extends androidx.room.RoomDatabase { <init>(); }
-keep class androidx.work.impl.WorkDatabase_Impl { <init>(); }
```

Always smoke-test the **minified release** APK on a device (not just debug) and check
`logcat -b crash` for this signature before submitting. If a game keeps minify off, it is
not affected today, but add these rules the moment minify is turned on.

## Verification

Run verification before finishing:

- Build debug and run relevant unit tests.
- Build release, including release lint when available.
- Inspect generated `BuildConfig` and merged manifests so debug contains test IDs
  and release contains production IDs.
- Install/launch on an emulator or device if available and check logcat for startup
  crashes, missing AdMob app ID errors, UMP failures, and obvious SDK errors.
- Test ad display only with debug/test IDs. Do not click production ads during
  development.
- For a rewarded level gate, test new install, old-save migration, reward earned,
  dismissal, load/show failure, offline/ad-unavailable behavior, consent decline,
  permanent access after restart, retry, replay, full purchase, pending purchase,
  restore, and entitlement revocation.
- For production-ID release smoke tests, verify launch, foreground state, package
  version, no fatal logcat entries, and privacy-options behavior; do not generate
  real ad interactions unless explicitly requested.

Useful logcat filters:

```text
FATAL EXCEPTION|AndroidRuntime|Consent|UserMessagingPlatform|UMP|MobileAds|AdMob|<package>
```

## References

- Read [Lights 2026 case study](references/lights-2026-case-study.md) only when
  you need a concrete rewarded-ad level-skip implementation example.
