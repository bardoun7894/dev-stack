// Bridge to the owner's real Chrome through the "File Drop Bridge" extension (chrome.debugger = CDP inside the signed-in profile).
// Node side: a WebSocket server on 127.0.0.1:8798 the extension dials into, plus BridgePage, a Playwright-shaped subset.
import { EventEmitter } from 'node:events';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { WebSocketServer } from 'ws';
import { splitSelector, engineExpression } from './selector.mjs';

export const PORT = 8798;
export const HOME_DIR = path.join(os.homedir(), '.reel-publish');
export const SECRET_FILE = path.join(HOME_DIR, 'bridge-secret');
export const EXTENSION_DIR = path.join(os.homedir(), 'code/dev-stack/tools/file-drop/extension');
const DEFAULT_TIMEOUT = 30_000;
const POLL_MS = 250;

export function readSecret(file = SECRET_FILE) {
  let s;
  try { s = fs.readFileSync(file, 'utf8').trim(); } catch { s = ''; }
  if (!s) throw new Error('no bridge secret: run `reel-publish pair` first');
  return s;
}

// 32-byte hex secret -> ~/.reel-publish/bridge-secret (0600) and extension/bridge-secret.js.
export function pair({ secretFile = SECRET_FILE, extDir = EXTENSION_DIR } = {}) {
  const secret = crypto.randomBytes(32).toString('hex');
  fs.mkdirSync(path.dirname(secretFile), { recursive: true });
  fs.writeFileSync(secretFile, secret + '\n', { mode: 0o600 });
  fs.chmodSync(secretFile, 0o600);
  const jsFile = path.join(extDir, 'bridge-secret.js');
  fs.writeFileSync(jsFile, `self.BRIDGE_SECRET = '${secret}';\n`, { mode: 0o600 });
  return { secretFile, jsFile };
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const same = (a, b) => {
  const x = Buffer.from(String(a)); const y = Buffer.from(String(b));
  return x.length === y.length && crypto.timingSafeEqual(x, y);
};

export class Bridge extends EventEmitter {
  constructor({ port = PORT, secret, log = (m) => console.log(m) } = {}) {
    super();
    if (!secret) throw new Error('Bridge needs a secret');
    this.port = port;
    this.secret = secret;
    this.log = log;
    this.wss = null;
    this.ext = null;        // the live, authenticated, hello-ed socket
    this.version = null;
    this.nextId = 1;
    this.pending = new Map();
    this.announced = false;
  }

  listen() {
    if (this.wss) return this.listening;
    this.listening = new Promise((resolve, reject) => {
      const wss = new WebSocketServer({
        host: '127.0.0.1', port: this.port,
        verifyClient: ({ req }) => {
          const k = new URL(req.url, 'http://127.0.0.1').searchParams.get('k');
          return k !== null && same(k, this.secret);
        },
      });
      wss.on('listening', () => { this.port = wss.address().port; resolve(this.port); });
      wss.on('error', (e) => { if (!this.ext) reject(e); });
      wss.on('connection', (sock) => this._adopt(sock));
      this.wss = wss;
    });
    return this.listening;
  }

  _adopt(sock) {
    if (this.ext && this.ext !== sock) this.ext.terminate();
    let helloed = false;
    sock.on('message', (data) => {
      let msg;
      try { msg = JSON.parse(String(data)); } catch { return; }
      if (msg.event === 'hello') {
        helloed = true;
        this.ext = sock;
        this.version = msg.version;
        this.emit('ready');
      } else if (!helloed) {
        return;
      } else if (msg.id !== undefined) {
        const p = this.pending.get(msg.id);
        if (!p) return;
        this.pending.delete(msg.id);
        clearTimeout(p.timer);
        if (msg.error !== undefined) p.reject(new Error(String(msg.error)));
        else p.resolve(msg.result);
      } else if (msg.event === 'cdp') {
        this.emit('cdp', msg);
      } else if (msg.event === 'detached') {
        this.emit('detached', msg);
      }
    });
    sock.on('close', () => {
      if (this.ext === sock) {
        this.ext = null;
        for (const [id, p] of this.pending) { clearTimeout(p.timer); p.reject(new Error('extension disconnected')); this.pending.delete(id); }
        this.emit('disconnected');
      }
    });
    sock.on('error', () => {});
  }

  // Start listening and wait for the extension's hello.
  async connect({ timeout = 90_000 } = {}) {
    await this.listen();
    if (this.ext) return;
    if (!this.announced) {
      this.announced = true;
      this.log('waiting for File Drop Bridge in Chrome (click its icon if this takes long)');
    }
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.off('ready', onReady); reject(new Error(`File Drop Bridge did not connect within ${Math.round(timeout / 1000)}s`)); }, timeout);
      const onReady = () => { clearTimeout(timer); resolve(); };
      this.once('ready', onReady);
    });
  }

  request(op, params = {}, { timeout = 120_000 } = {}) {
    if (!this.ext) return Promise.reject(new Error('extension not connected'));
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error(`bridge ${op} timed out after ${timeout}ms`)); }, timeout);
      this.pending.set(id, { resolve, reject, timer });
      this.ext.send(JSON.stringify({ id, op, ...params }));
    });
  }

  async newPage() {
    const { tabId } = await this.request('newTab', { url: 'about:blank' });
    return new BridgePage(this, tabId);
  }

  async close() {
    if (this.ext) this.ext.terminate();
    for (const c of this.wss?.clients || []) c.terminate();
    if (this.wss) await new Promise((r) => this.wss.close(r));
    this.wss = null;
  }
}

const MODS = { alt: 1, control: 2, ctrl: 2, meta: 4, cmd: 4, command: 4, shift: 8 };
const KEYS = {
  backspace: { key: 'Backspace', code: 'Backspace', vk: 8 },
  enter: { key: 'Enter', code: 'Enter', vk: 13, text: '\r' },
  tab: { key: 'Tab', code: 'Tab', vk: 9 },
  escape: { key: 'Escape', code: 'Escape', vk: 27 },
};

// 'Meta+A' -> Input.dispatchKeyEvent param pairs [keyDown, keyUp].
export function keyEvents(combo) {
  const parts = combo.split('+');
  const name = parts.pop();
  let modifiers = 0;
  for (const m of parts) {
    if (!(m.toLowerCase() in MODS)) throw new Error(`unknown modifier ${m} in ${combo}`);
    modifiers |= MODS[m.toLowerCase()];
  }
  let k = KEYS[name.toLowerCase()];
  if (!k) {
    if (name.length !== 1) throw new Error(`unsupported key ${name}`);
    const up = name.toUpperCase();
    const letter = /[A-Z]/.test(up);
    k = { key: modifiers & 8 ? up : name.toLowerCase(), code: letter ? `Key${up}` : `Digit${up}`, vk: up.charCodeAt(0) };
    if (name.toLowerCase() === 'a' && modifiers & (2 | 4)) k.commands = ['selectAll'];
    if (!(modifiers & (2 | 4 | 1)) && !k.commands) k.text = k.key;
  }
  const base = { modifiers, key: k.key, code: k.code, windowsVirtualKeyCode: k.vk, nativeVirtualKeyCode: k.vk };
  const down = { type: k.text ? 'keyDown' : 'rawKeyDown', ...base, ...(k.text ? { text: k.text } : {}), ...(k.commands ? { commands: k.commands } : {}) };
  return [down, { type: 'keyUp', ...base }];
}

export class BridgePage {
  constructor(bridge, tabId) {
    this.bridge = bridge;
    this.tabId = tabId;
    this._url = 'about:blank';
    this._pending = Promise.resolve();
    this._closed = false;
    this._listeners = new Set();
    this._onCdp = (ev) => {
      if (ev.tabId !== tabId) return;
      if (ev.method === 'Page.frameNavigated' && !ev.params.frame.parentId) this._url = ev.params.frame.url;
      if (ev.method === 'Page.navigatedWithinDocument') this._url = ev.params.url;
      for (const l of [...this._listeners]) l(ev);
    };
    bridge.on('cdp', this._onCdp);
    this.keyboard = {
      press: async (combo) => {
        for (const params of keyEvents(combo)) await this.cdp('Input.dispatchKeyEvent', params);
      },
      insertText: (text) => this.cdp('Input.insertText', { text }),
    };
  }

  async cdp(method, params = {}) {
    await this._pending;
    return this.bridge.request('cdp', { tabId: this.tabId, method, params });
  }

  // Resolves on the first matching CDP event; the listener is registered synchronously.
  _waitEvent(method, { timeout, filter } = {}) {
    return new Promise((resolve, reject) => {
      const l = (ev) => {
        if (ev.method !== method || (filter && !filter(ev.params))) return;
        done(); resolve(ev.params);
      };
      const timer = timeout ? setTimeout(() => { done(); reject(new Error(`timeout ${timeout}ms waiting for ${method}`)); }, timeout) : null;
      const done = () => { clearTimeout(timer); this._listeners.delete(l); };
      this._listeners.add(l);
    });
  }

  url() { return this._url; }

  async currentUrl() {
    const r = await this.evalRaw('location.href');
    if (typeof r === 'string') this._url = r;
    return this._url;
  }

  async evalRaw(expression) {
    const r = await this.cdp('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
    return r.result.value;
  }

  async goto(url, { waitUntil = 'load', timeout = 60_000 } = {}) {
    await this.cdp('Page.enable');
    const event = waitUntil === 'domcontentloaded' ? 'Page.domContentEventFired' : 'Page.loadEventFired';
    const loaded = this._waitEvent(event, { timeout });
    loaded.catch(() => {});
    const nav = await this.cdp('Page.navigate', { url });
    if (nav.errorText) throw new Error(`navigation to ${url} failed: ${nav.errorText}`);
    // Same-document navigation fires no load event.
    if (nav.loaderId === undefined) { this._url = url; return; }
    await loaded;
    await this.currentUrl().catch(() => {});
  }

  waitForTimeout(ms) { return sleep(ms); }

  async waitForURL(re, { timeout = DEFAULT_TIMEOUT } = {}) {
    const end = Date.now() + timeout;
    for (;;) {
      const u = await this.currentUrl().catch(() => this._url);
      if (typeof re === 'string' ? u.includes(re) : re.test(u)) return;
      if (Date.now() >= end) throw new Error(`timeout ${timeout}ms waiting for URL ${re} (at ${u})`);
      await sleep(POLL_MS);
    }
  }

  // Only 'filechooser' is supported. Interception is enabled before any later action runs.
  waitForEvent(name, { timeout = DEFAULT_TIMEOUT } = {}) {
    if (name !== 'filechooser') return Promise.reject(new Error(`waitForEvent(${name}) is not supported`));
    const opened = this._waitEvent('Page.fileChooserOpened', { timeout });
    const ready = this.bridge.request('cdp', { tabId: this.tabId, method: 'Page.setInterceptFileChooserDialog', params: { enabled: true } });
    this._pending = ready.catch(() => {});
    return (async () => {
      await ready;
      const p = await opened;
      return {
        setFiles: async (files) => {
          const list = [].concat(files).map((f) => path.resolve(f));
          await this.bridge.request('cdp', { tabId: this.tabId, method: 'DOM.setFileInputFiles', params: { files: list, backendNodeId: p.backendNodeId } });
          await this.bridge.request('cdp', { tabId: this.tabId, method: 'Page.setInterceptFileChooserDialog', params: { enabled: false } }).catch(() => {});
        },
      };
    })();
  }

  async screenshot({ path: file } = {}) {
    await this.cdp('Page.bringToFront').catch(() => {});
    const r = await this.cdp('Page.captureScreenshot', { format: 'png' });
    const buf = Buffer.from(r.data, 'base64');
    if (file) fs.writeFileSync(file, buf);
    return buf;
  }

  async close() {
    if (this._closed) return;
    this._closed = true;
    this.bridge.off('cdp', this._onCdp);
    await this.bridge.request('closeTab', { tabId: this.tabId });
  }

  locator(selector, { hasText } = {}) { return new Locator(this, splitSelector(selector), 0, hasText, selector); }
  getByText(text) { return new Locator(this, [`text=${text}`], 0, undefined, `text=${text}`); }
}

class Locator {
  constructor(page, alts, index, hasText, label) {
    this.page = page; this.alts = alts; this.index = index; this.hasText = hasText; this.label = label;
  }

  _with(index) { return new Locator(this.page, this.alts, index, this.hasText, this.label); }
  first() { return this._with(0); }
  last() { return this._with(-1); }
  nth(i) { return this._with(i); }

  async _find(mode) {
    const r = await this.page.cdp('Runtime.evaluate', { expression: engineExpression(this.alts, this.index, this.hasText, mode), returnByValue: mode === 'state' || mode === 'count' });
    if (r.exceptionDetails) throw new Error(`selector "${this.label}": ${r.exceptionDetails.exception?.description || r.exceptionDetails.text}`);
    return mode === 'state' || mode === 'count' ? r.result.value : (r.result.objectId || null);
  }

  // Poll until `probe` returns a truthy value; throw after the timeout.
  async _until(probe, timeout, what) {
    const end = Date.now() + timeout;
    for (;;) {
      const v = await probe();
      if (v) return v;
      if (Date.now() >= end) throw new Error(`timeout ${timeout}ms waiting for ${what} "${this.label}"`);
      await sleep(POLL_MS);
    }
  }

  _call(objectId, fn, args = []) {
    return this.page.cdp('Runtime.callFunctionOn', {
      objectId, functionDeclaration: fn, arguments: args.map((value) => ({ value })), returnByValue: true, awaitPromise: true,
    }).then((r) => {
      if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
      return r.result.value;
    });
  }

  async click({ timeout = DEFAULT_TIMEOUT } = {}) {
    const id = await this._until(() => this._find('elvis'), timeout, 'visible');
    const pt = await this._call(id, `function () {
      this.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
      const r = this.getBoundingClientRect();
      let x = r.left + r.width / 2, y = r.top + r.height / 2;
      for (let w = this.ownerDocument.defaultView; w && w.frameElement; w = w.parent) {
        const f = w.frameElement, fr = f.getBoundingClientRect();
        x += fr.left + f.clientLeft; y += fr.top + f.clientTop;
      }
      return { x, y };
    }`);
    const base = { x: pt.x, y: pt.y, button: 'left' };
    await this.page.cdp('Input.dispatchMouseEvent', { type: 'mouseMoved', x: pt.x, y: pt.y });
    await this.page.cdp('Input.dispatchMouseEvent', { ...base, type: 'mousePressed', buttons: 1, clickCount: 1 });
    await this.page.cdp('Input.dispatchMouseEvent', { ...base, type: 'mouseReleased', buttons: 0, clickCount: 1 });
  }

  async waitFor({ state = 'visible', timeout = DEFAULT_TIMEOUT } = {}) {
    const ok = async () => {
      const s = await this._find('state');
      if (state === 'attached') return !!s;
      if (state === 'visible') return !!(s && s.visible);
      if (state === 'hidden') return !s || !s.visible;
      throw new Error(`unknown state ${state}`);
    };
    await this._until(ok, timeout, `state ${state} of`);
  }

  // Waits up to `timeout` for the element to be visible; no timeout means one immediate check.
  async isVisible({ timeout = 0 } = {}) {
    const check = async () => !!((await this._find('state'))?.visible);
    const end = Date.now() + timeout;
    for (;;) {
      if (await check()) return true;
      if (Date.now() >= end) return false;
      await sleep(POLL_MS);
    }
  }

  async _attached(timeout) { return this._until(() => this._find('el'), timeout, 'element'); }

  async isChecked({ timeout = DEFAULT_TIMEOUT } = {}) {
    return this._call(await this._attached(timeout), 'function () { return !!this.checked; }');
  }

  async uncheck({ timeout = DEFAULT_TIMEOUT } = {}) {
    if (await this.isChecked({ timeout })) await this.click({ timeout });
  }

  async setInputFiles(files, { timeout = DEFAULT_TIMEOUT } = {}) {
    const objectId = await this._attached(timeout);
    const list = [].concat(files).map((f) => path.resolve(f));
    await this.page.cdp('DOM.setFileInputFiles', { files: list, objectId });
  }

  async getAttribute(name, { timeout = DEFAULT_TIMEOUT } = {}) {
    return this._call(await this._attached(timeout), 'function (n) { return this.getAttribute(n); }', [name]);
  }

  async evaluate(fn, { timeout = DEFAULT_TIMEOUT } = {}) {
    return this._call(await this._attached(timeout), `function () { return (${fn.toString()})(this); }`);
  }

  async fill(value, { timeout = DEFAULT_TIMEOUT } = {}) {
    const id = await this._attached(timeout);
    const editable = await this._call(id, `function () {
      this.focus();
      if (this.isContentEditable) { this.ownerDocument.execCommand('selectAll'); return true; }
      return false;
    }`);
    if (editable) { await this.page.cdp('Input.insertText', { text: value }); return; }
    await this._call(id, `function (v) {
      const proto = this instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(this, v);
      this.dispatchEvent(new Event('input', { bubbles: true }));
      this.dispatchEvent(new Event('change', { bubbles: true }));
    }`, [value]);
  }
}
