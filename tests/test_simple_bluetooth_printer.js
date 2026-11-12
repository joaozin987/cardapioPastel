const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

const root = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'da-lanches-pedidos.html'), 'utf8');
const scripts = [...html.matchAll(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/g)].map(match => match[1]);

function deferred() {
  let resolve, reject;
  const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
  return {promise, resolve, reject};
}

function order(id = 1, changes = {}) {
  return {id, t: new Date('2026-11-12T12:00:00'), itens: [{q: 1, n: 'Pastel de queijo', p: 9}],
    estacao_id: 'station-1', impressao_destino: 'simple_bluetooth', impressao_status: 'pendente', ...changes};
}

function app() {
  const elements = new Map(), navigations = [], events = {}, timers = new Map(), notices = [];
  let timerId = 0;
  function element(id) {
    if (!elements.has(id)) elements.set(id, {id, style: {display: 'none'}, value: '', innerHTML: '', textContent: '', disabled: false,
      setAttribute(name, value) { this[name] = value; }, insertAdjacentHTML() {}, appendChild() {}, querySelector: element, focus() {}});
    return elements.get(id);
  }
  const location = {protocol: 'https:'};
  Object.defineProperty(location, 'href', {set(value) { navigations.push(value); }});
  const context = {console: {...console, error() {}}, Headers, location, navigator: {},
    document: {getElementById: element, createElement: () => element(`created-${elements.size}`), querySelector: element,
      head: {appendChild() {}}, addEventListener() {}},
    addEventListener(name, callback) { (events[name] ||= []).push(callback); },
    localStorage: {getItem() { return null; }, setItem() {}, removeItem() {}},
    setTimeout(callback, delay) { const id = ++timerId; timers.set(id, {callback, delay}); return id; },
    clearTimeout(id) { timers.delete(id); }, confirm() { return true; }};
  context.window = context;
  vm.createContext(context);
  for (const filename of ['ticket-text.js', 'simple-bluetooth-printer.js', 'legacy-printers.js', 'print-bridge.js']) {
    vm.runInContext(fs.readFileSync(path.join(root, 'static', filename), 'utf8'), context);
  }
  for (const script of scripts) vm.runInContext('"use strict";\n' + script.replace(/\nstartAuthApp\(\);\s*$/, ''), context);
  context.AUTH = {role: 'station', station_id: 'station-1', csrf_token: 'synthetic-private-csrf'};
  context.toast = text => notices.push(text);
  context.printContext.onMessage = context.toast;
  context.api = async () => { throw new Error('Unexpected API request'); };
  element('printDestination').value = 'simple_bluetooth';
  element('.view.on').id = 'v3';
  return {c: context, element, navigations, timers, events, notices};
}


test('print sends encoded text with autoprint=true and never confirms physical printing', () => {
  const {c,navigations}=app();const saved=order();c.orders=[saved];
  c.ticketText=()=>"\x01D&A\nCafé & queijo + 50%\x02";
  assert.equal(c.SimpleBluetoothPrinter.print(saved,false),true);
  const uri=new URL(navigations[0]);assert.equal(uri.searchParams.get('autoprint'),'true');
  assert.equal(uri.searchParams.get('text'),'D&A\nCafé & queijo + 50%');
  assert.doesNotMatch(navigations[0],/synthetic-private-csrf/);assert.equal(saved.impressao_status,'pendente');
  c.SimpleBluetoothPrinter.print(saved,false);assert.equal(navigations.length,1);
});
test('one cart click saves then launches without history or another button; duplicate clicks save once',async()=>{
  const {c,navigations}=app();const created=deferred(),requests=[];
  c.MENU=[{id:5,n:'Pastel',c:'Pastéis',p:9,e:3,on:true}];c.cart={5:1};
  c.go=()=>{throw new Error('Must remain on catalogue')};
  c.api=async(path,options)=>{requests.push(path);assert.equal(JSON.parse(options.body).impressao_destino,'simple_bluetooth');return created.promise};
  const saving=c.send();await c.send();assert.equal(requests.length,1);assert.equal(navigations.length,0);
  created.resolve({pedido:order()});await saving;
  assert.equal(navigations.length,1);assert.equal(c.orders.length,1);assert.equal(c.MENU[0].e,2);assert.equal(Object.keys(c.cart).length,0);
  await c.send();assert.equal(requests.length,1);assert.equal(navigations.length,1);
});
test('save failure preserves the cart and never opens the app',async()=>{
  const {c,navigations}=app();c.MENU=[{id:5,n:'Pastel',c:'Pastéis',p:9,e:3,on:true}];c.cart={5:1};
  c.api=async()=>{throw new Error('offline')};await c.send();
  assert.equal(c.cart[5],1);assert.equal(c.orders.length,0);assert.equal(c.MENU[0].e,3);assert.equal(navigations.length,0);
});
test('an absent application cannot undo the saved order or decrement stock again',async()=>{
  const {c}=app();c.MENU=[{id:5,n:'Pastel',c:'Pastéis',p:9,e:3,on:true}];c.cart={5:1};let requests=0;
  c.api=async()=>{requests++;return{pedido:order()}};
  c.location={};Object.defineProperty(c.location,'href',{set(){throw new Error('No app')}});
  await c.send();await c.send();assert.equal(requests,1);assert.equal(c.orders.length,1);assert.equal(c.MENU[0].e,2);
});
test('history validates with server and launches directly, without an intermediate panel',async()=>{
  const {c,navigations}=app();c.orders=[order()];let requests=0;
  c.api=async(path,opts)=>{requests++;assert.equal(path,'/api/pedidos/1/impressao/preparar');return{pedido:order()}};
  await c.printSelectedOrder(1);assert.equal(requests,1);assert.equal(navigations.length,1);assert.equal(c.orders[0].impressao_status,'pendente');
});
test('foreign or cancelled orders cannot launch',()=>{
  for(const change of [{cancel:true},{estacao_id:'station-2'}]){const{c,navigations}=app();const saved=order(1,change);c.orders=[saved];assert.equal(c.SimpleBluetoothPrinter.print(saved,false),false);assert.equal(navigations.length,0)}
});
test('a late server response cannot print into another station or clear its cart',async()=>{
  const{c,navigations}=app();const done=deferred();c.MENU=[{id:5,n:'Pastel',c:'Pastéis',p:9,e:3,on:true}];c.cart={5:1};c.api=()=>done.promise;
  const saving=c.send();c.AUTH={role:'admin',station_id:'station-2'};c.cart={5:2};done.resolve({pedido:order()});await saving;
  assert.equal(c.cart[5],2);assert.equal(c.orders.length,0);assert.equal(navigations.length,0);
});
test('late history preparation after reset or logout cannot launch',async()=>{
  for(const change of [c=>c.resetPreparedPrints(),c=>{c.AUTH=null}]){const{c,navigations}=app();c.orders=[order()];const done=deferred();c.api=()=>done.promise;
    const pending=c.printSelectedOrder(1);change(c);done.resolve({pedido:order()});await pending;assert.equal(navigations.length,0)}
});
test('logout blocks any new print immediately while its request is pending',async()=>{
  const{c,navigations}=app();c.orders=[order()];const done=deferred();c.api=()=>done.promise;
  const loggingOut=c.logoutApp();assert.equal(c.canPrintSavedOrder(c.orders[0]),false);
  assert.equal(c.SimpleBluetoothPrinter.print(c.orders[0],false),false);assert.equal(navigations.length,0);
  done.resolve({ok:true});await loggingOut;assert.equal(c.AUTH,null);
});
test('no queue option or multi-step Simple panel remains; adapters stay separate from Babel',()=>{
  assert.doesNotMatch(html,/option value="padrao"|id="simplePrintSaved"/);
  assert.equal(scripts.length,2);assert.match(html,/id="printerSettings"/);
  for(const file of ['ticket-text.js','simple-bluetooth-printer.js','legacy-printers.js'])assert(html.indexOf('/static/'+file)<html.indexOf('<script type="text/babel"'));
});

test('printer settings expose Web Bluetooth, Simple Bluetooth and Android bridge without AirPrint',()=>{
  assert.match(html,/option value="web_bluetooth"/);
  assert.match(html,/option value="simple_bluetooth"/);
  assert.match(html,/option value="print_bridge"/);
  assert.doesNotMatch(html,/option value="airprint"|ipad_api/);
});

test('Android transport saves once and sends the existing ticket, without navigation or printed status', async () => {
  const {c,element,navigations}=app(), done=deferred(), requests=[];
  element('printDestination').value='print_bridge';element('printBridgeCode').value='1234 5678 9012';
  c.MENU=[{id:5,n:'Pastel',c:'Pastéis',p:9,e:3,on:true}];c.cart={5:1};
  c.ticketText=()=>"\x01D&A\nCafé + queijo & 50%\x02";
  c.go=()=>{throw new Error('Must remain on catalogue')};
  c.api=async (path,options)=>{
    requests.push([path,JSON.parse(options.body)]);
    if(path==='/api/pedidos')return {pedido:order()};
    if(path.endsWith('/preparar'))return {pedido:order()};
    assert.equal(path,'/api/pedidos/1/impressao/android');return done.promise;
  };
  const saving=c.send();await Promise.resolve();await Promise.resolve();
  await c.send();assert.equal(requests.length,2);assert.equal(c.SENDING,true);
  assert.equal(requests[0][1].impressao_destino,'simple_bluetooth');
  assert.deepEqual(requests[1][1],{code:'123456789012',text:'D&A\nCafé + queijo & 50%'});
  done.resolve({status:'enviado'});await saving;await c.send();
  assert.equal(requests.length,3);assert.equal(requests.filter(([path])=>path.endsWith('/android')).length,1);assert.equal(navigations.length,0);
  assert.equal(c.orders.length,1);assert.equal(c.MENU[0].e,2);assert.equal(c.orders[0].impressao_status,'pendente');
  assert.match(element('printBridgeStatus').textContent,/enviado ao Android/);
});

test('missing Android code or remote failure preserves the saved order and never retries automatically', async () => {
  for(const code of ['', '１２３４５６７８９０１２', '123456789012']){
    const {c,element,navigations,timers}=app();let calls=0;
    element('printDestination').value='print_bridge';element('printBridgeCode').value=code;
    c.MENU=[{id:5,n:'Pastel',c:'Pastéis',p:9,e:3,on:true}];c.cart={5:1};
    c.api=async path=>{calls++;if(path==='/api/pedidos')return {pedido:order()};throw new Error('Código expirado')};
    await c.send();
    assert.equal(calls,code==='123456789012'?2:1);assert.equal(c.MENU[0].e,2);assert.equal(c.orders.length,1);
    assert.equal(navigations.length,0);assert.equal(c.orders[0].impressao_status,'pendente');
    assert.equal([...timers.values()].filter(t=>t.delay===1800).length,0);
    assert.match(element('printBridgeStatus').textContent,code==='123456789012'?/Código expirado/:/12 dígitos/);
  }
});

test('history reprint via Android revalidates the stored app destination and uses ticketText reprint', async () => {
  const {c,element,navigations}=app(), requests=[];c.orders=[order()];
  element('printDestination').value='print_bridge';element('printBridgeCode').value='123456789012';
  c.api=async(path,options)=>{requests.push([path,JSON.parse(options.body)]);return path.endsWith('/preparar')?{pedido:order()}:{status:'enviado'}};
  await c.printSelectedOrder(1);
  assert.equal(requests.length,2);assert.equal(requests[0][1].destino,'simple_bluetooth');
  assert.match(requests[1][1].text,/REIMPRESSAO/);assert.equal(navigations.length,0);
});

test('Android rejects foreign/cancelled orders and ignores feedback from a previous session', async () => {
  const {c,element,notices}=app(), done=deferred();
  element('printBridgeCode').value='123456789012';c.api=()=>done.promise;
  for(const saved of [order(1,{cancel:true}),order(1,{estacao_id:'station-2'}),order(1,{impressao_destino:'web_bluetooth'})]){
    c.orders=[saved];assert.equal(c.PrintBridge.print(saved,false),false);
  }
  const saved=order();c.orders=[saved];const pending=c.PrintBridge.print(saved,false);
  c.resetPreparedPrints();c.AUTH=null;const before=notices.length;
  done.resolve({status:'enviado'});await pending;assert.equal(notices.length,before);
});

test('Android adapter remains ES5 and never persists the receiving code',()=>{
  const source=fs.readFileSync(path.join(root,'static/print-bridge.js'),'utf8');
  assert.doesNotMatch(source,/\b(?:const|let|async|await)\b|=>|URLSearchParams|localStorage|sessionStorage/);
  assert(html.indexOf('/static/print-bridge.js')<html.indexOf('<script type="text/babel"'));
});
