#!/usr/bin/env node
/* Generate instrumental Suno songs through the logged-in OpenClaw Chrome UI. */

const fs = require("fs");
const path = require("path");
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
    expected: 2,
    instrumental: true,
    timeoutMs: 10 * 60 * 1000,
    workspace: "",
    json: false
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
    else if (arg === "--title") args.title = next();
    else if (arg === "--prompt") args.prompt = next();
    else if (arg === "--prompt-file") args.prompt = fs.readFileSync(next(), "utf8").trim();
    else if (arg === "--workspace") args.workspace = next();
    else if (arg === "--expected") args.expected = Number(next());
    else if (arg === "--timeout-ms") args.timeoutMs = Number(next());
    else if (arg === "--allow-vocals") args.instrumental = false;
    else if (arg === "--json") args.json = true;
    else if (arg === "-h" || arg === "--help") args.help = true;
    else throw new Error(`unknown argument: ${arg}`);
  }
  return args;
}

function usage() {
  return `Usage:
  suno_generate.cjs --title "Game - Menu" --prompt "instrumental only, ..." [options]

Options:
  --prompt-file <path>   Read the prompt from a file instead of --prompt.
  --workspace <name>     Click a visible Suno workspace before generating.
  --expected <n>         Number of new song links to wait for. Default: 2.
  --timeout-ms <ms>      Wait limit for generated links. Default: 600000.
  --cdp-url <url>        Browser CDP endpoint. Default: SUNO_CDP_URL or OpenClaw 18801.
  --cdp-timeout-ms <ms>  CDP attach timeout. Default: SUNO_CDP_TIMEOUT_MS or 120000.
  --allow-vocals         Do not force Instrumental mode. Avoid this for game music.
  --json                 Print only machine-readable JSON.`;
}

function extractSongId(url) {
  const match = String(url).match(SONG_ID_RE);
  return match ? match[0].toLowerCase() : null;
}

async function getSongLinks(page) {
  const links = await page.evaluate(() =>
    [...document.querySelectorAll('a[href*="/song/"]')].map((anchor) => ({
      href: anchor.href,
      text: (anchor.innerText || "").trim()
    }))
  );
  const seen = new Set();
  return links
    .map((link) => ({ ...link, id: (link.href.match(/[0-9a-fA-F-]{36}/) || [])[0]?.toLowerCase() }))
    .filter((link) => link.id && !seen.has(link.id) && seen.add(link.id));
}

async function visible(locator) {
  return locator.count().then((count) => count > 0 && locator.first().isVisible()).catch(() => false);
}

async function clickIfVisible(locator) {
  if (await visible(locator)) {
    await locator.first().click();
    return true;
  }
  return false;
}

async function selectedSaveWorkspace(page) {
  const bodyText = await page.locator("body").innerText({ timeout: 5000 }).catch(() => "");
  const lines = bodyText.split(/\n+/).map((line) => line.trim()).filter(Boolean);
  const saveIndex = lines.findIndex((line) => line === "Save to...");
  return saveIndex >= 0 ? lines[saveIndex + 1] || "" : "";
}

async function selectSaveWorkspace(page, workspace) {
  const current = await selectedSaveWorkspace(page);
  if (current === workspace) return true;
  const opened = await page.evaluate(() => {
    const candidates = [...document.querySelectorAll("button,[role=button],div")]
      .map((element) => {
        const rect = element.getBoundingClientRect();
        return {
          element,
          text: (element.innerText || element.textContent || "").trim(),
          rect,
          visible: !!(rect.width && rect.height)
        };
      })
      .filter((item) => item.visible
        && item.rect.x >= 180 && item.rect.x < 700
        && item.rect.y >= 500 && item.rect.y < 900
        && item.text.startsWith("Save to..."));
    const target = candidates.sort((a, b) => (a.rect.width * a.rect.height) - (b.rect.width * b.rect.height))[0];
    if (!target) return false;
    target.element.click();
    return true;
  });
  if (!opened) return false;
  await page.waitForTimeout(1000);
  const clicked = await page.evaluate((name) => {
    const candidates = [...document.querySelectorAll("button,[role=button],[role=option],li,div,span")]
      .map((element) => {
        const rect = element.getBoundingClientRect();
        return {
          element,
          text: (element.innerText || element.textContent || "").trim(),
          rect,
          visible: !!(rect.width && rect.height)
        };
      })
      .filter((item) => item.visible
        && item.text.startsWith(`${name} (`)
        && item.text.endsWith(" clips)"));
    const target = candidates.sort((a, b) => (a.rect.width * a.rect.height) - (b.rect.width * b.rect.height))[0];
    if (!target) return false;
    target.element.click();
    return true;
  }, workspace);
  if (!clicked) return false;
  await page.waitForTimeout(1200);
  return await selectedSaveWorkspace(page) === workspace;
}

async function setWorkspace(page, workspace) {
  if (!workspace) return;
  const escaped = workspace.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  if (await selectedSaveWorkspace(page) === workspace) return;
  if (await selectSaveWorkspace(page, workspace)) return;
  const selected = page.locator("button").filter({ hasText: new RegExp(`^${workspace.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`) });
  if (await visible(selected)) return;
  const saveButtons = await page.locator("button").all();
  for (const button of saveButtons) {
    if (await button.isVisible().catch(() => false)) {
      const box = await button.boundingBox().catch(() => null);
      const text = ((await button.innerText().catch(() => "")) || "").trim();
      if (box && box.x < 650 && box.y > 500 && text) {
        await button.click();
        await page.waitForTimeout(500);
        break;
      }
    }
  }
  const pickerOption = page.getByText(new RegExp(`^${escaped}\\s*\\(`));
  if (await clickIfVisible(pickerOption)) {
    await page.waitForTimeout(800);
    return;
  }
  const candidates = [
    page.getByRole("button", { name: new RegExp(`^${workspace.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`) }),
    page.getByText(workspace, { exact: true })
  ];
  for (const locator of candidates) {
    if (await clickIfVisible(locator)) {
      await page.waitForTimeout(800);
      return;
    }
  }
  throw new Error(`workspace not visible: ${workspace}`);
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

async function ensureCreatePage(context) {
  let page = await findPinnedPage(context);
  if (page && !page.url().includes("suno.com/create")) {
    await page.bringToFront();
    await page.goto("https://suno.com/create", { waitUntil: "domcontentloaded", timeout: 45000 });
  }
  if (!page) page = context.pages().find((candidate) => candidate.url().includes("suno.com/create"));
  if (!page) page = await context.newPage();
  await page.bringToFront();
  if (!page.url().includes("suno.com/create")) {
    await page.goto("https://suno.com/create", { waitUntil: "domcontentloaded", timeout: 45000 });
  }
  await page.waitForTimeout(2500);
  return page;
}

async function assertLoggedIn(page) {
  const body = await page.locator("body").innerText({ timeout: 15000 });
  if (/Log in|Join Suno for free/i.test(body) && !/Pro Plan|Upgrade to Premier|d_haupt82/i.test(body)) {
    throw new Error("Suno page is not logged in; use the main OpenClaw profile or copy login state first.");
  }
}

async function fillVisibleInputs(page, args) {
  await clickIfVisible(page.getByRole("tab", { name: "Advanced" }));
  await page.waitForTimeout(500);

  if (args.instrumental) {
    await page.waitForTimeout(1000);
    const radios = await page.locator('[role="radio"]').filter({ hasText: /^Instrumental$/ }).all();
    let instrumental = null;
    for (const radio of radios) {
      if (await radio.isVisible().catch(() => false)) { instrumental = radio; break; }
    }
    if (!instrumental) throw new Error("could not find Suno Instrumental option");
    if (await instrumental.getAttribute("aria-checked") !== "true") {
      await instrumental.evaluate((element) => element.click());
      await page.waitForTimeout(500);
    }
    if (await instrumental.getAttribute("aria-checked") !== "true") {
      throw new Error("Suno Instrumental option did not enable");
    }
  }

  const titleInputs = await page.locator('input[placeholder="Song Title (Optional)"]').all();
  for (const input of titleInputs) {
    if (await input.isVisible().catch(() => false)) await input.fill(args.title);
  }

  const textareas = await page.locator("textarea").all();
  let filled = false;
  for (const textarea of textareas) {
    if (await textarea.isVisible().catch(() => false)) {
      await textarea.fill(args.prompt);
      filled = true;
      break;
    }
  }
  if (!filled) throw new Error("could not find visible Suno prompt textarea");
}

async function clickCreate(page) {
  const candidates = [
    page.getByRole("button", { name: "Create song" }),
    page.getByRole("button", { name: /^Create$/ }),
    page.locator("button").filter({ hasText: /^Create$/ })
  ];
  for (const locator of candidates) {
    if (await visible(locator)) {
      await locator.last().scrollIntoViewIfNeeded();
      await locator.last().click();
      return;
    }
  }
  throw new Error("could not find Suno Create button");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    console.log(usage());
    return;
  }
  if (!args.title || !args.prompt) throw new Error("--title and --prompt/--prompt-file are required");

  const browser = await chromium.connectOverCDP(args.cdpUrl, { timeout: args.cdpTimeoutMs });
  const context = browser.contexts()[0];
  const page = await ensureCreatePage(context);
  await assertLoggedIn(page);
  await setWorkspace(page, args.workspace);

  const before = new Set((await getSongLinks(page)).map((link) => link.id));
  await fillVisibleInputs(page, args);
  await clickCreate(page);

  const startedAt = Date.now();
  let newLinks = [];
  while (Date.now() - startedAt < args.timeoutMs) {
    await page.waitForTimeout(5000);
    newLinks = (await getSongLinks(page)).filter((link) => !before.has(link.id));
    if (newLinks.length >= args.expected) break;
  }

  const result = {
    title: args.title,
    prompt: args.prompt,
    workspace: args.workspace || null,
    links: newLinks.map((link) => ({ id: link.id, url: link.href, text: link.text }))
  };
  if (args.json) console.log(JSON.stringify(result, null, 2));
  else {
    console.log(`Generated ${result.links.length} Suno link(s):`);
    for (const link of result.links) console.log(`${link.id} ${link.url}`);
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error.message || error);
    process.exit(1);
  });
