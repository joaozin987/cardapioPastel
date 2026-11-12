'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ticketSource = fs.readFileSync(path.join(__dirname, '../static/ticket-text.js'), 'utf8');
const legacySource = fs.readFileSync(path.join(__dirname, '../static/legacy-printers.js'), 'utf8');
const date = {toLocaleDateString: () => '12/11/2026', toLocaleTimeString: () => '14:05'};
function order(destination) {
  return {id: 7, estacao_id: 'station-1', impressao_destino: destination, cancel: false,
    impressao_status: 'manual', t: date, itens: [{q: 2, n: 'Pastel de carne de sol com queijo', p: 8}]};
}
function deferred() { let resolve; const promise = new Promise(r => { resolve = r; }); return {promise, resolve}; }
async function flush() { for (let i = 0; i < 8; i++) await new Promise(setImmediate); }
function setup(options = {}) {
  const elements = {};
  ['legacyPrintSaved', 'legacyPrintOpen', 'legacyPrintMessage'].forEach(id => {
    elements[id] = {style: {}, textContent: '', disabled: false, onclick: null};
  });
  const nodes = [], stats = {opens: 0, prints: 0, requests: 0, writes: [], apiWrites: 0, confirms: 0, disconnects: 0};
  const popupDocument = {body: {appendChild: node => nodes.push(node)}, html: '',
    open() {}, write(html) { this.html += html; }, close() {}, createElement: tag => ({tag, textContent: ''})};
  const popup = {document: popupDocument, focus() {}, print() { stats.prints++; }};
  let auth = {role: 'station', station_id: 'station-1'}, cached = {};
  let listener;
  const channel = {properties: {write: true}, writeValue(bytes) {
    stats.writes.push(Array.from(bytes));
    return options.onWrite ? options.onWrite(stats.writes.length) : Promise.resolve();
  }};
  const service = {getCharacteristics: () => Promise.resolve([channel])};
  let serviceCalls = 0;
  const device = {name: 'Impressora de teste', addEventListener(type, callback) { listener = callback; },
    gatt: {connected: false, connect() {
      const server = {getPrimaryServices: () => {
        serviceCalls++;
        return options.getServices ? options.getServices(serviceCalls, service) : Promise.resolve([service]);
      }};
      if (options.gattGate) return options.gattGate.promise.then(() => { this.connected = true; return server; });
      this.connected = true; return Promise.resolve(server);
    }, disconnect() { this.connected = false; stats.disconnects++; if (listener) listener(); }}};
  const document = {getElementById: id => elements[id] || null};
  const window = {navigator: {}, setTimeout: (callback, ms) => setTimeout(callback, ms === 20 || options.fastTimeout && ms === 35000 ? 0 : ms), clearTimeout,
    open() { stats.opens++; return popup; }, confirm() { stats.confirms++; return options.confirm !== false; },
    api() { stats.apiWrites++; throw new Error('Printing must not write server state'); },
    fetch() { stats.apiWrites++; throw new Error('Printing must not fetch'); }};
  if (options.bluetooth) window.navigator.bluetooth = {requestDevice() { stats.requests++; return Promise.resolve(device); }};
  const context = vm.createContext({window, document, Promise, Uint8Array});
  vm.runInContext('String.prototype.repeat = undefined; String.prototype.padStart = undefined;', context);
  vm.runInContext(ticketSource, context); vm.runInContext(legacySource, context);
  window.LegacyPrinters.configure({getAuth: () => auth, getOrder: id => cached[id],
    canPrint: (item, destination) => item.impressao_destino === destination});
  return {window, elements, stats, nodes, popupDocument, device, channel, context,
    put(item) { cached[item.id] = item; }, setAuth(value) { auth = value; }};
}

async function main() {
  assert(!/\b(?:const|let|class|async|await)\b|=>|`/.test(ticketSource + legacySource), 'browser modules must use ES5 syntax');
  let h = setup();
  const normal = h.window.ticketText(order('web_bluetooth'), false);
  assert.equal(normal, '\x01  D&A LANCHE\'S\n  PEDIDO #007\n\x02           12/11/2026\n             14:05\n--------------------------------\n\x03\n   2x Pastel carne sol c/ queijo\n--------------------------------\n           Obrigado!');
  assert(h.window.ticketText(order('web_bluetooth'), true).includes('  REIMPRESSAO\n\x02'));
  const names = [
    ['Pastel de frango com catupiry', 'Pastel frango c/ catupiry'],
    ['Pastel de frango com queijo', 'Pastel frango c/ queijo'],
    ['Pastel de calabresa com queijo', 'Pastel calabresa c/ queijo'],
    ['Pizza brotinho de calabresa', 'Pizza calabresa'],
    ['Pizza brotinho de mussarela', 'Pizza mussarela'],
    ['Pizza brotinho de frango com catupiry', 'Pizza frango c/ catupiry'],
    ['Pastel de queijo com tomate', 'Pastel queijo c/ tomate'], ['constructor', 'constructor']
  ];
  names.forEach(([name, expected]) => { const item = order('web_bluetooth'); item.itens[0].n = name; assert(h.window.ticketText(item).includes(expected)); });
  const controlled = order('web_bluetooth'); controlled.itens[0].n = 'Queijo\x1b\x00\x01' + 'X'.repeat(70);
  const cleaned = h.window.ticketText(controlled);
  assert(!/[\x00\x1b]/.test(cleaned)); assert.equal((cleaned.match(/\x01/g) || []).length, 1);
  assert(cleaned.split('\x03\n')[1].split('\n').every(line => line.length <= 32));
  assert.equal(h.window.C, undefined); assert.equal(h.window.wrap, undefined);
  const sentinel = () => 'existing'; const existing = vm.createContext({window: {ticketText: sentinel}});
  vm.runInContext(ticketSource, existing); assert.equal(existing.window.ticketText, sentinel);

  const unsupported = order('web_bluetooth'); h.put(unsupported);
  assert.equal(h.window.LegacyPrinters.offer(unsupported, false), true);
  assert.equal(h.stats.requests + h.stats.opens, 0, 'offer cannot launch printing');
  h.elements.legacyPrintOpen.onclick(); await flush();
  assert(h.elements.legacyPrintMessage.textContent.includes('Bluetooth indisponível'));
  assert.equal(unsupported.impressao_status, 'manual'); assert.equal(h.stats.apiWrites, 0);

  h = setup(); const air = order('airprint'); air.itens[0].n = '<img src=x onerror=alert(1)> & queijo'; h.put(air);
  const before = JSON.stringify(air); h.window.LegacyPrinters.offer(air, true);
  assert.equal(h.stats.opens, 0); h.elements.legacyPrintOpen.onclick();
  assert.equal(h.stats.confirms, 1); assert.equal(h.stats.prints, 1);
  assert(!h.popupDocument.html.includes(air.itens[0].n), 'untrusted names cannot enter document.write');
  assert(h.nodes.some(node => node.textContent === '2x ' + air.itens[0].n));
  assert(h.nodes.some(node => node.textContent.includes('REIMPRESSÃO')));
  assert.equal(JSON.stringify(air), before); assert.equal(h.stats.apiWrites, 0);
  assert(!h.elements.legacyPrintMessage.textContent.includes('Pedido impresso'));
  h.elements.legacyPrintOpen.onclick(); assert.equal(h.stats.prints, 1, 'same offer is consumed once');
  h = setup({confirm: false}); const cancelled = order('airprint'); h.put(cancelled);
  h.window.LegacyPrinters.offer(cancelled, true); h.elements.legacyPrintOpen.onclick();
  assert.equal(h.stats.opens, 0); assert.equal(h.stats.confirms, 1);

  h = setup(); const stale = order('airprint'); h.put(stale); h.window.LegacyPrinters.offer(stale, false);
  h.setAuth({role: 'admin', station_id: 'station-2'}); h.elements.legacyPrintOpen.onclick();
  assert.equal(h.stats.opens, 0);
  h = setup(); h.put(stale); h.window.LegacyPrinters.offer(stale, false); stale.cancel = true;
  h.elements.legacyPrintOpen.onclick(); assert.equal(h.stats.opens, 0);

  h = setup({bluetooth: true}); const ble = order('web_bluetooth'); h.put(ble);
  h.window.LegacyPrinters.offer(ble, false); assert.equal(h.stats.requests, 0);
  h.elements.legacyPrintOpen.onclick(); await flush();
  assert.equal(h.stats.requests, 1); assert(h.stats.writes.length > 1);
  assert(h.stats.writes.every(bytes => bytes.length > 0 && bytes.length <= 20));
  const flattened = h.stats.writes.flat(); assert.deepEqual(flattened.slice(0, 8), [27, 64, 29, 33, 0, 27, 97, 0]);
  assert(h.elements.legacyPrintMessage.textContent.includes('não confirma a impressão física'));
  assert.equal(ble.impressao_status, 'manual'); assert.equal(h.stats.apiWrites, 0); h.window.LegacyPrinters.reset();

  const first = deferred(); h = setup({bluetooth: true, onWrite: count => count === 1 ? first.promise : Promise.resolve()});
  const interrupted = order('web_bluetooth'); h.put(interrupted);
  await h.window.LegacyPrinters.connect(); h.window.LegacyPrinters.offer(interrupted, false); h.elements.legacyPrintOpen.onclick(); await flush();
  assert.equal(h.stats.writes.length, 1); h.setAuth({role: 'station', station_id: 'station-2'}); first.resolve(); await flush();
  assert.equal(h.stats.writes.length, 1, 'session change must stop later chunks');
  assert(!h.elements.legacyPrintMessage.textContent.startsWith('Dados enviados')); assert.equal(h.stats.apiWrites, 0);

  const oldServices = deferred(); h = setup({bluetooth: true, getServices: (count, service) => count === 1 ? oldServices.promise : Promise.resolve([service])});
  const oldConnection = h.window.LegacyPrinters.connect(); await flush(); h.window.LegacyPrinters.reset();
  assert.equal(await h.window.LegacyPrinters.connect(), true);
  oldServices.resolve([]); assert.equal(await oldConnection, false);
  assert.equal(h.device.gatt.connected, true, 'old connection failure must not disconnect a newer selection');
  h.window.LegacyPrinters.reset();
  for (const timedOut of [false, true]) {
    const gate = deferred(); h = setup({bluetooth: true, gattGate: gate, fastTimeout: timedOut});
    const lateConnection = h.window.LegacyPrinters.connect(); await flush();
    if (timedOut) assert.equal(await lateConnection, false); else h.window.LegacyPrinters.reset();
    gate.resolve(); await flush();
    assert.equal(await lateConnection, false);
    assert.equal(h.device.gatt.connected, false, 'late GATT completion after reset/timeout must be disconnected');
  }
  console.log('ticket-text/legacy-printers: layout, ES5, controls, explicit click, ownership, safe AirPrint, BLE chunks and stale connection guards OK');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
