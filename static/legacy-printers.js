(function (root, document) {
  'use strict';
  if (root.LegacyPrinters) return;
  var config = {}, offered = null, device = null, pendingDevice = null, channel = null, deviceAuth = null;
  var connecting = false, printing = false, generation = 0, activeTimer = null;
  var services = ['000018f0-0000-1000-8000-00805f9b34fb', '0000ffe0-0000-1000-8000-00805f9b34fb',
    '0000ff00-0000-1000-8000-00805f9b34fb', 'e7810a71-73ae-499d-8c15-faa9aef0c3f2',
    '49535343-fe7d-4ae5-8fa9-9fafd205e455', '0000fee7-0000-1000-8000-00805f9b34fb'];
  function el(id) { return document.getElementById(id); }
  function auth() { return config.getAuth ? config.getAuth() : root.AUTH; }
  function message(text) {
    var node = el('legacyPrintMessage'); if (node) node.textContent = text;
    if (config.onMessage) config.onMessage(text);
  }
  function authenticated(value) { return value && (value.role === 'station' || value.role === 'admin') && value.station_id; }
  function allowed(order, destination) {
    var session = auth();
    return authenticated(session) && order && typeof order.id === 'number' && isFinite(order.id) && order.id > 0 && Math.floor(order.id) === order.id && !order.cancel &&
      order.estacao_id === session.station_id && order.impressao_destino === destination &&
      (!config.canPrint || config.canPrint(order, destination));
  }
  function current(job) {
    var order = config.getOrder ? config.getOrder(job.id) : job.order;
    return offered === job && auth() === job.auth && allowed(order, job.destination) ? order : null;
  }
  function dropConnection() {
    var old = device, pending = pendingDevice;
    device = null; pendingDevice = null; channel = null; deviceAuth = null;
    if (old && old.gatt && old.gatt.connected) old.gatt.disconnect();
    if (pending && pending !== old && pending.gatt && pending.gatt.connected) pending.gatt.disconnect();
  }
  function reset() {
    generation++; offered = null; connecting = false; printing = false;
    if (activeTimer !== null) { root.clearTimeout(activeTimer); activeTimer = null; }
    dropConnection();
    var panel = el('legacyPrintSaved'), button = el('legacyPrintOpen');
    if (panel) panel.style.display = 'none';
    if (button) { button.onclick = null; button.disabled = true; }
  }
  function deadline(promise, milliseconds) {
    return new Promise(function (resolve, reject) {
      var timer = root.setTimeout(function () { reject(new Error('Tempo excedido. Confira o papel antes de tentar novamente pelo histórico.')); }, milliseconds);
      activeTimer = timer;
      function clear() { root.clearTimeout(timer); if (activeTimer === timer) activeTimer = null; }
      Promise.resolve(promise).then(function (value) { clear(); resolve(value); }, function (error) { clear(); reject(error); });
    });
  }
  function connected() { return device && channel && device.gatt.connected && deviceAuth === auth(); }
  function connect() {
    if (connecting || printing) { message('Aguarde a operação de impressão atual.'); return Promise.resolve(false); }
    if (!authenticated(auth())) { message('Entre na sua estação antes de conectar.'); return Promise.resolve(false); }
    if (connected()) { dropConnection(); message('Impressora desconectada. Os pedidos continuam salvos.'); return Promise.resolve(false); }
    if (!root.navigator.bluetooth || !root.navigator.bluetooth.requestDevice) {
      message('Bluetooth indisponível neste navegador. O pedido continua salvo no histórico.'); return Promise.resolve(false);
    }
    var epoch = generation, session = auth(), selected = null;
    connecting = true;
    function check() {
      if (epoch !== generation || auth() !== session) {
        if (selected && selected !== device && selected !== pendingDevice && selected.gatt && selected.gatt.connected) selected.gatt.disconnect();
        throw new Error('A sessão mudou; selecione novamente a impressora.');
      }
    }
    var request;
    try { request = root.navigator.bluetooth.requestDevice({acceptAllDevices: true, optionalServices: services}); }
    catch (error) { connecting = false; message('Não conectou: ' + error.message); return Promise.resolve(false); }
    var operation = Promise.resolve(request).then(function (chosen) {
      check(); selected = chosen; pendingDevice = chosen;
      if (!chosen.gatt) throw new Error('Dispositivo sem conexão BLE.');
      return chosen.gatt.connect();
    }).then(function (server) { check(); return server.getPrimaryServices(); }).then(function (available) {
      function find(index) {
        check();
        if (index >= available.length) throw new Error('Não achei canal de impressão nesta impressora.');
        return available[index].getCharacteristics().then(function (channels) {
          check();
          for (var i = 0; i < channels.length; i++) {
            if (channels[i].properties.write || channels[i].properties.writeWithoutResponse) return channels[i];
          }
          return find(index + 1);
        });
      }
      return find(0);
    }).then(function (writable) {
      check();
      // shortcut: preserves the original first writable BLE channel; confirm its print output on the actual printer.
      device = selected; pendingDevice = null; channel = writable; deviceAuth = session;
      selected.addEventListener('gattserverdisconnected', function () {
        if (device === selected) { channel = null; message('Bluetooth desconectado. Confira o papel antes de repetir.'); }
      });
      connecting = false; message('Impressora BLE conectada. A conexão não confirma impressão.'); return true;
    });
    return deadline(operation, 35000).then(function (result) { return result; }, function (error) {
      if (selected && device !== selected && pendingDevice !== selected && selected.gatt && selected.gatt.connected) selected.gatt.disconnect();
      if (epoch === generation) { reset(); message('Não conectou: ' + (error.message || error) + ' Pedido preservado no histórico.'); }
      return false;
    });
  }
  function encode(text) {
    var normalized = typeof text.normalize === 'function' ? text.normalize('NFD').replace(/[\u0300-\u036f]/g, '') : text;
    var bytes = [27, 64, 29, 33, 0, 27, 97, 0];
    for (var i = 0; i < normalized.length; i++) {
      var code = normalized.charCodeAt(i);
      if (code === 1) bytes.push(29, 33, 17);
      else if (code === 2) bytes.push(29, 33, 0);
      else if (code === 3) bytes.push(29, 33, 1);
      else bytes.push(code === 10 || code >= 32 && code <= 126 ? code : 63);
    }
    return new Uint8Array(bytes.concat([29, 33, 0, 27, 97, 0, 10, 10, 10, 10]));
  }
  function send(bytes, epoch, job) {
    var offset = 0, target = channel;
    function next() {
      if (generation !== epoch || !current(job) || target !== channel || !connected()) throw new Error('Envio interrompido. Confira o papel antes de repetir.');
      if (offset >= bytes.length) return;
      var chunk = bytes.subarray(offset, Math.min(bytes.length, offset + 20)); offset += chunk.length;
      if (target.properties.writeWithoutResponse && typeof target.writeValueWithoutResponse === 'function') {
        return Promise.resolve(target.writeValueWithoutResponse(chunk)).then(function () {
          return new Promise(function (resolve) { root.setTimeout(resolve, 20); });
        }).then(next);
      }
      if (typeof target.writeValue !== 'function') throw new Error('Canal BLE não permite gravar os dados.');
      return Promise.resolve(target.writeValue(chunk)).then(next);
    }
    return Promise.resolve().then(next);
  }
  function openOffered() {
    var job = offered, order = job && current(job), button = el('legacyPrintOpen');
    if (!order) { reset(); message('Pedido indisponível para esta sessão. Atualize o histórico.'); return false; }
    if (printing || connecting) { message('Aguarde a operação de impressão atual.'); return false; }
    if (job.reprint && (typeof root.confirm !== 'function' || !root.confirm('Reimprimir o pedido #' + job.id + '? Confira se ele já saiu para evitar duplicidade.'))) {
      message('Reimpressão cancelada. O pedido continua salvo.'); return false;
    }
    if (!current(job)) { reset(); message('A sessão ou o pedido mudou. Atualize o histórico.'); return false; }
    if (!root.navigator.bluetooth) { message('Bluetooth indisponível neste navegador. O pedido continua salvo no histórico.'); return false; }
    var epoch = generation, connection = connected() ? Promise.resolve(true) : connect();
    printing = true; if (button) button.disabled = true;
    Promise.resolve(connection).then(function (ok) {
      if (!ok || !current(job) || epoch !== generation) throw new Error('Impressora não conectada; pedido preservado.');
      return deadline(send(encode(root.ticketText(order, job.reprint)), epoch, job), 45000);
    }).then(function () {
      if (epoch !== generation) return;
      offered = null; printing = false;
      message('Dados enviados à impressora. Confira o papel; isso não confirma a impressão física.');
    }, function (error) {
      if (epoch !== generation) return;
      reset(); message((error.message || String(error)) + ' Confira o papel antes de tentar novamente pelo histórico.');
    });
    return false;
  }
  function offer(order, reprint) {
    var destination = order && order.impressao_destino;
    if (destination !== 'web_bluetooth') return false;
    if (!allowed(order, destination)) { reset(); message('Somente a estação que criou o pedido pode imprimi-lo.'); return false; }
    if (printing || connecting) { message('Há uma operação em andamento. O novo pedido está preservado no histórico.'); return false; }
    offered = {id: order.id, order: order, auth: auth(), destination: destination, reprint: !!reprint};
    var panel = el('legacyPrintSaved'), button = el('legacyPrintOpen');
    if (panel) panel.style.display = 'block';
    if (button) { button.disabled = false; button.textContent = 'Imprimir pelo Bluetooth do navegador'; button.onclick = openOffered; }
    message('Pedido #' + order.id + ' salvo. Toque no botão para abrir a impressão.'); return true;
  }
  root.LegacyPrinters = {configure: function (options) { config = options || {}; }, offer: offer, connect: connect, reset: reset};
}(window, document));
