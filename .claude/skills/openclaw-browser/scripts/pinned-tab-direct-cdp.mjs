#!/usr/bin/env node
// Direct pinned-tab CDP helper.
//
// Use this when pinned-tab-ctl.js is too slow in a crowded profile. It reads the
// same /tmp/openclaw/pinned-tabs/<PIN_NAME>.json state, connects directly to that
// target's WebSocket, and avoids Playwright page enumeration.

import fs from 'node:fs';
import path from 'node:path';

const CDP = (process.env.OPENCLAW_CDP_URL || 'http://192.168.112.1:18812').replace(/\/+$/, '');
const PIN = process.env.PIN_NAME || 'default';
const STATE_DIR = process.env.OPENCLAW_PIN_STATE_DIR || '/tmp/openclaw/pinned-tabs';
const STATE = path.join(STATE_DIR, `${PIN}.json`);
const LIMIT = Number(process.env.OPENCLAW_TEXT_LIMIT || 8000);
const TIMEOUT_MS = Number(process.env.OPENCLAW_DIRECT_CDP_TIMEOUT_MS || 45000);

function usage() {
  console.error(`usage: pinned-tab-direct-cdp.mjs <command> [args...]

Commands:
  create [url]                 create/reuse the named pinned target
  goto <url>                   navigate the pinned target
  url                          print current URL
  text                         print document.body.innerText
  eval <js>                    evaluate JS and print JSON
  click <css>                  trusted-click the first matching element
  click-text <text>            trusted-click the first visible clickable containing text
  type <css> <text>            trusted-click an element, then insert text
  fill <css> <text>            set element value and dispatch input/change
  press <key>                  send Enter, Tab, Escape, Backspace, or Delete
  setfiles <css> <win-path...> set a file input with browser-host paths
  screenshot <out.png> [w h]   capture viewport PNG to a WSL path, optionally at an exact size
  frames                       list page frames
  frame-text <match>           print innerText from a frame URL/name/title match
  frame-eval <match> <js>      evaluate JS in a matching frame
  frame-click <match> <css>    trusted-click an element in a matching frame
  frame-click-text <match> <text>
                               trusted-click visible clickable text in a frame
  frame-fill <match> <css> <text>
                               set element value in a matching frame
  close                        close the pinned target and remove state

Environment:
  PIN_NAME                     required unique per task in normal use
  OPENCLAW_CDP_URL             CDP HTTP endpoint, default ${CDP}
  OPENCLAW_PIN_STATE_DIR       default ${STATE_DIR}`);
  process.exit(2);
}

async function json(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`${url} -> HTTP ${response.status}`);
  return response.json();
}

async function targetList() {
  return json(`${CDP}/json/list`);
}

function readSavedTargetId() {
  try {
    return JSON.parse(fs.readFileSync(STATE, 'utf8')).targetId;
  } catch {
    return null;
  }
}

function writeState(targetId) {
  fs.mkdirSync(STATE_DIR, { recursive: true });
  fs.writeFileSync(STATE, JSON.stringify({
    targetId,
    cdpUrl: CDP,
    updatedAt: new Date().toISOString(),
  }, null, 2));
}

async function findTarget(targetId) {
  if (!targetId) return null;
  const targets = await targetList();
  return targets.find(target => target.id === targetId) || null;
}

async function pinnedTarget() {
  const targetId = readSavedTargetId();
  const target = await findTarget(targetId);
  if (!target) {
    throw new Error(`no live pinned target for PIN_NAME=${PIN}; run: pinned-tab-direct-cdp.mjs create <url>`);
  }
  return target;
}

function connect(wsUrl) {
  if (!globalThis.WebSocket) {
    throw new Error('global WebSocket is unavailable; use Node 22+');
  }

  const ws = new WebSocket(wsUrl);
  let id = 0;
  const pending = new Map();
  const waiters = new Map();
  const events = [];

  ws.onmessage = event => {
    const msg = JSON.parse(event.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject, method } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? reject(new Error(`${method}: ${JSON.stringify(msg.error)}`)) : resolve(msg.result);
      return;
    }

    events.push(msg);
    const queue = waiters.get(msg.method);
    if (queue?.length) {
      const waiter = queue.shift();
      clearTimeout(waiter.timer);
      waiter.resolve(msg);
    }
  };

  const open = new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = reject;
  });

  function cmd(method, params = {}) {
    return new Promise((resolve, reject) => {
      const msgId = ++id;
      pending.set(msgId, { resolve, reject, method });
      ws.send(JSON.stringify({ id: msgId, method, params }));
    });
  }

  function waitFor(method, ms = 15000) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`timeout waiting for ${method}`)), ms);
      const queue = waiters.get(method) || [];
      queue.push({ resolve, reject, timer });
      waiters.set(method, queue);
    });
  }

  function close() {
    try { ws.close(); } catch {}
  }

  return { open, cmd, waitFor, close, events };
}

async function browserClient() {
  const version = await json(`${CDP}/json/version`);
  if (!version.webSocketDebuggerUrl) throw new Error('CDP /json/version did not expose browser WebSocket');
  const client = connect(version.webSocketDebuggerUrl);
  await client.open;
  return client;
}

async function createTarget(url = 'about:blank') {
  let targetId;
  let client;
  try {
    client = await browserClient();
    const result = await client.cmd('Target.createTarget', { url });
    targetId = result.targetId;
  } catch {
    const target = await json(`${CDP}/json/new?${encodeURIComponent(url)}`, { method: 'PUT' });
    targetId = target.id;
  } finally {
    client?.close();
  }

  writeState(targetId);
  for (let i = 0; i < 20; i += 1) {
    const target = await findTarget(targetId);
    if (target) return target;
    await sleep(250);
  }
  throw new Error(`created target ${targetId}, but it did not appear in /json/list`);
}

async function closeTarget() {
  const targetId = readSavedTargetId();
  const target = await findTarget(targetId);
  if (target) {
    let client;
    try {
      client = await browserClient();
      await client.cmd('Target.closeTarget', { targetId });
    } finally {
      client?.close();
    }
  }
  fs.rmSync(STATE, { force: true });
}

function unpack(result) {
  if (result?.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  const value = result?.result;
  if (!value) return null;
  if ('value' in value) return value.value;
  if ('description' in value) return value.description;
  return value;
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function pagePoint(cmd, selector) {
  const expression = `(() => {
    const e = document.querySelector(${JSON.stringify(selector)});
    if (!e) return null;
    e.scrollIntoView({block: 'center', inline: 'center'});
    const r = e.getBoundingClientRect();
    if (!r.width || !r.height) return null;
    return {x: r.left + r.width / 2, y: r.top + r.height / 2};
  })()`;
  const point = unpack(await cmd('Runtime.evaluate', {
    expression,
    returnByValue: true,
    awaitPromise: true,
  }));
  if (!point) throw new Error(`no visible element for selector ${selector}`);
  return point;
}

function flattenFrames(frameTree, out = []) {
  if (!frameTree) return out;
  out.push(frameTree.frame);
  for (const child of frameTree.childFrames || []) flattenFrames(child, out);
  return out;
}

async function frames(cmd) {
  const { frameTree } = await cmd('Page.getFrameTree');
  return flattenFrames(frameTree);
}

async function matchedFrame(cmd, match) {
  if (!match) usage();
  const needle = match.toLowerCase();
  const frame = (await frames(cmd)).find(item => (
    item.url || item.name || item.title || item.id || ''
  ).toLowerCase().includes(needle));
  if (!frame) throw new Error(`no frame matching ${match}`);
  return frame;
}

async function frameContext(cmd, frameId) {
  const result = await cmd('Page.createIsolatedWorld', {
    frameId,
    worldName: 'openclaw-direct-cdp',
    grantUniveralAccess: true,
  });
  return result.executionContextId;
}

async function frameRect(cmd, match) {
  const expression = `(() => {
    const needle = ${JSON.stringify(match)}.toLowerCase();
    const frame = [...document.querySelectorAll('iframe')].find(f => (
      f.src || f.name || f.title || f.id || ''
    ).toLowerCase().includes(needle));
    if (!frame) return null;
    frame.scrollIntoView({block: 'nearest', inline: 'nearest'});
    const r = frame.getBoundingClientRect();
    return {x: r.left, y: r.top, w: r.width, h: r.height};
  })()`;
  const rect = unpack(await cmd('Runtime.evaluate', {
    expression,
    returnByValue: true,
    awaitPromise: true,
  }));
  if (!rect) throw new Error(`no iframe element matching ${match}`);
  return rect;
}

async function framePoint(cmd, contextId, match, selector) {
  const expression = `(() => {
    const e = document.querySelector(${JSON.stringify(selector)});
    if (!e) return null;
    e.scrollIntoView({block: 'center', inline: 'center'});
    const r = e.getBoundingClientRect();
    if (!r.width || !r.height) return null;
    return {x: r.left + r.width / 2, y: r.top + r.height / 2};
  })()`;
  const point = unpack(await cmd('Runtime.evaluate', {
    expression,
    contextId,
    returnByValue: true,
    awaitPromise: true,
  }));
  if (!point) throw new Error(`no visible frame element for selector ${selector}`);
  const rect = await frameRect(cmd, match);
  return { x: rect.x + point.x, y: rect.y + point.y };
}

async function trustedClick(cmd, point) {
  await cmd('Input.dispatchMouseEvent', { type: 'mouseMoved', x: point.x, y: point.y, button: 'none' });
  await cmd('Input.dispatchMouseEvent', { type: 'mousePressed', x: point.x, y: point.y, button: 'left', clickCount: 1 });
  await cmd('Input.dispatchMouseEvent', { type: 'mouseReleased', x: point.x, y: point.y, button: 'left', clickCount: 1 });
}

async function keyPress(cmd, key) {
  const keys = {
    Enter: { key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 },
    Tab: { key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 },
    Escape: { key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 },
    Backspace: { key: 'Backspace', code: 'Backspace', windowsVirtualKeyCode: 8 },
    Delete: { key: 'Delete', code: 'Delete', windowsVirtualKeyCode: 46 },
  };
  const spec = keys[key];
  if (!spec) throw new Error(`unsupported key ${key}; supported: ${Object.keys(keys).join(', ')}`);
  await cmd('Input.dispatchKeyEvent', { type: 'keyDown', ...spec });
  await cmd('Input.dispatchKeyEvent', { type: 'keyUp', ...spec });
}

async function main() {
  const [action, ...args] = process.argv.slice(2);
  if (!action) usage();

  if (action === 'create') {
    let target = await findTarget(readSavedTargetId());
    if (!target) target = await createTarget(args[0] || 'about:blank');
    if (args[0] && target.url !== args[0]) {
      const client = connect(target.webSocketDebuggerUrl);
      await client.open;
      try {
        await client.cmd('Page.enable');
        await client.cmd('Page.navigate', { url: args[0] });
        await sleep(2500);
      } finally {
        client.close();
      }
      target = await pinnedTarget();
    }
    console.log(`pinned tab ready: ${target.url}`);
    return;
  }

  if (action === 'close') {
    await closeTarget();
    console.log('pinned tab closed');
    return;
  }

  if (action === 'url') {
    const target = await pinnedTarget();
    console.log(target.url);
    return;
  }

  const target = await pinnedTarget();
  const client = connect(target.webSocketDebuggerUrl);
  await client.open;
  const { cmd } = client;

  try {
    await cmd('Runtime.enable');
    await cmd('Page.enable');
    await cmd('DOM.enable');

    if (action === 'goto') {
      const url = args[0];
      if (!url) usage();
      const load = client.waitFor('Page.loadEventFired', 15000).catch(() => null);
      await cmd('Page.navigate', { url });
      await load;
      await sleep(1000);
      const refreshed = await pinnedTarget();
      console.log(`at: ${refreshed.url}`);
      return;
    }

    if (action === 'text') {
      const value = unpack(await cmd('Runtime.evaluate', {
        expression: 'document.body ? document.body.innerText : ""',
        returnByValue: true,
        awaitPromise: true,
      }));
      console.log(String(value || '').replace(/\n{3,}/g, '\n\n').slice(0, LIMIT));
      return;
    }

    if (action === 'frames') {
      const value = (await frames(cmd)).map(frame => ({
        id: frame.id,
        parentId: frame.parentId || null,
        name: frame.name || '',
        title: frame.title || '',
        url: frame.url || '',
      }));
      console.log(JSON.stringify(value, null, 2));
      return;
    }

    if (action === 'eval') {
      const expression = args.join(' ');
      if (!expression) usage();
      const value = unpack(await cmd('Runtime.evaluate', {
        expression,
        returnByValue: true,
        awaitPromise: true,
      }));
      console.log(JSON.stringify(value, null, 2));
      return;
    }

    if (action === 'frame-text') {
      const match = args[0];
      if (!match) usage();
      const frame = await matchedFrame(cmd, match);
      const contextId = await frameContext(cmd, frame.id);
      const value = unpack(await cmd('Runtime.evaluate', {
        expression: 'document.body ? document.body.innerText : ""',
        contextId,
        returnByValue: true,
        awaitPromise: true,
      }));
      console.log(String(value || '').replace(/\n{3,}/g, '\n\n').slice(0, LIMIT));
      return;
    }

    if (action === 'frame-eval') {
      const [match, ...expressionParts] = args;
      const expression = expressionParts.join(' ');
      if (!match || !expression) usage();
      const frame = await matchedFrame(cmd, match);
      const contextId = await frameContext(cmd, frame.id);
      const value = unpack(await cmd('Runtime.evaluate', {
        expression,
        contextId,
        returnByValue: true,
        awaitPromise: true,
      }));
      console.log(JSON.stringify(value, null, 2));
      return;
    }

    if (action === 'click') {
      const selector = args[0];
      if (!selector) usage();
      await trustedClick(cmd, await pagePoint(cmd, selector));
      console.log(`clicked: ${selector}`);
      return;
    }

    if (action === 'frame-click') {
      const [match, selector] = args;
      if (!match || !selector) usage();
      const frame = await matchedFrame(cmd, match);
      const contextId = await frameContext(cmd, frame.id);
      await trustedClick(cmd, await framePoint(cmd, contextId, match, selector));
      console.log(`clicked frame ${match}: ${selector}`);
      return;
    }

    if (action === 'click-text') {
      const text = args.join(' ');
      if (!text) usage();
      const expression = `(() => {
        const needle = ${JSON.stringify(text)}.toLowerCase();
        const isVisible = e => {
          const s = getComputedStyle(e);
          const r = e.getBoundingClientRect();
          return s.visibility !== 'hidden' && s.display !== 'none' && r.width > 0 && r.height > 0;
        };
        const candidates = [...document.querySelectorAll('button,[role=button],a,input[type=button],input[type=submit],mat-option,[role=option]')];
        const e = candidates.find(x => isVisible(x) && (x.innerText || x.value || x.textContent || '').toLowerCase().includes(needle));
        if (!e) return null;
        e.scrollIntoView({block: 'center', inline: 'center'});
        const r = e.getBoundingClientRect();
        return {x: r.left + r.width / 2, y: r.top + r.height / 2};
      })()`;
      const point = unpack(await cmd('Runtime.evaluate', {
        expression,
        returnByValue: true,
        awaitPromise: true,
      }));
      if (!point) throw new Error(`no visible clickable text: ${text}`);
      await trustedClick(cmd, point);
      console.log(`clicked text: ${text}`);
      return;
    }

    if (action === 'frame-click-text') {
      const [match, ...textParts] = args;
      const text = textParts.join(' ');
      if (!match || !text) usage();
      const frame = await matchedFrame(cmd, match);
      const contextId = await frameContext(cmd, frame.id);
      const expression = `(() => {
        const needle = ${JSON.stringify(text)}.toLowerCase();
        const isVisible = e => {
          const s = getComputedStyle(e);
          const r = e.getBoundingClientRect();
          return s.visibility !== 'hidden' && s.display !== 'none' && r.width > 0 && r.height > 0;
        };
        const candidates = [...document.querySelectorAll('button,[role=button],a,input[type=button],input[type=submit],material-button,material-tab,[role=tab],mat-option,[role=option]')];
        const e = candidates.find(x => isVisible(x) && (x.innerText || x.value || x.textContent || '').toLowerCase().includes(needle));
        if (!e) return null;
        e.scrollIntoView({block: 'center', inline: 'center'});
        const r = e.getBoundingClientRect();
        return {x: r.left + r.width / 2, y: r.top + r.height / 2};
      })()`;
      const point = unpack(await cmd('Runtime.evaluate', {
        expression,
        contextId,
        returnByValue: true,
        awaitPromise: true,
      }));
      if (!point) throw new Error(`no visible frame clickable text: ${text}`);
      const rect = await frameRect(cmd, match);
      await trustedClick(cmd, { x: rect.x + point.x, y: rect.y + point.y });
      console.log(`clicked frame text ${match}: ${text}`);
      return;
    }

    if (action === 'type') {
      const [selector, ...textParts] = args;
      const text = textParts.join(' ');
      if (!selector || !text) usage();
      await trustedClick(cmd, await pagePoint(cmd, selector));
      await cmd('Input.insertText', { text });
      console.log(`typed into: ${selector}`);
      return;
    }

    if (action === 'frame-fill') {
      const [match, selector, ...textParts] = args;
      const text = textParts.join(' ');
      if (!match || !selector) usage();
      const frame = await matchedFrame(cmd, match);
      const contextId = await frameContext(cmd, frame.id);
      const expression = `(() => {
        const e = document.querySelector(${JSON.stringify(selector)});
        if (!e) return false;
        e.focus();
        const value = ${JSON.stringify(text)};
        const proto = e instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
        setter ? setter.call(e, value) : e.value = value;
        e.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: value}));
        e.dispatchEvent(new Event('change', {bubbles: true}));
        return true;
      })()`;
      const ok = unpack(await cmd('Runtime.evaluate', {
        expression,
        contextId,
        returnByValue: true,
        awaitPromise: true,
      }));
      if (!ok) throw new Error(`no frame input element for selector ${selector}`);
      console.log(`filled frame ${match}: ${selector}`);
      return;
    }

    if (action === 'fill') {
      const [selector, ...textParts] = args;
      const text = textParts.join(' ');
      if (!selector) usage();
      const expression = `(() => {
        const e = document.querySelector(${JSON.stringify(selector)});
        if (!e) return false;
        e.focus();
        const value = ${JSON.stringify(text)};
        const proto = e instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
        setter ? setter.call(e, value) : e.value = value;
        e.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: value}));
        e.dispatchEvent(new Event('change', {bubbles: true}));
        return true;
      })()`;
      const ok = unpack(await cmd('Runtime.evaluate', {
        expression,
        returnByValue: true,
        awaitPromise: true,
      }));
      if (!ok) throw new Error(`no input element for selector ${selector}`);
      console.log(`filled: ${selector}`);
      return;
    }

    if (action === 'press') {
      const key = args[0];
      if (!key) usage();
      await keyPress(cmd, key);
      console.log(`pressed: ${key}`);
      return;
    }

    if (action === 'setfiles') {
      const [selector, ...files] = args;
      if (!selector || files.length === 0) usage();
      const doc = await cmd('DOM.getDocument', { depth: 0 });
      const node = await cmd('DOM.querySelector', { nodeId: doc.root.nodeId, selector });
      if (!node.nodeId) throw new Error(`no node for selector ${selector}`);
      await cmd('DOM.setFileInputFiles', { nodeId: node.nodeId, files });
      console.log(`files set on ${selector}: ${files.join(', ')}`);
      return;
    }

    if (action === 'screenshot') {
      const out = args[0];
      if (!out) usage();
      const width = Number(args[1]);
      const height = Number(args[2]);
      if (args[1] || args[2]) {
        if (!Number.isInteger(width) || width <= 0 || !Number.isInteger(height) || height <= 0) {
          throw new Error('screenshot width and height must be positive integers');
        }
        await cmd('Emulation.setDeviceMetricsOverride', {
          width,
          height,
          deviceScaleFactor: 1,
          mobile: false,
        });
      }
      const shot = await cmd('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
      fs.writeFileSync(out, Buffer.from(shot.data, 'base64'));
      console.log(`MEDIA:${out}`);
      return;
    }

    usage();
  } finally {
    client.close();
  }
}

const timeout = setTimeout(() => {
  console.error('ERROR: helper timeout');
  process.exit(124);
}, TIMEOUT_MS);

main().then(() => {
  clearTimeout(timeout);
}).catch(error => {
  clearTimeout(timeout);
  console.error(`ERROR: ${error.message}`);
  process.exit(1);
});
