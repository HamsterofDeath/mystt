#!/usr/bin/env node
// Pinned-tab controller: 1 agent = 1 tab on the shared OpenClaw Chrome, over raw CDP.
//
// Why: the openclaw CLI has no per-command tab targeting — every CLI command acts on
// the profile's single ACTIVE tab, so parallel agents redirect each other mid-flow.
// This script pins a tab by CDP targetId (survives all navigations; window.name does
// NOT — Chrome clears it on cross-site navigation) and finds it again on every call,
// regardless of which tab other agents focus.
//
// Each agent picks a unique pin name:
//   export PIN_NAME=dtb-upload            # your agent's pin (default: "default")
//   export OPENCLAW_CDP_URL=http://192.168.112.1:18812   # full relay to shared Chrome
//
// Usage:
//   pinned-tab-ctl.js create <url>          open your pinned tab (idempotent)
//   pinned-tab-ctl.js goto <url>            navigate the pinned tab
//   pinned-tab-ctl.js url                   print current URL
//   pinned-tab-ctl.js text                  dump page innerText (first 6000 chars)
//   pinned-tab-ctl.js eval '<js-expr>'      evaluate in page, print JSON result
//   pinned-tab-ctl.js click <css>           click first match of CSS selector
//   pinned-tab-ctl.js click-text <text>     click first clickable containing text
//   pinned-tab-ctl.js type <css> <text>     focus element and type text
//   pinned-tab-ctl.js fill <css> <text>     replace a plain input/textarea value
//   pinned-tab-ctl.js select <css> <value>  select a native <select> option by value
//   pinned-tab-ctl.js click-confirm <css> <expected-message...>
//       click and accept an expected JavaScript confirm() dialog
//   pinned-tab-ctl.js click-prompt <css> <response> <expected-message...>
//       click and answer an expected non-secret JavaScript prompt() dialog
//   pinned-tab-ctl.js press <key>           send a key (Enter, Tab, ...)
//   pinned-tab-ctl.js screenshot <out.png>  screenshot the pinned tab
//   pinned-tab-ctl.js setfiles <css> <windows-path...>
//       arm a file input via DOM.setFileInputFiles; paths resolve on the BROWSER
//       host, so pass Windows paths (C:\Users\...\file.mp4), not WSL paths.
//   pinned-tab-ctl.js close                 close the pinned tab and forget the pin

const fs = require('fs');
const path = require('path');

function loadChromium() {
  const candidates = [
    process.env.OPENCLAW_PLAYWRIGHT_CORE,
    process.env.PW_PATH,
    path.join(process.env.HOME || '', '.local/lib/node_modules/openclaw/node_modules/playwright-core'),
    path.join(process.env.HOME || '', '.openclaw/node_modules/playwright-core'),
    '/home/hod/IdeaProjects/dinkel/node_modules/playwright-core',
  ].filter(Boolean);

  try {
    return require('playwright-core').chromium;
  } catch { /* try explicit cross-platform locations below */ }

  for (const candidate of candidates) {
    try {
      return require(candidate).chromium;
    } catch { /* try the next candidate */ }
  }

  throw new Error(
    'playwright-core not found; set OPENCLAW_PLAYWRIGHT_CORE to its module directory'
  );
}

const chromium = loadChromium();

const CDP = process.env.OPENCLAW_CDP_URL || 'http://192.168.112.1:18812';
const PIN = process.env.PIN_NAME || 'default';
const STATE_DIR = '/tmp/openclaw/pinned-tabs';
const STATE = path.join(STATE_DIR, PIN + '.json');

async function targetIdOf(ctx, page) {
  const session = await ctx.newCDPSession(page);
  try {
    const { targetInfo } = await session.send('Target.getTargetInfo');
    return targetInfo.targetId;
  } finally {
    await session.detach().catch(() => {});
  }
}

async function findPinned(ctx) {
  let saved;
  try { saved = JSON.parse(fs.readFileSync(STATE, 'utf8')).targetId; } catch { return null; }
  for (const p of ctx.pages()) {
    try {
      const id = await Promise.race([
        targetIdOf(ctx, p),
        new Promise((_, rej) => setTimeout(() => rej(new Error('slow tab')), 3000)),
      ]);
      if (id === saved) return p;
    } catch (e) { /* hung or restricted tab — not ours */ }
  }
  return null;
}

async function clickWithExpectedDialog(page, selector, expectedType, response, expectedMessage) {
  if (!selector || !expectedMessage) {
    throw new Error(`${expectedType === 'prompt' ? 'click-prompt' : 'click-confirm'} requires a selector and expected dialog text`);
  }

  let handler;
  const dialogPromise = new Promise(resolve => {
    handler = async dialog => {
      try {
        const message = dialog.message();
        if (dialog.type() !== expectedType || !message.includes(expectedMessage)) {
          await dialog.dismiss();
          resolve({
            error: new Error(
              `unexpected dialog: type=${dialog.type()} message=${JSON.stringify(message)}`
            ),
          });
          return;
        }
        if (expectedType === 'prompt') await dialog.accept(response);
        else await dialog.accept();
        resolve({ type: dialog.type(), message });
      } catch (error) {
        resolve({ error });
      }
    };
    page.once('dialog', handler);
  });

  try {
    await page.locator(selector).first().click({ timeout: 10000 });
    const dialog = await Promise.race([
      dialogPromise,
      new Promise((_, reject) => setTimeout(
        () => reject(new Error(`expected ${expectedType} dialog did not appear`)),
        5000
      )),
    ]);
    if (dialog.error) throw dialog.error;
    return dialog;
  } finally {
    if (handler) page.off('dialog', handler);
  }
}

(async () => {
  const [cmd, ...args] = process.argv.slice(2);
  const browser = await chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  let page = await findPinned(ctx);

  if (cmd === 'create') {
    if (!page) {
      page = await ctx.newPage();
      fs.mkdirSync(STATE_DIR, { recursive: true });
      fs.writeFileSync(STATE, JSON.stringify({ targetId: await targetIdOf(ctx, page) }));
    }
    if (args[0]) await page.goto(args[0], { waitUntil: 'domcontentloaded', timeout: 45000 });
    console.log('pinned tab ready:', page.url());
    return process.exit(0);
  }

  if (!page) { console.error(`no pinned tab for PIN_NAME=${PIN} — run: pinned-tab-ctl.js create <url>`); return process.exit(2); }

  switch (cmd) {
    case 'goto':
      await page.goto(args[0], { waitUntil: 'domcontentloaded', timeout: 45000 });
      console.log('at:', page.url());
      break;
    case 'url':
      console.log(page.url());
      break;
    case 'text': {
      const t = await page.evaluate('document.body ? document.body.innerText : ""');
      console.log(t.replace(/\n{3,}/g, '\n\n').slice(0, 6000));
      break;
    }
    case 'eval': {
      const r = await page.evaluate(args[0]);
      console.log(JSON.stringify(r, null, 1));
      break;
    }
    case 'click-text': {
      const target = page.locator(
        `button:has-text("${args[0]}"), [role=button]:has-text("${args[0]}"), a:has-text("${args[0]}"), tp-yt-paper-item:has-text("${args[0]}"), yt-formatted-string:has-text("${args[0]}")`
      ).first();
      await target.click({ timeout: 10000 });
      console.log('clicked text:', args[0]);
      break;
    }
    case 'click':
      await page.locator(args[0]).first().click({ timeout: 10000 });
      console.log('clicked:', args[0]);
      break;
    case 'click-confirm': {
      const [selector, ...expectedParts] = args;
      const dialog = await clickWithExpectedDialog(
        page,
        selector,
        'confirm',
        '',
        expectedParts.join(' ')
      );
      console.log('confirmed dialog:', dialog.message);
      break;
    }
    case 'click-prompt': {
      const [selector, response, ...expectedParts] = args;
      const dialog = await clickWithExpectedDialog(
        page,
        selector,
        'prompt',
        response,
        expectedParts.join(' ')
      );
      console.log('answered prompt:', dialog.message);
      break;
    }
    case 'type':
      await page.locator(args[0]).first().click({ timeout: 10000 });
      await page.keyboard.type(args.slice(1).join(' '), { delay: 20 });
      console.log('typed into:', args[0]);
      break;
    case 'fill':
      await page.locator(args[0]).first().fill(args.slice(1).join(' '), { timeout: 10000 });
      console.log('filled:', args[0]);
      break;
    case 'select':
      await page.locator(args[0]).first().selectOption({ value: args[1] });
      console.log('selected:', args[0], '=', args[1]);
      break;
    case 'press':
      await page.keyboard.press(args[0]);
      console.log('pressed:', args[0]);
      break;
    case 'screenshot':
      await page.screenshot({ path: args[0], timeout: 60000 });
      console.log('MEDIA:' + args[0]);
      break;
    case 'setfiles': {
      const [sel, ...files] = args;
      const session = await ctx.newCDPSession(page);
      const doc = await session.send('DOM.getDocument');
      const node = await session.send('DOM.querySelector', { nodeId: doc.root.nodeId, selector: sel });
      if (!node.nodeId) throw new Error('no node for selector: ' + sel);
      await session.send('DOM.setFileInputFiles', { files, nodeId: node.nodeId });
      console.log('files set on', sel, ':', files.join(', '));
      break;
    }
    case 'close':
      await page.close();
      fs.rmSync(STATE, { force: true });
      console.log('pinned tab closed');
      break;
    default:
      console.error('unknown command:', cmd);
      process.exit(2);
  }
  process.exit(0);
})().catch(e => { console.error('ERROR:', e.message); process.exit(1); });
