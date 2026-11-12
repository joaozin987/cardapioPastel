(function (global) {
  'use strict';
  var context, busy = false, generation = 0, attempted = {};
  function notice(text) {
    if (context && context.onMessage) context.onMessage(text);
    var status = global.document.getElementById('printBridgeStatus');
    if (status) { status.textContent = text; status.className = 'printer-feedback'; }
  }
  function confirmCode() {
    if (!context || !context.getAuth()) return false;
    var input = global.document.getElementById('printBridgeCode');
    var code = input.value.replace(/\s/g, '');
    var valid = /^[0-9]{12}$/.test(code);
    input.setAttribute('aria-invalid', valid ? 'false' : 'true');
    if (valid) {
      input.value = code;
      notice('Código informado nesta página. O Android será consultado ao imprimir o pedido.');
    } else {
      notice('Confira o código: informe os 12 dígitos exibidos no Android.');
      global.document.getElementById('printBridgeStatus').className += ' printer-feedback-error';
      input.focus();
    }
    return false;
  }
  function print(order, reprint) {
    if (busy || !context || !order || !context.getAuth() || context.getOrder(order.id) !== order || !context.canPrint(order, 'simple_bluetooth')) return false;
    var code = global.document.getElementById('printBridgeCode').value.replace(/\s/g, '');
    if (!/^[0-9]{12}$/.test(code)) {
      global.document.getElementById('printerSettings').open = true;
      notice('Pedido salvo. Digite em Configurar impressora o código de 12 dígitos mostrado no Android.');
      return false;
    }
    var now = new Date().getTime();
    if (attempted[order.id] && now - attempted[order.id] < 1200) return false;
    var epoch = generation, owner = context.getAuth();
    var text = String(global.ticketText(order, !!reprint)).replace(/[\x00-\x09\x0b\x0c\x0e-\x1f\x7f]/g, '');
    busy = true;
    attempted[order.id] = now;
    notice('Enviando pedido #' + order.id + ' ao Android...');
    return context.request('/api/pedidos/' + order.id + '/impressao/android', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({code: code, text: text})
    }).then(function () {
      if (epoch === generation && context.getAuth() === owner) notice('Pedido #' + order.id + ' enviado ao Android. Confira a saída na impressora.');
      return true;
    }, function (error) {
      if (epoch === generation && context.getAuth() === owner) {
        global.document.getElementById('printerSettings').open = true;
        notice('Pedido #' + order.id + ' salvo. ' + error.message);
      }
      return false;
    }).then(function (result) { busy = false; return result; });
  }
  global.PrintBridge = {
    configure: function (options) { context = options; generation++; },
    confirmCode: confirmCode,
    print: print,
    reset: function () { generation++; }
  };
}(window));
