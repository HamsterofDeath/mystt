#!/usr/bin/env node
/* Create an instrumental Suno cover or remix from a source song page. */

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

// Suno's DOM changes often enough that a silent failure is expensive to diagnose.
// SUNO_DEBUG=1 traces the navigation decisions to stderr.
const DEBUG = process.env.SUNO_DEBUG === "1";
const debug = (...parts) => { if (DEBUG) console.error("[suno]", ...parts); };

// The WSL-visible host IP of the OpenClaw relay changes between machines and
// reboots, so a single hardcoded default reliably burns a full connect timeout.
// Probe the known endpoints instead and use the first that answers.
const CDP_CANDIDATES = [
  process.env.SUNO_CDP_URL,
  process.env.OPENCLAW_CDP_URL,
  "http://192.168.112.1:18812",
  "http://172.20.160.1:18801"
].filter(Boolean);

function parseArgs(argv) {
  const args = {
    cdpUrl: "",
    expected: 2,
    timeoutMs: 10 * 60 * 1000,
    mode: "cover",
    workspace: "",
    dryRun: false,
    json: false
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = () => {
      if (i + 1 >= argv.length) throw new Error(`${arg} requires a value`);
      i += 1;
      return argv[i];
    };
    if (arg === "--source") args.source = next();
    else if (arg === "--mode") args.mode = next();
    else if (arg === "--title") args.title = next();
    else if (arg === "--prompt") args.prompt = next();
    else if (arg === "--prompt-file") args.prompt = fs.readFileSync(next(), "utf8").trim();
    else if (arg === "--workspace") args.workspace = next();
    else if (arg === "--expected") args.expected = Number(next());
    else if (arg === "--timeout-ms") args.timeoutMs = Number(next());
    else if (arg === "--cdp-url") args.cdpUrl = next();
    else if (arg === "--dry-run") args.dryRun = true;
    else if (arg === "--json") args.json = true;
    else if (arg === "-h" || arg === "--help") args.help = true;
    else throw new Error(`unknown argument: ${arg}`);
  }
  return args;
}

function usage() {
  return `Usage:
  suno_cover.cjs --source <song-id-or-url> --title "Game - Cover" --prompt "instrumental only, ..."
  suno_cover.cjs --mode remix --source <song-id-or-url> --title "Game - Remix" --prompt "instrumental only, ..."

Difference:
  cover   Preserves the source composition/motif more strongly while changing surface style.
  remix   Gives Suno more freedom to alter arrangement, density, energy, and structure.

The script opens the source song, opens the action menu, chooses Cover or Remix,
fills the create form, and returns the generated /song/ links.

Options:
  --workspace <name>     Select the target Suno workspace before generating.
  --dry-run              Do everything except click Create. Use this to verify the
                         menu/-form navigation after a Suno UI change without
                         spending generation credits.
  --cdp-url <url>        Browser CDP endpoint. Default: probe SUNO_CDP_URL,
                         OPENCLAW_CDP_URL, then the known OpenClaw relays.`;
}

async function connectCdp(explicitUrl) {
  const urls = explicitUrl ? [explicitUrl] : CDP_CANDIDATES;
  const failures = [];
  for (const url of urls) {
    try {
      const browser = await chromium.connectOverCDP(url, { timeout: 15000 });
      return { browser, url };
    } catch (error) {
      failures.push(`${url}: ${error.message.split("\n")[0]}`);
    }
  }
  throw new Error(`could not reach a browser CDP endpoint.\n  ${failures.join("\n  ")}\n` +
    `If every endpoint failed, the OpenClaw bridge is probably down — run\n` +
    `  bash ~/.claude/skills/openclaw-browser/scripts/ensure-openclaw-browser.sh`);
}

function extractSongId(value) {
  const match = String(value || "").match(SONG_ID_RE);
  if (!match) throw new Error(`could not find a Suno song UUID in: ${value}`);
  return match[0].toLowerCase();
}

async function visible(locator) {
  return locator.count().then((count) => count > 0 && locator.first().isVisible()).catch(() => false);
}

async function clickFirstVisible(locators) {
  for (const locator of locators) {
    if (await visible(locator)) {
      await locator.first().click();
      return true;
    }
  }
  return false;
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

async function firstVisibleElement(locator, predicate = () => true) {
  const elements = await locator.all();
  for (const element of elements) {
    if (!(await element.isVisible().catch(() => false))) continue;
    const box = await element.boundingBox().catch(() => null);
    if (!box || !predicate(box, element)) continue;
    return element;
  }
  return null;
}

async function clickVisibleButtonText(page, text, predicate = () => true) {
  const escaped = text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const element = await firstVisibleElement(
    page.locator("button,[role=button]").filter({ hasText: new RegExp(`^${escaped}$`) }),
    predicate
  );
  if (!element) return false;
  await element.click();
  await page.waitForTimeout(500);
  return true;
}

// The song page has several "More menu contents" buttons: the one belonging to the
// song itself, one per row of the right-hand "Similar" list, and one in the bottom
// playbar. Only the song's own overflow is in the main column near the top, so a
// loose position bound still earns its keep here — but keep it generous, and click
// through the DOM to get past the portal overlay.
async function openSourceOverflow(page) {
  for (let attempt = 0; attempt < 6; attempt += 1) {
    await page.evaluate(() => window.scrollTo(0, 0)).catch(() => {});
    const clicked = await page.evaluate(() => {
      const element = [...document.querySelectorAll('[aria-label="More menu contents"]')]
        .find((candidate) => {
          const box = candidate.getBoundingClientRect();
          return box.width > 0 && box.x < 1100 && box.y < 700;
        });
      if (!element) return false;
      element.click();
      return true;
    });
    if (clicked) {
      await page.waitForTimeout(800);
      return true;
    }
    await page.waitForTimeout(1000);
  }
  return false;
}

// Read the workspace the create form will actually save into.
async function currentWorkspace(page) {
  return page.evaluate(() => {
    const lines = document.body.innerText.split(/\n+/).map((line) => line.trim()).filter(Boolean);
    const index = lines.findIndex((line) => line === "Save to...");
    return index >= 0 ? lines[index + 1] || "" : "";
  });
}

// Selecting the target workspace is done through the right-hand Workspaces panel,
// not a dropdown on the create form. The "Save to..." chip only focuses itself
// when clicked; the panel row is what actually rebinds the save target. Rows sit
// at roughly x=720-1660, which the old `box.x < 900 && box.y > 450` predicate
// mostly excluded, and the panel's portal overlay swallows real mouse events, so
// this uses DOM clicks throughout.
async function setWorkspace(page, workspace) {
  if (!workspace) return;
  if ((await currentWorkspace(page)) === workspace) return;

  for (let attempt = 0; attempt < 3; attempt += 1) {
    // Open the Workspaces panel (breadcrumb at the top of the right-hand column).
    await domClickByText(page, "Workspaces");
    await page.waitForTimeout(1500);

    // Click the row itself, not the bare label: the label is a <span> with no
    // handler, so walk up to the row-sized ancestor that carries the click.
    const picked = await page.evaluate((name) => {
      const candidates = [...document.querySelectorAll("*")]
        .filter((element) => element.children.length === 0
          && element.textContent.trim() === name
          && element.getBoundingClientRect().width > 0)
        .map((label) => ({ label, row: label.closest('[role="button"]') }))
        .filter(({ row }) => row && row.getBoundingClientRect().width > 0)
        .sort((a, b) => b.row.getBoundingClientRect().width - a.row.getBoundingClientRect().width);
      const target = candidates[0]?.row;
      if (!target) return false;
      target.click();
      return true;
    }, workspace);

    if (picked) {
      await page.waitForTimeout(2000);
      if ((await currentWorkspace(page)) === workspace) return;
    }
    await page.waitForTimeout(1000);
  }

  const available = await page.evaluate(() =>
    [...document.querySelectorAll("*")]
      .filter((element) => element.children.length === 0 && /Songs ·/.test(element.textContent))
      .map((element) => (element.previousElementSibling || {}).textContent || "")
      .map((text) => text.trim()).filter(Boolean));
  throw new Error(`could not select workspace "${workspace}". Visible workspaces: ${available.join(", ") || "none"}`);
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

async function openSourceSong(context, id, preferredPage = null) {
  let page = preferredPage || context.pages().find((candidate) => candidate.url().includes(`suno.com/song/${id}`));
  if (!page) page = context.pages().find((candidate) => candidate.url().includes("suno.com")) || await context.newPage();
  await page.bringToFront();
  await page.goto(`https://suno.com/song/${id}`, { waitUntil: "domcontentloaded", timeout: 45000 });
  await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(4000);
  await page.evaluate(() => window.scrollTo(0, 0)).catch(() => {});
  await page.keyboard.press("Escape").catch(() => {});
  return page;
}

// Click an element by its exact visible text, anywhere on the page, using a DOM
// click. Suno renders its menus inside a `data-base-ui-portal` layer that also
// installs a `data-base-ui-inert` presentation overlay; that overlay intercepts
// Playwright's real mouse events, so a trusted click can never land. A DOM click
// is the only thing that reliably works against these menus.
async function domClickByText(page, text) {
  return page.evaluate((wanted) => {
    const element = [...document.querySelectorAll('button,[role="button"],[role="menuitem"],[role="option"]')]
      .find((candidate) => candidate.textContent.trim() === wanted
        && candidate.getBoundingClientRect().width > 0);
    if (!element) return false;
    element.click();
    return true;
  }, text);
}

// Suno v5.5 restructured this. There is no longer a "Remix" *action*: the button
// labelled `Remix` opens a menu whose items are Cover / Extend / Reuse Prompt /
// Reverse / Adjust Speed. Both --mode cover and --mode remix therefore go through
// the same menu; they differ only in the prompt freedom the caller writes.
//
// The previous implementation also filtered menu items to `box.x < 1000 && box.y
// < 800`. v5.5 renders that menu in the right-hand column at roughly x=1520,
// y=740-900, so every candidate was discarded and the run failed later with the
// misleading "cover action did not reach a Suno create form". Do not reintroduce
// position predicates here — the menu's location is not stable across versions.
// The action menu is NOT rendered into a floating portal — its items are plain
// `<button data-react-aria-pressable>` elements inside anonymous divs in the
// right-hand panel, with no role="menu" ancestor to scope to. So menu items can
// only be told apart from the rest of the page by their text.
//
// That creates one trap: the button that OPENS the menu is itself labelled
// "Remix", so for --mode remix a naive text click just toggles the menu shut.
// Mark the opener when clicking it and exclude it when picking an action.
const OPENER_MARK = "data-suno-opener";

async function openActionMenu(page) {
  return page.evaluate((mark) => {
    document.querySelectorAll(`[${mark}]`).forEach((element) => element.removeAttribute(mark));
    const pill = [...document.querySelectorAll('button,[role="button"]')]
      .find((candidate) => candidate.textContent.trim() === "Remix"
        && candidate.getBoundingClientRect().width > 0);
    if (!pill) return false;
    pill.setAttribute(mark, "1");
    pill.click();
    return true;
  }, OPENER_MARK);
}

async function clickAction(page, text) {
  return page.evaluate(([wanted, mark]) => {
    const element = [...document.querySelectorAll('button,[role="button"],[role="menuitem"],[role="option"]')]
      .find((candidate) => candidate.textContent.trim() === wanted
        && candidate.getBoundingClientRect().width > 0
        && !candidate.hasAttribute(mark));
    if (!element) return false;
    element.click();
    return true;
  }, [text, OPENER_MARK]);
}

// Short visible button labels, for diagnostics when an action cannot be found.
async function listActionCandidates(page) {
  return page.evaluate(() => [...new Set(
    [...document.querySelectorAll('button,[role="button"],[role="menuitem"]')]
      .filter((element) => element.getBoundingClientRect().width > 0)
      .map((element) => element.textContent.trim())
      .filter((text) => text && text.length < 24 && !/^\p{Extended_Pictographic}/u.test(text))
  )]);
}

// Suno v5.5 restructured this. There is no longer a "Remix" *action*: the button
// labelled `Remix` opens a menu whose items are Cover / Extend / Reuse Prompt /
// Reverse / Adjust Speed. Both --mode cover and --mode remix therefore go through
// the same menu and land on the same Cover form; they differ only in how much
// freedom the caller's prompt gives Suno.
//
// The previous implementation filtered menu items to `box.x < 1000 && box.y <
// 800`. v5.5 renders that menu in the right-hand column at roughly x=1520,
// y=740-900, so every candidate was discarded and the run failed later with the
// misleading "cover action did not reach a Suno create form". Do not reintroduce
// position predicates here — the menu's location is not stable across versions.
// The song page hydrates well after domcontentloaded, so a fixed settle time is a
// coin flip — a cold tab needs noticeably longer than one already on Suno. Poll
// for the control instead of guessing.
// Only two controls can actually open the action menu: the `Remix` pill, which
// mounts at the foot of the right-hand panel and therefore appears only after the
// async "Similar" list has loaded, and the song's own overflow button in the main
// column. Every row of the Similar list also has an overflow button, so an
// any-overflow check reports ready while nothing usable is on screen yet — which
// is exactly how a cold tab used to fail with "could not open the menu".
async function waitForSongPageReady(page, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const ready = await page.evaluate(() => {
      const hasRemix = [...document.querySelectorAll('button,[role="button"]')]
        .some((element) => element.textContent.trim() === "Remix"
          && element.getBoundingClientRect().width > 0);
      const hasOwnOverflow = [...document.querySelectorAll('[aria-label="More menu contents"]')]
        .some((element) => {
          const box = element.getBoundingClientRect();
          return box.width > 0 && box.x < 1100 && box.y < 700;
        });
      return hasRemix || hasOwnOverflow;
    });
    if (ready) return true;
    await page.waitForTimeout(1000);
  }
  return false;
}

async function selectSourceAction(page, mode) {
  // Preference order for the menu item that derives a new song from this one.
  const wanted = mode === "remix" ? ["Remix", "Cover"] : ["Cover"];

  if (!await waitForSongPageReady(page)) {
    throw new Error(`the Suno song page never finished loading its controls: ${page.url()}`);
  }

  // Suno navigates to the create form client-side and can take well over three
  // seconds. Poll instead of sleeping a fixed amount: a premature "it didn't
  // work" retry lands the next click on the create page, where the same labels
  // mean different things.
  const reachedCreateForm = async (timeoutMs = 20000) => {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (page.url().includes("/create")) return true;
      await page.waitForTimeout(500);
    }
    return false;
  };

  let lastItems = [];
  for (let attempt = 0; attempt < 4; attempt += 1) {
    if (page.url().includes("/create")) return;
    await page.evaluate(() => window.scrollTo(0, 0)).catch(() => {});
    await page.keyboard.press("Escape").catch(() => {});
    await page.waitForTimeout(500);

    // Open the action menu. Prefer the "Remix" pill; the song's own overflow menu
    // is the fallback for builds that do not render the pill.
    const viaPill = await openActionMenu(page);
    const opened = viaPill || (await openSourceOverflow(page));
    debug(`attempt ${attempt}: opened=${opened} viaPill=${viaPill} url=${page.url()}`);
    if (!opened) {
      await page.waitForTimeout(2000);
      continue;
    }
    await page.waitForTimeout(2000);

    lastItems = await listActionCandidates(page);
    debug(`attempt ${attempt}: candidates = ${JSON.stringify(lastItems.slice(0, 20))}`);

    for (const label of wanted) {
      if (await clickAction(page, label)) {
        debug(`clicked action "${label}"`);
        if (await reachedCreateForm()) return;
        debug(`action "${label}" did not navigate to /create (at ${page.url()})`);
      }
    }
    await page.waitForTimeout(1500);
  }
  throw new Error("could not reach the Suno Cover/Remix action from the source song. " +
    `Last menu items seen: ${lastItems.length ? lastItems.join(", ") : "(none — the menu never opened)"}. ` +
    "Re-run with SUNO_DEBUG=1 to trace, and check whether Suno renamed the action.");
}

async function waitForCreateForm(context, preferredPage = null) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < 45000) {
    const pages = context.pages();
    const candidates = [preferredPage, pages.find((candidate) => candidate.url().includes("suno.com/create")), pages[pages.length - 1]]
      .filter(Boolean)
      .filter((page, index, all) => all.indexOf(page) === index);
    for (const page of candidates) {
      await page.bringToFront().catch(() => {});
      const body = await page.locator("body").innerText({ timeout: 5000 }).catch(() => "");
      const hasPrompt = await firstVisibleElement(page.locator("textarea")).then(Boolean).catch(() => false);
      const hasCreate = await visible(page.getByRole("button", { name: /^Create( song)?$/ }))
        || await visible(page.locator("button").filter({ hasText: /^Create$/ }));
      if (hasPrompt && hasCreate && /Prompt|Styles|Lyrics|Instrumental/i.test(body)) return page;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error("cover action did not reach a Suno create form");
}

// Suno's create form is React-controlled: assigning `.value` or using Playwright's
// fill() on a field it re-renders can leave the visible text set but the internal
// state empty, so the generation silently uses the old prompt. Go through the
// native value setter and dispatch the events React listens for.
const setReactValue = (page, handleSelector, value) => page.evaluate(([selector, text]) => {
  const element = typeof selector === "number"
    ? document.querySelectorAll("textarea")[selector]
    : document.querySelector(selector);
  if (!element) return false;
  const proto = element.tagName === "TEXTAREA"
    ? window.HTMLTextAreaElement.prototype
    : window.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value").set.call(element, text);
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
  return true;
}, [handleSelector, value]);

async function fillCoverForm(page, args) {
  // Title: the field is an input on some versions and a textarea on others.
  const titled = await page.evaluate((title) => {
    const element = [...document.querySelectorAll("input,textarea")]
      .find((candidate) => /Song Title/i.test(candidate.placeholder || "")
        && candidate.getBoundingClientRect().width > 0);
    if (!element) return false;
    const proto = element.tagName === "TEXTAREA"
      ? window.HTMLTextAreaElement.prototype
      : window.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(element, title);
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }, args.title);
  await page.waitForTimeout(500);

  // Instrumental. A cover inherits the source's instrumental setting, and v5.5
  // states that inline ("This song will be instrumental, with no vocals or
  // lyrics.") rather than exposing a checked radio. Treat that copy as
  // authoritative and only fail if the form neither says it nor offers the
  // control — the old code threw on every v5.5 cover.
  const declaresInstrumental = await page.evaluate(() =>
    /will be instrumental/i.test(document.body.innerText));
  if (!declaresInstrumental) {
    const instrumental = await firstVisibleElement(
      page.locator('[role="radio"],[role="tab"],button').filter({ hasText: /^Instrumental$/ })
    );
    if (!instrumental) throw new Error("could not find Suno Instrumental option or confirmation");
    if ((await instrumental.getAttribute("aria-checked")) !== "true") {
      await instrumental.evaluate((element) => element.click());
      await page.waitForTimeout(800);
    }
    const confirmed = await page.evaluate(() => /will be instrumental/i.test(document.body.innerText));
    if (!confirmed && (await instrumental.getAttribute("aria-checked")) !== "true") {
      throw new Error("Suno Instrumental option did not enable");
    }
  }

  // Styles prompt. The create form has several textareas — lyrics, styles, an
  // "exclude styles" box, and a hidden one. The first *visible* textarea is not
  // the styles box on v5.5, so the old first-match loop wrote the prompt into the
  // lyrics field. Identify the styles box by its placeholder (a comma-separated
  // list of genres) or by the prompt a cover inherits from its source.
  const stylesIndex = await page.evaluate(() => {
    const textareas = [...document.querySelectorAll("textarea")];
    let byInherited = -1;
    let byPlaceholder = -1;
    textareas.forEach((textarea, index) => {
      const box = textarea.getBoundingClientRect();
      if (box.width < 100 || box.height < 40) return;
      if ((textarea.value || "").trim()) byInherited = index;
      const placeholder = textarea.placeholder || "";
      if (/denpa song|surf music|glitch core|syncopated/i.test(placeholder)
        || (placeholder.includes(",") && !/song about|describe the sound/i.test(placeholder))) {
        byPlaceholder = index;
      }
    });
    return byInherited >= 0 ? byInherited : byPlaceholder;
  });
  if (stylesIndex < 0) throw new Error("could not identify the Suno styles textarea on the create form");
  if (!await setReactValue(page, stylesIndex, args.prompt)) {
    throw new Error("could not write the prompt into the Suno styles textarea");
  }
  await page.waitForTimeout(500);

  const written = await page.evaluate((index) =>
    (document.querySelectorAll("textarea")[index].value || "").trim(), stylesIndex);
  if (written !== args.prompt.trim()) {
    throw new Error("the Suno styles textarea did not accept the prompt");
  }
  return { titled };
}

// "Create" is ambiguous on this page: the left sidebar has a Create nav entry and
// the workspace panel has "Create new workspace". Pick the enabled submit button
// in the composer column, which is the widest / lowest of the exact matches.
async function clickCreate(page) {
  const clicked = await page.evaluate(() => {
    const exact = [...document.querySelectorAll('button,[role="button"]')]
      .filter((element) => {
        const text = element.textContent.trim();
        return (text === "Create" || text === "Create song")
          && element.getBoundingClientRect().width > 0
          && !element.disabled
          && element.getAttribute("aria-disabled") !== "true";
      });
    if (!exact.length) return false;
    // The composer's submit button is the largest of them.
    exact.sort((a, b) => b.getBoundingClientRect().width - a.getBoundingClientRect().width);
    exact[0].click();
    return true;
  });
  if (!clicked) throw new Error("could not find an enabled Suno Create button");
  await page.waitForTimeout(1500);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    console.log(usage());
    return;
  }
  if (!["cover", "remix"].includes(args.mode)) throw new Error("--mode must be cover or remix");
  if (!args.source || !args.title || !args.prompt) throw new Error("--source, --title, and --prompt/--prompt-file are required");

  const sourceId = extractSongId(args.source);
  const { browser, url: cdpUrl } = await connectCdp(args.cdpUrl);
  const context = browser.contexts()[0];
  const pinnedPage = await findPinnedPage(context);
  const sourcePage = await openSourceSong(context, sourceId, pinnedPage);

  await selectSourceAction(sourcePage, args.mode);
  const createPage = await waitForCreateForm(context, sourcePage);
  await setWorkspace(createPage, args.workspace);
  const { titled } = await fillCoverForm(createPage, args);

  if (args.dryRun) {
    const result = {
      sourceId,
      mode: args.mode,
      title: args.title,
      dryRun: true,
      cdpUrl,
      reachedCreateForm: createPage.url(),
      titleFieldFound: titled,
      workspace: await currentWorkspace(createPage),
      links: []
    };
    console.log(JSON.stringify(result, null, 2));
    return;
  }

  // Baseline the song list on the SAME page the results will appear on. The song
  // page links to only a handful of songs while the create page lists the whole
  // workspace, so baselining on the song page makes every existing workspace
  // track look "new".
  const before = new Set((await getSongLinks(createPage)).map((link) => link.id));
  debug(`baseline: ${before.size} song links on the create page`);

  await clickCreate(createPage);

  // Prefer links whose card text matches the title, but do not require it: Suno
  // renders the cards before applying the title, so an exact-title filter alone
  // can wait out the whole timeout on a generation that actually succeeded.
  const startedAt = Date.now();
  let newLinks = [];
  while (Date.now() - startedAt < args.timeoutMs) {
    await createPage.waitForTimeout(5000);
    const fresh = (await getSongLinks(createPage))
      .filter((link) => !before.has(link.id) && link.id !== sourceId);
    const titled = fresh.filter((link) => link.text.trim() === args.title);
    newLinks = titled.length >= args.expected ? titled : fresh;
    if (titled.length >= args.expected) break;
    if (fresh.length >= args.expected && Date.now() - startedAt > 60000) break;
  }

  const result = {
    sourceId,
    mode: args.mode,
    title: args.title,
    prompt: args.prompt,
    cdpUrl,
    links: newLinks.map((link) => ({ id: link.id, url: link.href, text: link.text }))
  };
  if (args.json) console.log(JSON.stringify(result, null, 2));
  else {
    console.log(`Created ${result.links.length} Suno ${args.mode} link(s) from ${sourceId}:`);
    for (const link of result.links) console.log(`${link.id} ${link.url}`);
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error.message || error);
    process.exit(1);
  });
