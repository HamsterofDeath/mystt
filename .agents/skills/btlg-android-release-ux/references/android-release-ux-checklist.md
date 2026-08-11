# Android Release UX Checklist

Use this checklist when auditing or implementing the standard BTLG Android game release UX pattern. Record evidence with file paths, command output, or console page names.

## Repo Discovery

- Package/application ID and app name are known.
- VersionCode/versionName and current Play track/release state are known.
- Release docs, store drafts, privacy docs, AdMob notes, and tester docs have been searched.
- Gradle dependencies are checked for:
  - Google Mobile Ads SDK.
  - UMP.
  - Google Play Billing.
  - Play in-app review.
  - Firebase/analytics, if present.
- Manifest is checked for AdMob app ID metadata, AD_ID, internet/network permissions, backup/data extraction, app links, and exported components.

## Optional Rewarded Ads

- Rewarded ads are optional and player-initiated.
- Each placement has a clear purpose, such as undo, solution unlock, level unlock, or skip.
- A native confirmation or equivalent opt-in appears before loading/showing an ad.
- Rewards are granted only from the SDK earned-reward callback.
- Ad unavailable, canceled, load-failed, and show-failed paths do not block progress or grant rewards incorrectly.
- Debug builds use Google test IDs; release builds use production IDs.
- Release docs name each production ad unit, placement, and reward item.
- If Google Mobile Ads/UMP code is missing or changing, use `android-admob-ads`.
- If AdMob app setup, ad units, Privacy & Messaging, or app review are needed, use `admob-settings`.

## Full Unlock IAP

- A one-time managed Play Billing product exists, normally `full_unlock`.
- The app uses an in-app product, not a subscription, for the full unlock.
- Purchase state grants the entitlement only for the expected product and only when purchased.
- Pending, canceled, failed, or unrelated product purchases do not grant the entitlement.
- Purchased but unacknowledged transactions are acknowledged once.
- Entitlement is persisted locally and survives app restarts.
- The full unlock bypasses or removes ad-gated UX according to the product decision.
- Tests cover product ID, grant rules, acknowledgement rules, and UI wiring.

## Restore Purchases

- Restore purchases is visible from settings/options or the purchase surface.
- Restore triggers owned-purchase reconciliation with Google Play, not only local state checks.
- Startup or foreground reconciliation restores entitlement after reinstall or device change when Play reports ownership.
- Restore has success, already-owned, unavailable, and failure feedback.
- Restore does not ask for personal account data, payment details, or private screenshots.

## Review Prompt

- The app depends on `com.google.android.play:review` or a current equivalent.
- Review requests happen at a positive moment, usually after a level completion or milestone.
- Prompt attempts are gated by solved/completed progress and cooldown time.
- No prompt at launch, after failure, inside onboarding, over consent/ad UI, or after every level.
- The app handles request/launch failures silently or with non-blocking fallback.
- Store strategy questions route to `play-store-aso-launch`.

## Privacy And Support Entry Points

- Privacy Policy link is visible in the main menu, settings, or options before release.
- Privacy Choices entry point is visible when UMP requires privacy options or consent withdrawal.
- Privacy entry points use the public BTLG privacy policy URL for the specific game.
- Public support email is consistent across app UI, Play Console app contact, privacy policy, tester invite, and store listing.
- Support text avoids promises beyond the approved privacy policy.
- Data deletion wording matches the app architecture: no account/server profile unless the app actually has one.

## Play Badges And Store Surface

- Play listing truthfully reflects ads, IAP, optional rewarded help, and no forced ads if applicable.
- Store badges/declarations align with app behavior: Contains ads, In-app purchases, age rating, target audience, Data Safety, Advertising ID, and content rating.
- Screenshots show real gameplay from a release-intended build.
- Privacy policy URL and developer website/contact are present.
- Listing growth, localization, review strategy, and asset quality route to `play-store-aso-launch`.

## Tester Feedback And Bug Reports

- A blank private-copy feedback template exists or is prepared from `support-feedback-template.md`.
- Filled tester names, email addresses, raw screenshots, recordings, and private messages are not committed.
- Issue categories cover install/update, crash/freeze, loading, tutorial, gameplay, layout, audio, ads/consent, purchases, privacy, and support.
- Severity and status fields are defined.
- Tester summaries are anonymized before being copied into public or repo artifacts.

## Release Verification

- Run the repo's documented unit test, lint, debug build, and release bundle/APK commands appropriate to the change.
- Verify debug and release BuildConfig/resource values for ad unit IDs, billing product IDs, and feature flags.
- Inspect merged manifests for AdMob app ID, AD_ID, network permissions, backup/data extraction, and privacy-sensitive declarations.
- Smoke-test debug with Google test ads if ad behavior changed.
- Smoke-test signed release launch and Privacy/Privacy Choices entry points without clicking production ads.
- Verify Play Console release mechanics with `play-console-release` when uploading or publishing.
- Update local release docs with exact verification commands and results.
