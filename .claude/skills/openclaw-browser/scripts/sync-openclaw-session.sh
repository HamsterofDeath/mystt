#!/usr/bin/env bash
# Best-effort session (cookie) top-up between two OpenClaw browser profiles over CDP.
#
# Reads cookies from a source profile (already logged in) and injects them into a
# destination profile. Cookies read over CDP are already DECRYPTED, so this bypasses
# Chrome's App-Bound Encryption (ABE) that makes a raw profile-dir copy log out.
#
# SCOPE / LIMITATION (verified 2026-07-01):
#   - Works for ordinary cookie-auth sites (itch.io, most dashboards).
#   - Does NOT restore a Google login. Google accounts use device-bound sessions
#     (DBSC): auth cookies are bound to the source profile's TPM key and will only
#     get you to the account chooser ("confirmidentifier"), not a signed-in session.
#     For Google, use a PERSISTENT profile and sign in once (see prepare-isolated-browser.sh).
#
# Values are never printed — only counts.
#
# Usage:
#   sync-openclaw-session.sh --from winchrome --to agent1 [--domains 'itch.io,google.']
#   sync-openclaw-session.sh --from-url http://HOST:18812 --to-url http://HOST:18854
set -euo pipefail

FROM="" TO="" FROM_URL="" TO_URL="" DOMAINS=""
die() { echo "error: $*" >&2; exit 1; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --from) FROM="${2:-}"; shift 2 ;;
    --to) TO="${2:-}"; shift 2 ;;
    --from-url) FROM_URL="${2:-}"; shift 2 ;;
    --to-url) TO_URL="${2:-}"; shift 2 ;;
    --domains) DOMAINS="${2:-}"; shift 2 ;;   # comma-separated substrings; empty = all cookies
    -h|--help) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

command -v node >/dev/null 2>&1 || die "node required"

# Resolve cdp URLs from openclaw.json when profile names were given.
resolve_url() {
  local prof="$1"
  node - "$prof" <<'NODE'
const fs=require("fs");
const p=`${process.env.HOME}/.openclaw/openclaw.json`;
const c=JSON.parse(fs.readFileSync(p,"utf8"));
const e=(c.browser&&c.browser.profiles&&c.browser.profiles[process.argv[2]])||{};
process.stdout.write(e.cdpUrl||"");
NODE
}
[[ -n "$FROM_URL" ]] || { [[ -n "$FROM" ]] || die "--from or --from-url required"; FROM_URL="$(resolve_url "$FROM")"; }
[[ -n "$TO_URL" ]]   || { [[ -n "$TO" ]]   || die "--to or --to-url required";   TO_URL="$(resolve_url "$TO")"; }
[[ -n "$FROM_URL" && -n "$TO_URL" ]] || die "could not resolve cdp URLs (from='$FROM_URL' to='$TO_URL')"

# Locate a playwright-core install (OpenClaw ships none; reuse a project's node_modules).
PW_PATH="${PW_PATH:-}"
if [[ -z "$PW_PATH" ]]; then
  for d in "$HOME"/IdeaProjects/*/node_modules/playwright-core "$HOME"/IdeaProjects/*/*/node_modules/playwright-core; do
    [[ -d "$d" ]] && { PW_PATH="$d"; break; }
  done
fi
[[ -n "$PW_PATH" && -d "$PW_PATH" ]] || die "playwright-core not found; set PW_PATH=/path/to/playwright-core"

PW_PATH="$PW_PATH" node - "$FROM_URL" "$TO_URL" "$DOMAINS" <<'NODE'
const { chromium } = require(process.env.PW_PATH);
const [srcUrl, dstUrl, domainsCsv] = process.argv.slice(2);
const filters = (domainsCsv||"").split(",").map(s=>s.trim()).filter(Boolean);
(async () => {
  const src = await chromium.connectOverCDP(srcUrl);
  const dst = await chromium.connectOverCDP(dstUrl);
  const all = await src.contexts()[0].cookies();
  const keep = filters.length ? all.filter(c => filters.some(f => c.domain.includes(f))) : all;
  await dst.contexts()[0].addCookies(keep);
  console.log(`source cookies: ${all.length}, copied: ${keep.length}`);
  process.exit(0);
})().catch(e => { console.error("sync failed:", e.message); process.exit(1); });
NODE

echo "note: reload the target tab to pick up the cookies; Google logins need a one-time sign-in (DBSC), not a copy."
