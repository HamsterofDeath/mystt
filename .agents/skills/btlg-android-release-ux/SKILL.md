---
name: btlg-android-release-ux
description: Audit or implement BTLG Android game release UX patterns for optional rewarded ads, full-unlock Play Billing IAP, restore purchases, in-app review prompts, Privacy Policy and Privacy Choices entry points, support email/contact flows, Play badges, tester feedback, bug-report intake, and release readiness checks. Use when a BTLG Android game needs ads, IAP, review prompts, support/privacy UI, tester feedback templates, or release UX verification.
---

# BTLG Android Release UX

## Purpose

Apply the BrainLiftGames Android release UX baseline: optional rewarded ads, a one-time full unlock purchase, restore/reconcile purchases, peak-happiness review prompts, visible privacy/support entry points, and structured tester feedback intake.

Keep this skill as the coordinator. Route implementation-heavy work to the existing specialist skills instead of duplicating their procedures.

## First Pass

Before changing a target Android repo, inspect and record:

- Package/application ID, app name, versionCode/versionName, release track notes, and any project-specific release docs.
- Gradle/AGP structure and dependencies for Google Mobile Ads, UMP, Google Play Billing, Play in-app review, Firebase/analytics, and Play services.
- Manifest declarations: AdMob app ID metadata, permissions including AD_ID, backup/data extraction, links, and exported components.
- Existing privacy/support UI: Privacy Policy, Privacy Choices or consent options, support email/contact, website links, settings/options menu, and localized strings.
- Existing monetization UX: rewarded placements, ad confirmation dialogs, ad-unavailable fallback, `full_unlock` or equivalent product IDs, restore purchase buttons, entitlement persistence, and tests.
- Store/release artifacts: Play listing drafts, Play Console worksheets, Data Safety notes, AdMob notes, tester invites, support runbooks, release notes, and feedback logs.

Read [android-release-ux-checklist.md](references/android-release-ux-checklist.md) for the audit and verification checklist. Read [support-feedback-template.md](references/support-feedback-template.md) when creating or updating bug-report, support, or tester-feedback materials.

## Routing

- Use `android-admob-ads` for Android ad SDK integration, UMP code, rewarded placements, debug/release ad ID separation, and local ad verification.
- Use `admob-settings` for live AdMob app linking, app-ads.txt, Privacy & Messaging, ad units, app review, and account-console checks.
- Use `play-store-aso-launch` for review-prompt strategy, store growth, listing copy, Play badges, screenshots, localization, and launch-readiness prioritization.
- Use `play-console-release` for signed bundle builds, Play Console uploads, track releases, managed publishing, and version-code mechanics.

If a task spans several areas, start with this skill's checklist, then invoke the specialist skill only for the specific implementation or console work.

## BTLG Pattern

- Store listings, release notes, support copy, and other publishing materials must
  never call a game or any of its content `handcrafted`, `handmade`, or
  `hand-made`. Do not imply manual production provenance.

- Ads stay optional. Rewarded ads must be explicitly requested by the player, explained before showing, and must grant rewards only from the earned-reward callback.
- Full unlock is a one-time Play Billing managed product, normally named `full_unlock` unless the existing product contract says otherwise. A purchased unlock should remove or bypass ad-gated friction where product design intends.
- Restore purchases means reconciling owned purchases, not only showing a button. Query current purchases on startup or settings entry, acknowledge eligible purchases once, and persist the entitlement locally.
- Review prompts use the Play in-app review API at positive completion moments. Gate attempts by progress and time so prompts are not shown at launch, after failures, during ads/consent, or repeatedly.
- Privacy and support entries must be reachable from the main menu or settings before release: Privacy Policy, Privacy Choices when UMP requires it, public support email, and a clear route for tester/player reports.
- Bug reports and tester feedback must avoid unnecessary personal data. Keep raw tester names, email addresses, screenshots, recordings, and private messages outside git.

## Example Sources

Use current BTLG game repos as references for intent, not as copy-paste implementation:

- Screwdriver: richer pattern for `full_unlock`, restore/reconcile purchases, multiple rewarded gates, support/contact copy, and tester feedback intake.
- Lights: precedent for optional rewarded skip, lazy ads/UMP, in-app review prompt gating, and release verification notes.

When examples differ from the current target repo's architecture, follow the target repo's patterns and keep the UX contract above.

## Deliverables

For audits, return a prioritized list of gaps with file/console evidence and note which specialist skill should own each fix.

For implementation, update the smallest set of app files and release docs needed, add focused tests for entitlement/reward/review/support behavior, and verify with the repo's documented Gradle commands. Do not click live production ads during development.
