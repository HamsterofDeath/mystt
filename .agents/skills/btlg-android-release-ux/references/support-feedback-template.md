# Support And Feedback Template

Use this as a reusable starting point for BTLG Android game bug-report intake, tester feedback logs, support runbooks, or first-production-week triage. Replace bracketed placeholders in the target repo. Keep the committed version blank; filled private data belongs in an owner-held tracker outside git.

## Current Test Context

- App: `[Game name]`.
- Package: `[applicationId]`.
- Current build: `[versionCode] ([versionName])`.
- Track: `[internal testing | closed testing | open testing | production]`.
- Test link: `[Play tester opt-in or store listing URL]`.
- Release artifact/source: `[tag, commit, or AAB note]`.
- Public privacy policy: `[URL]`.
- Public support email: `[email]`.

## Privacy Rules

- Use anonymous tester labels such as `Tester 01`; keep real names and email addresses in Play Console or another private owner-held system.
- Do not request passwords, payment details, government IDs, full Google account screenshots, Advertising IDs, device serial numbers, or unnecessary personal data.
- Keep raw screenshots, recordings, private messages, and contact details outside git.
- Summarize themes in repo or public artifacts instead of pasting private feedback.

## Issue Intake Table

Copy this table into a private tracker before use.

| Issue ID | Date | Tester label | Source | Build seen | Device model | Android version | Category | Mode | Level | Severity | Status | Expected | Actual | Repro steps | Evidence link | Owner notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-001 |  | Tester 01 | internal test |  |  |  |  |  |  |  | new |  |  |  | private |  |
| T-002 |  | Tester 02 | internal test |  |  |  |  |  |  |  | new |  |  |  | private |  |
| T-003 |  | Tester 03 | internal test |  |  |  |  |  |  |  | new |  |  |  | private |  |

## Categories

- install_update: opt-in, install, update, listing visibility, wrong account, unavailable app.
- crash_freeze: crash, ANR, freeze, black screen, app resume failure.
- loading: first launch, startup loading, level loading, long wait between levels.
- tutorial: tutorial, onboarding, first-session clarity.
- gameplay: stuck level, unclear move, wrong rules/physics, restart, undo, hint, solution unlock.
- mode_navigation: mode selection, level select, menus, settings, back/home navigation.
- visual_layout: small-phone layout, HUD, buttons, readability, screenshots.
- audio: music, sound effects, volume toggles, unwanted silence.
- ads_consent: rewarded ads, ad unavailable fallback, consent prompt, Privacy Choices.
- purchases_restore: full unlock, price display, purchase flow, restore purchases, entitlement not applied.
- privacy_support: Privacy Policy, data deletion, support contact, consent questions.

## Severity

- critical: crash, ANR, data-loss risk, app cannot install, app cannot launch, purchase entitlement is wrong, rewarded reward is granted incorrectly.
- high: blocks normal progress, makes a tutorial impossible, breaks Play install/update, or causes repeated user confusion.
- medium: confusing but recoverable gameplay, layout/readability issue, slow flow, ad/IAP unavailable path issue.
- low: copy, polish, minor visual issue, minor audio issue, isolated suggestion.

## Status

- new: received but not triaged.
- needs_repro: not enough detail to reproduce.
- accepted: reproducible or clearly actionable.
- fixed: code/content changed and verified locally.
- deferred: known issue intentionally not fixed before the next release.
- not_repro: tried and could not reproduce with available evidence.
- owner_followup: needs Play Console, AdMob, Firebase, billing product, legal/privacy, support email, or tester-account action.

## Support Intake Prompts

### Install Or Update Issue

Please confirm that you opened the Play tester or store link with the same Google account that was added to the tester list, then open the app listing from that link and check for updates. If it still does not work, send your device model, Android version, app version shown by Google Play, and the exact message Google Play shows.

### Crash Or Freeze

Please send your device model, Android version, app version shown by Google Play, the mode and level if you know them, and what happened just before the crash or freeze. A screenshot or short screen recording helps if you can include one.

### Gameplay Or Level Issue

Please send the mode, level, what you expected to happen, what happened instead, and the last few actions you took. A screenshot or short screen recording is helpful when available.

### Rewarded Ad Or Privacy Choices Issue

Please tell us whether this happened with a rewarded ad, Privacy Policy, or Privacy Choices. Include your device model, Android version, app version, and whether the app showed an ad, a consent prompt, an unavailable message, or nothing.

### Purchase Or Restore Issue

Please tell us whether this happened while buying the full unlock, restoring purchases, or using an already-unlocked app. Include your device model, Android version, app version, and the exact message shown. Do not send card details, passwords, full account screenshots, or receipts containing private payment details unless the owner specifically requests a redacted proof channel.

### Data Deletion Or Privacy

This game currently has no app account or server profile unless the release docs say otherwise. Game progress and settings are local to the device and can usually be removed by clearing app data or uninstalling the app. Ads, consent, and SDK-side data are handled through Google services as described in the privacy policy. Send privacy requests to the approved public support email without passwords, payment details, or unnecessary personal data.

## Triage Summary

Update this privately after each tester wave.

- Test window:
- Build(s) tested:
- Number of testers who installed from Google Play:
- Number of sessions reported:
- Critical/high issues:
- Most common confusion:
- Tutorial/onboarding issues:
- Loading/performance issues:
- Ad/consent/privacy issues:
- Purchase/restore issues:
- Store install/update issues:
- Fixes made from feedback:
- Known issues deferred:
- Ready for next tester wave: yes/no.

## Production Access Summary

If Play asks what was learned from testing, summarize themes without personal data.

- What testers liked:
- What testers found confusing:
- Crash/freeze/install issues found:
- Gameplay fixes made:
- Tutorial or onboarding fixes made:
- Ad/consent/privacy fixes made:
- Purchase/restore fixes made:
- Remaining known issues:
- Why the app is ready for production:
