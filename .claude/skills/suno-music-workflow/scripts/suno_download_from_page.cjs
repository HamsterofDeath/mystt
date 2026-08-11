#!/usr/bin/env node
/* Download Suno audio by opening the logged-in song page and extracting completed media URLs. */

const fs = require("fs");
const path = require("path");
const http = require("http");
const https = require("https");
const { createRequire } = require("module");

function loadPlaywright() {
  try {
    return require("playwright");
  } catch {
    return createRequire(path.join(process.cwd(), "package.json"))("playwright");
  }
}

const { chromium } = loadPlaywright();

const SONG_ID_RE = /[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/;
const PIN_STATE_DIR = "/tmp/openclaw/pinned-tabs";

function parseArgs(argv) {
  const args = {
    cdpUrl: process.env.SUNO_CDP_URL || "http://172.20.160.1:18801",
    cdpTimeoutMs: Number(process.env.SUNO_CDP_TIMEOUT_MS || 120000),
    outputDir: "/mnt/c/Users/dhaup/Downloads",
    format: "mp3",
    timeoutMs: 180000,
    json: false,
    songs: []
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = () => {
      if (i + 1 >= argv.length) throw new Error(`${arg} requires a value`);
      i += 1;
      return argv[i];
    };
    if (arg === "--cdp-url") args.cdpUrl = next();
    else if (arg === "--cdp-timeout-ms") args.cdpTimeoutMs = Number(next());
    else if (arg === "--output-dir") args.outputDir = next();
    else if (arg === "--format") args.format = next();
    else if (arg === "--timeout-ms") args.timeoutMs = Number(next());
    else if (arg === "--json") args.json = true;
    else if (arg === "-h" || arg === "--help") args.help = true;
    else args.songs.push(arg);
  }
  return args;
}

function usage() {
  return `Usage:
  suno_download_from_page.cjs --output-dir ./public/audio/music filename=<song-id-or-url>

Options:
  --format mp3|m4a      Preferred media type. Default: mp3.
  --timeout-ms <ms>     Wait for completed song-page media. Default: 180000.
  --cdp-url <url>       Browser CDP endpoint. Default: SUNO_CDP_URL or OpenClaw 18801.
  --cdp-timeout-ms <ms> CDP attach timeout. Default: SUNO_CDP_TIMEOUT_MS or 120000.
  --json                Print machine-readable result data.`;
}

function sanitizeName(value) {
  return value.trim().replace(/[\\\/]+/g, "_").replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^[._-]+|[._-]+$/g, "") || "suno_track";
}

function parseSongArg(value) {
  let name = null;
  let raw = value;
  if (value.includes("=")) {
    const parts = value.split("=");
    name = sanitizeName(parts.shift());
    raw = parts.join("=");
  }
  const match = raw.match(SONG_ID_RE);
  if (!match) throw new Error(`could not find a Suno song UUID in: ${value}`);
  return { name, id: match[0].toLowerCase() };
}

function decodeJsonString(value) {
  try {
    return JSON.parse(`"${value.replace(/"/g, '\\"')}"`);
  } catch {
    return value.replace(/\\\//g, "/").replace(/\\u002F/g, "/");
  }
}

function extractMediaFromHtml(html, preferredFormat) {
  const title =
    html.match(/<title>([^<]+)<\/title>/i)?.[1]?.replace(/\s+by\s+.*?\s+\|\s+Suno$/i, "").trim() ||
    "";
  const status = decodeJsonString(html.match(/\\?"status\\?"\s*:\s*\\?"([^"\\]+)\\?"/)?.[1] || "");
  const candidates = [];
  const escapedAudio = html.match(/\\?"audio_url\\?"\s*:\s*\\?"([^"\\]+)\\?"/);
  if (escapedAudio) candidates.push({ url: decodeJsonString(escapedAudio[1]), contentType: "mp3", source: "audio_url" });

  const mediaPattern = /\\?"url\\?"\s*:\s*\\?"([^"\\]+)\\?"\s*,\s*\\?"content_type\\?"\s*:\s*\\?"([^"\\]+)\\?"/g;
  let match;
  while ((match = mediaPattern.exec(html))) {
    candidates.push({ url: decodeJsonString(match[1]), contentType: decodeJsonString(match[2]), source: "media_urls" });
  }

  const preferred = candidates.find((candidate) => candidate.contentType.toLowerCase().includes(preferredFormat));
  return { title, status, candidates, selected: preferred || candidates[0] || null };
}

async function extractCompletedMedia(page, songId, preferredFormat, timeoutMs) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    await page.goto(`https://suno.com/song/${songId}`, { waitUntil: "domcontentloaded", timeout: 45000 });
    await page.waitForTimeout(2500);
    const media = await page.evaluate((format) => {
      const html = document.documentElement.outerHTML;
      return { html };
    }, preferredFormat);
    const extracted = extractMediaFromHtml(media.html, preferredFormat);
    if (extracted.selected && (!extracted.status || extracted.status === "complete")) return extracted;
    await page.waitForTimeout(5000);
  }
  throw new Error(`song page did not expose completed ${preferredFormat} media for ${songId}`);
}

function requestBuffer(url, redirects = 0) {
  return new Promise((resolve, reject) => {
    const client = url.startsWith("https:") ? https : http;
    const request = client.get(
      url,
      {
        headers: {
          "User-Agent": "Mozilla/5.0",
          Accept: "audio/mpeg,audio/*;q=0.9,*/*;q=0.8"
        }
      },
      (response) => {
        if ([301, 302, 303, 307, 308].includes(response.statusCode) && response.headers.location && redirects < 5) {
          response.resume();
          resolve(requestBuffer(new URL(response.headers.location, url).toString(), redirects + 1));
          return;
        }
        const chunks = [];
        response.on("data", (chunk) => chunks.push(chunk));
        response.on("end", () => {
          const buffer = Buffer.concat(chunks);
          resolve({ statusCode: response.statusCode, contentType: response.headers["content-type"] || "", buffer });
        });
      }
    );
    request.setTimeout(180000, () => request.destroy(new Error("download timed out")));
    request.on("error", reject);
  });
}

async function downloadWithRetry(url, timeoutMs) {
  const startedAt = Date.now();
  let lastError = null;
  while (Date.now() - startedAt < timeoutMs) {
    const response = await requestBuffer(url).catch((error) => {
      lastError = error;
      return null;
    });
    if (response && response.statusCode === 200 && /^audio\//i.test(response.contentType) && response.buffer.length > 100000) {
      return response;
    }
    lastError = new Error(`download returned ${response?.statusCode || "error"} ${response?.contentType || ""}`);
    await new Promise((resolve) => setTimeout(resolve, 5000));
  }
  throw lastError || new Error("download failed");
}

async function targetIdOf(context, page) {
  const session = await context.newCDPSession(page);
  try {
    const { targetInfo } = await session.send("Target.getTargetInfo");
    return targetInfo.targetId;
  } finally {
    await session.detach().catch(() => {});
  }
}

async function findPinnedPage(context) {
  const pin = process.env.PIN_NAME || "";
  if (!pin) return null;
  let targetId = "";
  try {
    targetId = JSON.parse(fs.readFileSync(path.join(PIN_STATE_DIR, `${pin}.json`), "utf8")).targetId || "";
  } catch {
    return null;
  }
  for (const page of context.pages()) {
    const id = await targetIdOf(context, page).catch(() => "");
    if (id === targetId) return page;
  }
  return null;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    console.log(usage());
    return;
  }
  if (!["mp3", "m4a"].includes(args.format)) throw new Error("--format must be mp3 or m4a");
  if (!args.songs.length) throw new Error("at least one song id/url is required");

  fs.mkdirSync(args.outputDir, { recursive: true });
  const browser = await chromium.connectOverCDP(args.cdpUrl, { timeout: args.cdpTimeoutMs });
  const context = browser.contexts()[0];
  let page = await findPinnedPage(context) || context.pages().find((candidate) => candidate.url().includes("suno.com/song/")) || context.pages().find((candidate) => candidate.url().includes("suno.com")) || await context.newPage();
  await page.bringToFront();

  const results = [];
  for (const songArg of args.songs) {
    const { name, id } = parseSongArg(songArg);
    const media = await extractCompletedMedia(page, id, args.format, args.timeoutMs);
    const response = await downloadWithRetry(media.selected.url, args.timeoutMs);
    const ext = args.format === "m4a" ? "m4a" : "mp3";
    const output = path.join(args.outputDir, `${name || id}.${ext}`);
    fs.writeFileSync(output, response.buffer);
    results.push({
      id,
      title: media.title,
      output,
      bytes: response.buffer.length,
      contentType: response.contentType,
      mediaUrl: media.selected.url,
      source: media.selected.source
    });
  }

  if (args.json) console.log(JSON.stringify(results, null, 2));
  else {
    for (const result of results) console.log(`wrote ${result.output} (${result.bytes} bytes) from ${result.id}`);
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error.message || error);
    process.exit(1);
  });
