(function (root) {
  'use strict';
  if (typeof root.ticketText !== 'undefined') return;

  function spaces(count) { return new Array(Math.max(0, count) + 1).join(' '); }
  function C(text, width) { return spaces(Math.floor((width - text.length) / 2)) + text; }
  function wrap(text, width) {
    var words = text.split(/\s+/), lines = [], line = '';
    words.forEach(function (word) {
      while (word.length > width) {
        if (line) { lines.push(line); line = ''; }
        lines.push(word.slice(0, width)); word = word.slice(width);
      }
      if (line && line.length + 1 + word.length > width) { lines.push(line); line = word; }
      else line += (line ? ' ' : '') + word;
    });
    if (line) lines.push(line);
    return lines;
  }
  function printName(name) {
    var names = {
      'Pastel de carne de sol com queijo': 'Pastel carne sol c/ queijo',
      'Pastel de frango com catupiry': 'Pastel frango c/ catupiry',
      'Pastel de frango com queijo': 'Pastel frango c/ queijo',
      'Pastel de calabresa com queijo': 'Pastel calabresa c/ queijo',
      'Pizza brotinho de calabresa': 'Pizza calabresa',
      'Pizza brotinho de mussarela': 'Pizza mussarela',
      'Pizza brotinho de frango com catupiry': 'Pizza frango c/ catupiry'
    };
    name = String(name).replace(/[\x00-\x1f\x7f]/g, ' ');
    return Object.prototype.hasOwnProperty.call(names, name) ? names[name] :
      name.replace(/^Pastel de /i, 'Pastel ').replace(/^Pizza brotinho de /i, 'Pizza ').replace(/ com /gi, ' c/ ');
  }
  function pad(value, width) {
    var text = String(value);
    return new Array(Math.max(0, width - text.length) + 1).join('0') + text;
  }

  root.ticketText = function (order, reprint) {
    var width = 32, divider = '--------------------------------';
    var date = order.t;
    var stamp = pad(date.getDate(), 2) + '/' + pad(date.getMonth() + 1, 2) + '/' + date.getFullYear() +
      '  ' + pad(date.getHours(), 2) + ':' + pad(date.getMinutes(), 2);
    var lines = [
      C("D&A LANCHE'S", width),
      '\x03' + C('PEDIDO #' + pad(order.id, 3), width),
      '\x02' + C(stamp, width)
    ];
    if (reprint) lines.push(C('REIMPRESSAO', width));
    lines.push(divider);
    order.itens.forEach(function (item) {
      var quantity = item.q + 'x ';
      var itemLines = wrap(printName(item.n).trim(), width - quantity.length);
      if (!itemLines.length) itemLines.push('');
      itemLines.forEach(function (line, index) {
        lines.push((index === 0 ? quantity : spaces(quantity.length)) + line);
      });
    });
    lines.push(divider, C('Obrigado!', width));
    return lines.join('\n') + '\n';
  };
}(window));
