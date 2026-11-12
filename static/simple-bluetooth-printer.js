(function (global) {
  'use strict';
  var context, attempted = {}, generation = 0;
  function notice(text) { if (context && context.onMessage) context.onMessage(text); }
  function print(order, reprint) {
    if (!context || !order || !context.getAuth() || context.getOrder(order.id) !== order || !context.canPrint(order, 'simple_bluetooth')) {
      notice('Pedido indisponível nesta estação.'); return false;
    }
    var now = new Date().getTime();
    if (attempted[order.id] && now - attempted[order.id] < 1200) return false;
    reprint = !!reprint || !!attempted[order.id];
    try {
      var text = String(global.ticketText(order, reprint)).replace(/[\x00-\x09\x0b\x0c\x0e-\x1f\x7f]/g, '');
      var url = 'thermalprint://print?text=' + encodeURIComponent(text) + '&autoprint=' + encodeURIComponent('true');
      attempted[order.id] = now;
      var epoch = generation, session = context.getAuth();
      notice('Pedido #' + order.id + ' salvo. Impressão solicitada no aplicativo.');
      // shortcut: iOS may require another tap after a slow save; never resend automatically.
      global.setTimeout(function () {
        if (generation === epoch && context.getAuth() === session && (!global.document || global.document.visibilityState !== 'hidden')) {
          notice('Se o app não abriu, toque novamente em Imprimir pedido. O pedido já está salvo.');
        }
      }, 1800);
      global.location.href = url;
      return true;
    } catch (error) {
      notice('Pedido salvo. Confira o aplicativo e toque novamente em Imprimir pedido.'); return false;
    }
  }
  global.SimpleBluetoothPrinter = {
    configure: function (options) { context = options; generation++; },
    print: print,
    reset: function () { generation++; }
  };
}(window));
