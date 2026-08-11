---
name: open-in-browser
description: Open a local file or URL in the user's visible browser from WSL/Linux, especially HTML reports or downloaded diagnostics. Use when the user says to open, view, show in browser, or open an HTML file. Prefer the Windows default browser on this workspace and avoid WSL UNC browser-launch failures.
---

# Open In Browser

Use this skill when the user asks to open a local file or URL in a browser.

## Default Workflow

1. If the target is a local file, make sure it exists.
2. Run the bundled helper:

```bash
/home/hod/.codex/skills/open-in-browser/scripts/open_in_browser.sh /absolute/path/to/file.html
```

For a URL:

```bash
/home/hod/.codex/skills/open-in-browser/scripts/open_in_browser.sh 'https://example.com'
```

3. Tell the user the original path, and if a Linux-side file had to be copied, the Windows copy path.

## WSL Rules

- Prefer the Windows default browser through PowerShell `Start-Process`.
- Do not use `xdg-open`, `gio open`, `sensible-browser`, or Linux Chrome first when running under WSL and the user expects a visible Windows browser.
- Do not use `cmd.exe /c start` from a WSL repository directory. Windows can reject UNC current directories such as `\\wsl.localhost\...`.
- Do not try to open Linux filesystem paths as WSL UNC paths directly. Copy files outside `/mnt/<drive>/...` into `C:\Users\d.haupt\Downloads\codex-open\` and open that copy.
- Run Windows open commands from `/mnt/c/Windows/System32` when available.

## Fallbacks

- If PowerShell is unavailable, try `wslview` for URLs or Windows-mounted files.
- If no Windows opener is available, try `xdg-open` only as a last resort.
- If every opener fails, return the exact file path and the error, without implying the file is broken.
