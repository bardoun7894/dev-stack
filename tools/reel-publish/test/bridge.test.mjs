import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { WebSocket } from 'ws';
import { Bridge, BridgePage, keyEvents, pair } from '../lib/bridge.mjs';

const SECRET = 'a'.repeat(64);

async function start() {
  const bridge = new Bridge({ port: 0, secret: SECRET, log() {} });
  await bridge.listen();
  return bridge;
}

const open = (bridge, k) => new Promise((resolve, reject) => {
  const ws = new WebSocket(`ws://127.0.0.1:${bridge.port}/?k=${k}`);
  ws.on('open', () => resolve(ws));
  ws.on('error', reject);
  ws.on('unexpected-response', (_req, res) => reject(new Error(`HTTP ${res.statusCode}`)));
});

// Fake extension: answers ops like the real one and records every request.
async function fakeExtension(bridge, { owned = new Set() } = {}) {
  const ws = await open(bridge, SECRET);
  const seen = [];
  ws.on('message', (d) => {
    const m = JSON.parse(String(d));
    seen.push(m);
    if (m.op === 'newTab') { owned.add(7); ws.send(JSON.stringify({ id: m.id, result: { tabId: 7 } })); }
    else if (m.op === 'cdp' && !owned.has(m.tabId)) ws.send(JSON.stringify({ id: m.id, error: `tab ${m.tabId} is not owned by the bridge` }));
    else if (m.op === 'cdp') ws.send(JSON.stringify({ id: m.id, result: {} }));
    else if (m.op === 'closeTab') { owned.delete(m.tabId); ws.send(JSON.stringify({ id: m.id, result: {} })); }
  });
  ws.send(JSON.stringify({ event: 'hello', version: '1.1.0' }));
  await new Promise((r) => bridge.once('ready', r));
  return { ws, seen };
}

test('bridge rejects a wrong secret and accepts the right one after hello', async () => {
  const bridge = await start();
  try {
    await assert.rejects(open(bridge, 'wrong'), /HTTP 401/);
    await assert.rejects(open(bridge, ''), /HTTP 401/);
    const ext = await fakeExtension(bridge);
    assert.equal(bridge.version, '1.1.0');
    ext.ws.close();
  } finally { await bridge.close(); }
});

test('connect() resolves once the extension says hello and times out otherwise', async () => {
  const bridge = await start();
  try {
    await assert.rejects(bridge.connect({ timeout: 50 }), /did not connect/);
    const p = bridge.connect({ timeout: 2000 });
    const ws = await open(bridge, SECRET);
    ws.send(JSON.stringify({ event: 'hello', version: '1.1.0' }));
    await p;
    ws.close();
  } finally { await bridge.close(); }
});

test('newTab -> cdp -> closeTab roundtrip', async () => {
  const bridge = await start();
  try {
    const { seen } = await fakeExtension(bridge);
    const page = await bridge.newPage();
    assert.ok(page instanceof BridgePage);
    assert.equal(page.tabId, 7);
    await page.cdp('Page.enable');
    await page.close();
    assert.deepEqual(seen.map((m) => m.op), ['newTab', 'cdp', 'closeTab']);
    assert.equal(seen[1].method, 'Page.enable');
    assert.equal(seen[1].tabId, 7);
  } finally { await bridge.close(); }
});

test('an extension refusal comes back as an error', async () => {
  const bridge = await start();
  try {
    await fakeExtension(bridge);
    await assert.rejects(bridge.request('cdp', { tabId: 99, method: 'Page.enable' }), /not owned/);
  } finally { await bridge.close(); }
});

test('socket loss rejects in-flight requests', async () => {
  const bridge = await start();
  try {
    const { ws } = await fakeExtension(bridge);
    ws.removeAllListeners('message');
    const p = bridge.request('cdp', { tabId: 7, method: 'x' });
    ws.close();
    await assert.rejects(p, /disconnected/);
  } finally { await bridge.close(); }
});

test('keyboard.press("Meta+A") sends Input.dispatchKeyEvent with Meta and selectAll', async () => {
  const bridge = await start();
  try {
    const { seen } = await fakeExtension(bridge);
    const page = await bridge.newPage();
    await page.keyboard.press('Meta+A');
    await page.keyboard.press('Backspace');
    const keys = seen.filter((m) => m.method === 'Input.dispatchKeyEvent').map((m) => m.params);
    assert.equal(keys.length, 4);
    assert.deepEqual(keys[0], { type: 'rawKeyDown', modifiers: 4, key: 'a', code: 'KeyA', windowsVirtualKeyCode: 65, nativeVirtualKeyCode: 65, commands: ['selectAll'] });
    assert.deepEqual(keys[1], { type: 'keyUp', modifiers: 4, key: 'a', code: 'KeyA', windowsVirtualKeyCode: 65, nativeVirtualKeyCode: 65 });
    assert.equal(keys[2].key, 'Backspace');
    assert.equal(keys[2].modifiers, 0);
    assert.equal(keys[2].windowsVirtualKeyCode, 8);
    await page.keyboard.insertText('hi');
    assert.deepEqual(seen.at(-1).params, { text: 'hi' });
  } finally { await bridge.close(); }
});

test('keyEvents: Control+A, Enter, unknown modifier', () => {
  assert.equal(keyEvents('Control+A')[0].modifiers, 2);
  assert.deepEqual(keyEvents('Control+A')[0].commands, ['selectAll']);
  assert.equal(keyEvents('Enter')[0].text, '\r');
  assert.throws(() => keyEvents('Hyper+A'), /unknown modifier/);
});

test('waitForEvent(filechooser) enables interception first and setFiles uses the node id', async () => {
  const bridge = await start();
  try {
    const { ws, seen } = await fakeExtension(bridge);
    const page = await bridge.newPage();
    const chooser = page.waitForEvent('filechooser', { timeout: 2000 });
    await page.cdp('Runtime.evaluate', { expression: '1' }); // a later action must run after interception is on
    const order = seen.filter((m) => m.op === 'cdp').map((m) => m.method);
    assert.deepEqual(order.slice(0, 2), ['Page.setInterceptFileChooserDialog', 'Runtime.evaluate']);
    ws.send(JSON.stringify({ event: 'cdp', tabId: 7, method: 'Page.fileChooserOpened', params: { frameId: 'f', mode: 'selectSingle', backendNodeId: 42 } }));
    const c = await chooser;
    await c.setFiles('rel/video.mp4');
    const set = seen.find((m) => m.method === 'DOM.setFileInputFiles');
    assert.deepEqual(set.params, { files: [path.resolve('rel/video.mp4')], backendNodeId: 42 });
  } finally { await bridge.close(); }
});

test('pair writes the secret file (0600) and the extension script', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'rp-pair-'));
  const { secretFile, jsFile } = pair({ secretFile: path.join(dir, 'h', 'bridge-secret'), extDir: dir });
  const secret = fs.readFileSync(secretFile, 'utf8').trim();
  assert.match(secret, /^[0-9a-f]{64}$/);
  assert.equal(fs.statSync(secretFile).mode & 0o777, 0o600);
  assert.equal(fs.readFileSync(jsFile, 'utf8'), `self.BRIDGE_SECRET = '${secret}';\n`);
});
