(function (root) {
  'use strict';
  if (typeof root.ticketText !== 'undefined') return;

  function spaces(count) { return new Array(Math.max(0, count) + 1).join(' '); }
  function C(text, width) { return spaces(Math.floor((width - text.length) / 2)) + text; }
  function R(text, width) { text = String(text); return spaces(width - text.length) + text; }
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
  root.ticketText = function (order, reprint) {
    var width = 32, divider = '--------------------------------\n';
    var id = String(order.id); while (id.length < 3) id = '0' + id;
    var date = order.t.toLocaleDateString('pt-BR', {day: '2-digit', month: '2-digit', year: 'numeric'});
    var time = order.t.toLocaleTimeString('pt-BR', {hour: '2-digit', minute: '2-digit'});
    var text = '\x01' + C("D&A LANCHE'S", 16) + '\n' + C('PEDIDO #' + id, 16) + '\n' +
      (reprint ? C('REIMPRESSAO', 16) + '\n' : '') + '\x02' + C(date, width) + '\n' + C(time, width) + '\n' + divider + '\x03';
    order.itens.forEach(function (item) {
      text += '\n' + wrap(item.q + 'x ' + printName(item.n), width).map(function (line) { return R(line, width); }).join('\n') + '\n';
    });
    return text + divider + C('Obrigado!', width);
  };
}(window));
