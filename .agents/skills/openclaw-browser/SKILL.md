---
name: openclaw-browser
description: Use the persistent OpenClaw-controlled Windows Chrome browser from agent sessions for web UI automation, page inspection, screenshots, frontend verification, file uploads, and recovery of the browser/CDP bridge. Requires a unique per-agent/task pinned tab for all page-control use cases (raw CDP target pinning, 1 agent = 1 tab); do not use unpinned active-tab CLI control for browsing or interaction. Use when the user asks the agent to open or control a browser, interact with a website, inspect browser-visible state, upload through a web form, run multiple browser agents in parallel, or recover the OpenClaw browser bridge.
---

# OpenClaw Browser

## Mandatory Unique Pinned Tab Rule

Every OpenClaw browser task that opens, navigates, inspects, screenshots, clicks, types, uploads,
or otherwise controls page content MUST use exactly **one unique pinned tab** for the whole task.
Set a task-unique `PIN_NAME`, create the pinned tab once with `scripts/pinned-tab-ctl.js`, and
reuse that same pinned target until the task is done. This is mandatory for all page-control use
cases, even when no other agents appear to be active.

Do not use unpinned active-tab CLI commands such as `openclaw browser open`, `focus`, `navigate`,
`snapshot`, `click`, `type`, `upload`, or `screenshot` as the normal interaction path. The
OpenClaw CLI has one profile-global active tab; unpinned commands can redirect or be redirected by
other agents and make tabs accumulate. Use the CLI only for bounded health/recovery/status commands
(`doctor`, `status`, `tabs`, service recovery) or for an explicitly documented emergency fallback
after confirming the pinned controller cannot perform the action.

- Make `PIN_NAME` unique per agent/task, for example `PIN_NAME=codex-$(basename "$PWD")-play-audit`.
- Pin by CDP target identity through `pinned-tab-ctl.js`; never rely on Chrome's active tab or a
  positional `tXX` ref for task control.
- If tabs have already piled up from your own navigation, close only stale tabs you created. Do
  not close tabs you did not open; other agents or the user may own them.
- After a burst of timeouts, run `ensure-openclaw-browser.sh` to recover the bridge, then continue
  by recreating or reusing your unique pinned tab.

## 1 Agent = 1 Unique Pinned Tab: Raw CDP Control

The CLI cannot isolate agents on a shared profile: all commands hit the single active tab. For
mandatory per-agent/task tab isolation, drive raw CDP with `scripts/pinned-tab-ctl.js`. It creates
a tab, records its CDP **targetId**, and re-finds it on every call — other agents' focus changes
cannot redirect it.

```bash
export PIN_NAME=codex-my-task      # unique per agent/task; do not reuse another agent's pin
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js create "https://studio.youtube.com/"
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js text | head -20
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js click-text "Erstellen"
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js setfiles 'input[type=file]' 'C:\Users\dhaup\Downloads\video.mp4'
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js close   # when done
```

If the shared or signed-in profile is crowded and `pinned-tab-ctl.js` times out while finding
pages, switch to the direct raw-CDP helper against the **same** `PIN_NAME`. It reads the same
saved target id in `/tmp/openclaw/pinned-tabs`, connects straight to that target WebSocket, and
does not enumerate pages through Playwright:

```bash
export PIN_NAME=codex-my-task
timeout --kill-after=5s 60s node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-direct-cdp.mjs text
timeout --kill-after=5s 60s node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-direct-cdp.mjs click '#saveButton'
timeout --kill-after=5s 60s node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-direct-cdp.mjs setfiles 'input[type=file]' 'C:\Users\dhaup\Downloads\file.png'
```

Use `pinned-tab-direct-cdp.mjs create <url>` only when there is no live pin yet or the saved pin is
stale. This is still pinned-tab control: one task, one `PIN_NAME`, one target. It is not an
active-tab fallback and it must not be used to drive arbitrary unpinned tabs.

Some Google settings surfaces, including AdMob Privacy & Messaging, render the main editor inside
a cross-origin iframe. The direct helper can inspect and control those frames without switching
tabs:

```bash
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-direct-cdp.mjs frames
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-direct-cdp.mjs frame-text display-ads-user-messaging-embed
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-direct-cdp.mjs frame-click-text display-ads-user-messaging-embed "Mitteilungen"
```

Hard-won facts baked into the script:

- Pin by **targetId**, never by `window.name` — Chrome clears `window.name` on cross-site
  navigation, so a name marker set on `about:blank` is gone after the first real `goto`.
- `setfiles` uses `DOM.setFileInputFiles`, whose paths resolve on the **browser host** —
  pass Windows paths (`C:\Users\dhaup\Downloads\...`), not WSL paths. Stage files somewhere
  Windows-local first. This also avoids the CLI `upload` arming dance entirely.
- The shared `winchrome` profile's CDP endpoint is the relay URL in
  `~/.openclaw/openclaw.json` (`browser.profiles.winchrome.cdpUrl`, currently
  `http://192.168.112.1:18812` → Windows loopback `127.0.0.1:18802`). Stale extra relays on
  other ports may point at the same Chrome. Never trust a port by number: check
  `curl <endpoint>/json/list` and confirm the target URLs look like the browser you expect.
- Limits: OS-level dialogs, downloads prompts, and Chrome relaunches are still global.
  This isolates *page control*, not the whole browser.

For custom/lazy widgets, native JavaScript dialogs, or long page-managed uploads, read
[interaction-patterns.md](references/interaction-patterns.md) completely before acting.

## Overview

Use OpenClaw's dedicated Windows Chrome profile through a unique pinned CDP target. The browser is separate from the user's normal Chrome profile and is reached from WSL through the `openclaw-windows-browser.service` CDP bridge.

For project work, prefer a Chrome instance per project. Multiple Codex agents may work in parallel, so ordinary automation, local previews, screenshots, and page inspection should use a project-specific Chrome profile and CDP port instead of sharing the default/main browser. Use the default/main OpenClaw profile only when the task needs existing login or account state; after that, prefer copying the required session state into the project profile rather than driving the shared profile. In every profile, page control still goes through one unique pinned tab.

Core paths:

- OpenClaw CLI: `/home/hod/.openclaw/bin/openclaw`
- Browser bridge service: `openclaw-windows-browser.service`
- Gateway service: `openclaw-gateway.service`
- Chrome profile on Windows: `%LOCALAPPDATA%\OpenClaw\ChromeProfile`
- Windows CDP helper scripts: `/home/hod/.openclaw/scripts/start-windows-chrome-cdp.ps1` and `/home/hod/.openclaw/scripts/windows-cdp-relay.ps1`

## Start And Check

Before browser work, run the helper script:

```bash
bash /home/hod/.codex/skills/openclaw-browser/scripts/ensure-openclaw-browser.sh
```

This starts the OpenClaw gateway and Windows Chrome CDP bridge if needed, then runs `openclaw browser doctor`.

For manual checks:

```bash
systemctl --user is-active openclaw-windows-browser.service openclaw-gateway.service
/home/hod/.openclaw/bin/openclaw browser doctor
/home/hod/.openclaw/bin/openclaw browser status
/home/hod/.openclaw/bin/openclaw browser tabs
```

Expected doctor output includes:

```text
OK gateway: browser control endpoint reachable
OK plugin: enabled
OK profile: winchrome (cdp)
OK browser: running
```

The profile line can differ for project-specific profiles, but it should name the intended profile and show `cdp`.

## Timeout Discipline

Treat OpenClaw browser commands as remote UI operations. Manual OpenClaw, PowerShell, and relay probes should be bounded so a bad CDP bridge, a stuck Google page, or a dead WSL service does not leave the Codex session waiting indefinitely.

Use the helper first; it has bounded health, startup, relay, and doctor checks:

```bash
timeout --kill-after=5s 120s bash /home/hod/.codex/skills/openclaw-browser/scripts/ensure-openclaw-browser.sh
```

For manual health/status commands, wrap the command itself. Do not use these CLI examples as
the normal page-control path:

```bash
timeout --kill-after=5s 30s /home/hod/.openclaw/bin/openclaw browser tabs
```

For page navigation and inspection, use the pinned controller with shell-level timeouts:

```bash
timeout --kill-after=5s 60s node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js create "https://play.google.com/console/"
timeout --kill-after=5s 45s node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js text
```

If `pinned-tab-ctl.js` times out but the target exists in the profile, try the direct raw-CDP helper
before restarting services:

```bash
timeout --kill-after=5s 60s node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-direct-cdp.mjs url
timeout --kill-after=5s 60s node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-direct-cdp.mjs text
```

If direct CDP also times out, do not immediately repeat the same command. Run the helper, then inspect the browser state with bounded `doctor`, `status`, and `tabs`. Check the Windows CDP relay directly when the profile is remote:

```bash
win_host="$(ip route | awk '/default/ {print $3; exit}')"
curl -fsS --max-time 2 "http://${win_host}:18812/json/version"
```

If OpenClaw says a remote CDP profile is stopped or unreachable, verify the real Windows Chrome port before restarting repeatedly. The OpenClaw profile config can be stale:

```bash
powershell.exe -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name = 'chrome.exe'\" | Select-Object ProcessId,CommandLine | Format-List"
powershell.exe -NoProfile -Command "(Invoke-RestMethod -UseBasicParsing http://127.0.0.1:18802/json/version).webSocketDebuggerUrl"
```

The helper timeout knobs are:

- `OPENCLAW_HEALTH_TIMEOUT` for direct gateway `/health` probes, default `2`.
- `OPENCLAW_COMMAND_TIMEOUT` for ordinary OpenClaw, PowerShell, and systemctl commands, default `30`.
- `OPENCLAW_DOCTOR_TIMEOUT` for each `browser doctor` attempt, default `30`.
- `OPENCLAW_STARTUP_ATTEMPTS` for gateway startup checks, default `30`.
- `OPENCLAW_DOCTOR_ATTEMPTS` for browser readiness checks after recovery commands, default `3`.

## Project Windows Profiles

Use an isolated Windows Chrome profile copy by default for each project. Launch it on a unique CDP port, relay that port to WSL, set `OPENCLAW_CDP_URL` to that endpoint, and drive one unique pinned tab with `pinned-tab-ctl.js`. This prevents parallel agents from changing each other's tabs, viewport, cookies in flight, or page state.

### Isolation model (profiles plus mandatory pinned tabs)

The OpenClaw CLI has **no per-command tab targeting** — there is no positional tab ref and no `--tab` flag on `snapshot`/`click`/`type`/`evaluate`/etc. Every command acts on the single **active tab** of the selected profile; you move it with `focus tXX` (and `open`/`navigate`/`close` also move it). The `tXX` refs printed by `tabs` are arguments to `focus`/`close` only. So two agents cannot "lock" separate tabs inside one profile with CLI focus. All page control must pin a CDP target by `targetId` instead.

**Use both layers.** Profiles isolate cookies, viewport, and browser process state; pinned tabs isolate the task's page target inside the selected profile. `openclaw browser --browser-profile <name> <cmd>` (flag goes AFTER `browser`) can still be useful for health/status checks, but normal page control must use `pinned-tab-ctl.js` against that profile's `OPENCLAW_CDP_URL`.

### Scripted provisioning (preferred)

Use the helper instead of the manual PowerShell below — it clones settings, launches Chrome on its own port, starts the relay, and registers the profile in `~/.openclaw/openclaw.json`:

```bash
# one persistent, isolated profile per agent (distinct --name AND --port each)
scripts/prepare-isolated-browser.sh --name agent1 --port 18822 --url about:blank
# then drive exactly one unique pinned tab in that profile:
export OPENCLAW_CDP_URL=http://<wsl-or-windows-relay-host>:18822
export PIN_NAME=codex-agent1-example
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js create https://example.com
```

**Login reality (verified 2026-07-01):** a profile-dir copy does **not** carry a Google login. Chrome's App-Bound Encryption makes the copied cookie DB undecryptable, and Google's device-bound sessions (DBSC) reject copied auth cookies even when read decrypted over CDP (you reach the account chooser / `confirmidentifier`, never a signed-in session). The reliable "don't log in every time" is **persistence**: the profile dir survives restarts, so sign in **once** in the launched window and the session stays put across runs (this is exactly why the shared `winchrome` profile stays logged in). For non-Google sites (itch.io, most dashboards) you can transfer the login without re-auth:

```bash
scripts/sync-openclaw-session.sh --from winchrome --to agent1 --domains 'itch.io'
```

Cookies read over CDP are already decrypted, so the top-up bypasses ABE; it prints counts only, never values. It pre-fills the Google account chooser but will not produce a working Google session.

The shared OpenClaw profile is the default/main profile. It has used ports such as `18801` and `18802`; inspect the running Chrome command line or `/json/version` endpoint instead of assuming a port. It is acceptable for account/login work, or as the source for cookies/session state, but avoid using it for ordinary project browser control once an isolated profile can do the work.

Use a project-specific profile and port. Example:

```bash
powershell.exe -NoProfile -Command '$src="$env:LOCALAPPDATA\OpenClaw\ChromeProfile"; $dst="$env:LOCALAPPDATA\OpenClaw\ChromeProfile-rrr-release"; if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }; New-Item -ItemType Directory -Force $dst | Out-Null; robocopy $src $dst /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP /XD "Crash Reports" "ShaderCache" "GrShaderCache" "GraphiteDawnCache" /XF "Singleton*" "LOCK" | Out-Null; $chrome="C:\Program Files\Google\Chrome\Application\chrome.exe"; Start-Process -FilePath $chrome -ArgumentList @("--user-data-dir=$dst", "--remote-debugging-port=18802", "--no-first-run", "--no-default-browser-check", "--new-window", "https://play.google.com/console") -WindowStyle Normal'
```

Windows Chrome binds remote debugging to Windows loopback. Start a Windows-side relay so WSL can reach it:

```bash
relay_win="$(wslpath -w /home/hod/.openclaw/scripts/windows-cdp-relay.ps1)"
powershell.exe -NoProfile -Command "\$script='$relay_win'; \$args=@('-NoProfile','-ExecutionPolicy','Bypass','-File',\$script,'-ListenAddress','172.20.160.1','-ListenPort','18802','-TargetAddress','127.0.0.1','-TargetPort','18802'); Start-Process -FilePath powershell.exe -ArgumentList \$args -WindowStyle Hidden"
curl -fsS http://172.20.160.1:18802/json/version
```

A profile copy lands on Google sign-in by design (App-Bound Encryption + device-bound sessions — see "Login reality" above), and copying cookies over CDP will **not** fix a Google login; it only helps non-Google sites and pre-fills the Google account chooser. Prefer `scripts/sync-openclaw-session.sh`. The underlying CDP copy, if you need it inline:

```js
const { chromium } = require("/home/hod/IdeaProjects/dinkel/node_modules/playwright-core"); // any project's playwright-core
const source = await chromium.connectOverCDP("http://<win-host>:<source-relay-port>");
const dest = await chromium.connectOverCDP("http://<win-host>:<dest-relay-port>");
const cookies = (await source.contexts()[0].cookies())
  .filter(c => c.domain.includes("itch.io")); // non-DBSC sites only
await dest.contexts()[0].addCookies(cookies);
```

Do not print cookie values. Use `process.exit(0)` at the end of small CDP scripts instead of `browser.close()`, because `browser.close()` closes the remote Chrome process.

### WSL Local Preview From Isolated Chrome

When opening a WSL-hosted local app in Windows Chrome, do not use `http://127.0.0.1:<port>` unless the server is running on Windows. From Windows Chrome, `127.0.0.1` is Windows loopback, not WSL loopback. Bind the WSL dev or static server to `0.0.0.0`, get the WSL address with `hostname -I | awk '{print $1}'`, and navigate Windows Chrome to `http://<wsl-ip>:<port>/...`.

For quick previews of a built app, a static server is often simpler and more stable than a framework dev server:

```bash
npm run build
nohup python3 -m http.server 5181 --bind 0.0.0.0 --directory dist > /tmp/project-static-5181.log 2>&1 < /dev/null &
wsl_ip="$(hostname -I | awk '{print $1}')"
```

Then create or reuse the task's unique pinned tab at `http://$wsl_ip:5181/` in the selected Windows Chrome profile. If using Vite or another dev server, keep it attached to an active tool session or confirm the process survives after the shell exits; some dev servers terminate when their stdin/session closes.

If Windows Chrome still cannot reach the WSL server, or if detached WSL servers are being cleaned up when the tool shell exits, serve the already-built files from Windows instead. This works well for repos under `/mnt/c`:

```bash
dist_win="$(wslpath -w "$PWD/dist")"
powershell.exe -NoProfile -Command "\$dir='$dist_win'; Start-Process -FilePath py.exe -ArgumentList @('-3','-m','http.server','5182','--bind','127.0.0.1','--directory',\$dir) -WindowStyle Hidden"
```

Then create or reuse the task's unique pinned tab at `http://127.0.0.1:5182/` in the selected Windows Chrome profile. Here `127.0.0.1` is correct because the server is also running on Windows.

Before opening a new visible tab, close or reuse existing tabs in the isolated profile when the user asks to keep browser load down. Drive the isolated CDP endpoint through a unique pinned tab:

```bash
export OPENCLAW_CDP_URL=http://172.20.160.1:18802
export PIN_NAME=codex-local-preview
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js create "http://${WSL_IP}:5181/"
```

## Common Actions

Use the pinned-tab controller for page actions. Use the absolute OpenClaw CLI path only for
health/status/recovery commands unless an emergency fallback is explicitly documented.

Open a URL:

```bash
export PIN_NAME=codex-unique-task-name
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js create "https://example.com"
```

Open local files:

OpenClaw browser navigation blocks direct `file://...` URLs. For simple local file previews (HTML reports, static pages), do not start a server. Always copy WSL/Linux-generated static files to a Windows-local staging folder before opening them. Copy the whole containing static folder when the HTML may reference sibling CSS, JS, images, CSVs, or other assets. Do not open static files through `\\wsl.localhost`, `file:///home/...`, or other WSL/Linux paths in a Windows browser.

For a single self-contained file, use the helper that copies it to the Windows Downloads folder and opens it in the default Windows browser:

```bash
bash /home/hod/.codex/skills/openclaw-browser/scripts/open-simple-file-in-windows-firefox.sh "/absolute/or/relative/path/to/file.html"
```

For a static report folder, copy the directory to a Windows-local staging path first, then open the copied file:

```bash
src="$(wslpath -w "$PWD/artifacts/report-folder")"
powershell.exe -NoProfile -Command "\$dst=Join-Path \$env:USERPROFILE 'Downloads\CodexStatic\project\report-folder'; if (Test-Path \$dst) { Remove-Item \$dst -Recurse -Force }; New-Item -ItemType Directory -Force (Split-Path \$dst) | Out-Null; Copy-Item '$src' \$dst -Recurse; Start-Process (Join-Path \$dst 'index.html')"
```

If the source is already under `/mnt/c/`, it is already Windows-local, but still copy static reports into the staging folder unless the user explicitly asks to open the source path directly.

Use these shortcuts when the user says things like "show me the HTML report", "open this in browser", or "open the dialog report" and no browser automation, DOM inspection, screenshot capture, local app routing, or account/login state is needed. The script helper copies one file into `%USERPROFILE%\Downloads` with a collision-safe name and opens it in the default Windows browser (Firefox if installed, otherwise the system default). If the user specifically asks for Edge, use `Start-Process msedge.exe` on the copied Windows-local path. If OpenClaw inspection, automation, or screenshots are needed, serve the file over a local HTTP server and open via the OpenClaw browser instead. Do not use these shortcuts for apps that need module loading, fetches, a dev server, routing fallback, or same-origin behavior; serve those over HTTP.

Inspect current page state:

```bash
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js url
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js text
```

Interact with the pinned tab:

```bash
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js click "button[type=submit]"
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js type "input[name=q]" "text"
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js fill "input[name=title]" "replacement text"
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js select "select[name=branch]" "closed-beta"
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js press Enter
```

`type` appends keystrokes to the current value. Use `fill` to replace the value of a plain
`input` or `textarea`. Use `select` for a native `<select>`; keep the trusted-click pattern for
custom/lazy comboboxes.

Upload a local file through a file chooser:

```bash
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js setfiles 'input[type=file]' 'C:\Users\dhaup\Downloads\file.png'
```

Then trigger the page's upload handler with a pinned-tab click if the site requires it.

### File upload tips and tricks

Use the pinned controller's `setfiles` command first. It talks to the pinned tab's DOM via CDP
and avoids the OpenClaw CLI upload arming flow entirely.

**Use Windows paths with `setfiles`.** `DOM.setFileInputFiles` resolves paths on the browser
host, so stage files somewhere Windows-local and pass paths such as
`C:\Users\dhaup\Downloads\file.png`. Do not pass `/tmp/...` or WSL paths to `setfiles`.

- Good staging target: `%USERPROFILE%\Downloads\CodexUploads\<project>\...`.
- If a file starts in WSL, copy it to a Windows-local path with `wslpath -w` plus PowerShell
  `Copy-Item`, then pass that Windows path to `setfiles`.

Set one file input:

```bash
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js setfiles \
  'input[type=file]' \
  'C:\Users\dhaup\Downloads\CodexUploads\proj\file.png'
```

Set multiple files on one input:

```bash
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js setfiles \
  'input[type=file]' \
  'C:\Users\dhaup\Downloads\CodexUploads\proj\screenshot-1.png' \
  'C:\Users\dhaup\Downloads\CodexUploads\proj\screenshot-2.png'
```

Find or tag file inputs from the pinned tab when the selector is unclear:

```bash
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js eval \
  'Array.from(document.querySelectorAll("input[type=file]")).map((i,n)=>({n,name:i.name,accept:i.accept,id:i.id,hidden:i.hidden}))'
```

If a custom upload button must be opened before the input exists, use pinned `eval` to tag the
button, pinned `click` to trigger it, then `setfiles` after the input appears:

```bash
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js eval \
  '(function(){var b=[...document.querySelectorAll("button,[role=button]")].find(x=>/upload|hochladen/i.test(x.textContent)); if(b){b.id="uploadTrigger"} return !!b})()'
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js click '#uploadTrigger'
```

Only use unpinned CLI upload or coordinate-click flows as a documented emergency fallback after
the pinned controller cannot access the required file input. Record that fallback in the task
summary because it violates the normal mandatory pinned-tab path.

**Common sites — known-working sequences:**

- Google Play Console asset slots open a dialog with a "Hochladen" / "Upload" button that creates a file input. Use pinned `eval`/`click` to open the dialog and pinned `setfiles` with Windows paths for store-listing graphics. Note: for **app-bundle (.aab) release uploads**, do not use the browser at all — the `play-console-release` skill uploads bundles, sets tracks, and writes release notes through the Google Play Android Developer API (`play_publish.py`), which is faster and avoids the flaky bundle-slot filechooser.
- Google Drive's `Neu → Dateien hochladen` triggers a hidden `<input type=file>`. Use pinned `eval` to inspect inputs, then pinned `setfiles`; switch to `Ordner hochladen` only if the file input is folder-specific.
- itch.io: do not upload game builds through the browser — the `itch-release` skill pushes builds with the `butler` CLI (incremental, channel-based, no filechooser). Use the browser only for itch store-page content (title, description, pricing, tags, screenshots, draft/public toggle), which has no API.

Capture visual state:

```bash
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js screenshot /tmp/openclaw-shot.png
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-direct-cdp.mjs screenshot /tmp/openclaw-steam-shot.png 1920 1080
```

The command prints a `MEDIA:<path>` reference. Use `view_image` on that local path when visual verification matters.
The direct helper's optional width and height set an exact CSS-pixel viewport for store or device
captures before taking the screenshot.

### Fast signed-in page dumps

For read-only metrics checks in signed-in Google surfaces, use the pinned controller first:

```bash
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js text
node /home/hod/.codex/skills/openclaw-browser/scripts/pinned-tab-ctl.js screenshot /tmp/google-surface.png
```

If the OpenClaw profile config is stale but Windows Chrome is running with
`--remote-debugging-port=<port>`, run the CDP dump helper with Windows Python. This creates and
closes its own temporary CDP tab and should be treated as a diagnostic fallback, not normal page
control:

```bash
script_win="$(wslpath -w /home/hod/.codex/skills/openclaw-browser/scripts/cdp-dump-windows.py)"
powershell.exe -NoProfile -Command "python '$script_win' 'https://play.google.com/console/' --port 18802 --wait 30 --prefix 'C:/Users/dhaup/AppData/Local/Temp/play-console-page'"
```

If it reports missing Python dependencies, install the small client libraries once:

```bash
powershell.exe -NoProfile -Command "python -m pip install --user requests websocket-client"
```

The helper suppresses the CDP WebSocket origin header and closes its temporary tab by default; use `--keep-open` only when manual inspection is useful.

## Workflow

1. Run the helper script.
2. Set a task-unique `PIN_NAME`; set `OPENCLAW_CDP_URL` too when using a non-default profile.
3. Create or reuse exactly one pinned tab with `pinned-tab-ctl.js create <url>`. For simple local file previews, first copy WSL/Linux static files or report folders to a Windows-local staging folder, then open the copied Windows path outside OpenClaw. For local apps or inspected files, serve them over local HTTP before creating the pinned tab.
4. Use pinned `text`, `url`, `eval`, and `screenshot` to understand visible state before clicking.
5. Use pinned `click`, `click-text`, `type`, and `press` for interaction; rerun pinned `text`/`eval` after navigation or substantial UI changes.
6. For file uploads, use pinned `setfiles` with Windows-local paths, then pinned-click the upload/confirm control if needed.

## Auth Boundary

Do not ask for passwords, 2FA codes, passkeys, recovery answers, or account secrets. If a site requires login, 2FA, passkey, CAPTCHA, or recovery checks, tell the user to complete that step in the visible browser and continue afterward.

For destructive or public actions such as publishing a public YouTube video, confirm the final action with the user unless they already gave explicit publish instructions.

## Troubleshooting

**WARNING — restarting the gateway/bridge can relaunch Windows Chrome and destroy ALL open
tabs** (verified 2026-07-02: a gateway kill + `ensure-openclaw-browser.sh` relaunched the shared
Chrome with one blank tab; 20 tabs from parallel agents were lost, including a mid-edit Play
Console form). Logins survive (profile is on disk) but page state does not. Before any restart:
dump `openclaw browser tabs` so URLs can be restored, and assume other agents' in-flight work
will be interrupted. Restart only when the bridge is actually broken — not as routine hygiene.

**After `npm install -g openclaw@<new>`, the running gateway stays on the old version** (check
with `openclaw gateway status` — it prints CLI vs Gateway versions). To pick up the new version
kill the gateway pid (`cat ~/.openclaw/gateway.pid`) and rerun the ensure helper — accepting the
tab-loss risk above.

If the bridge is unreachable or the browser is stopped, restart the services and rerun the helper script:

```bash
systemctl --user restart openclaw-windows-browser.service
systemctl --user restart openclaw-gateway.service
bash /home/hod/.codex/skills/openclaw-browser/scripts/ensure-openclaw-browser.sh
```

If that still fails on a systemd-enabled WSL session, inspect service logs:

```bash
journalctl --user -u openclaw-windows-browser.service -n 80 --no-pager
journalctl --user -u openclaw-gateway.service -n 80 --no-pager
```

On WSL sessions without a user systemd bus, the helper starts the gateway as a detached process and launches a Windows-side CDP relay. Inspect these logs instead:

```bash
tail -n 80 /home/hod/.openclaw/logs/gateway-run.log
cat /home/hod/.openclaw/gateway.pid
tail -n 80 /tmp/openclaw-windows-relay-18812.log
cat /tmp/openclaw-windows-relay-18812.pid
```

If navigation to a local file fails with an unsupported `file:` protocol or a `chrome-error://chromewebdata/` page, do not retry direct file navigation in OpenClaw. Open the file with Firefox, or serve it over local HTTP and open that URL in OpenClaw.
