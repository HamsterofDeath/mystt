---
name: open-in-firefox
description: Open local files or URLs in the user's visible Windows Firefox from WSL/Linux. Use when the user explicitly asks for Firefox, asks to open an HTML/report/file in Firefox, or describes the workflow "create a file, copy it to my Windows Startup folder, and open it in Firefox."
---

# Open In Firefox

Use this skill when Firefox is required instead of the Windows default browser.

## Workflow

1. If the user asks to create content, create the file first using normal editing rules.
2. For a local file, pass its absolute path to the bundled helper:

```bash
/home/hod/.codex/skills/open-in-firefox/scripts/open_in_firefox.sh /absolute/path/to/file.html
```

3. For a URL, pass the URL:

```bash
/home/hod/.codex/skills/open-in-firefox/scripts/open_in_firefox.sh 'https://example.com'
```

4. Tell the user the original path and the Windows Startup-folder copy path printed by the helper.

## Behavior

- For local files, the helper copies the file into the Windows Startup folder returned by PowerShell:
  `C:\Users\d.haupt\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup`
- Copied files are named `codex-firefox-<sanitized-original-name>` and overwritten on repeated opens.
- The helper opens the copied file with Windows Firefox, normally:
  `C:\Program Files\Mozilla Firefox\firefox.exe`
- For URLs, the helper opens Firefox directly and does not create a Startup-folder copy.

## WSL Rules

- Use the helper instead of `xdg-open`, `wslview`, `gio open`, or the default-browser skill when the user asked for Firefox.
- Do not open Linux filesystem paths as WSL UNC paths directly. The helper stages local files in the Windows Startup folder first.
- Run Windows PowerShell commands from `/mnt/c/Windows/System32` when available to avoid UNC current-directory failures.
- If the helper fails, report the exact command output and do not imply the file itself is broken.

## Useful Options

Use `--copy-only` when validating or when the user asks only to stage the file:

```bash
/home/hod/.codex/skills/open-in-firefox/scripts/open_in_firefox.sh --copy-only /absolute/path/to/file.html
```
