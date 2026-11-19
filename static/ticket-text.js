(function (root) {
  'use strict';
  if (typeof root.ticketText !== 'undefined') return;

  function printerText(text) {
    var accents = {
      'á':'a','à':'a','â':'a','ã':'a','ä':'a','Á':'A','À':'A','Â':'A','Ã':'A','Ä':'A',
      'é':'e','è':'e','ê':'e','ë':'e','É':'E','È':'E','Ê':'E','Ë':'E',
      'í':'i','ì':'i','î':'i','ï':'i','Í':'I','Ì':'I','Î':'I','Ï':'I',
      'ó':'o','ò':'o','ô':'o','õ':'o','ö':'o','Ó':'O','Ò':'O','Ô':'O','Õ':'O','Ö':'O',
      'ú':'u','ù':'u','û':'u','ü':'u','Ú':'U','Ù':'U','Û':'U','Ü':'U',
      'ç':'c','Ç':'C','ñ':'n','Ñ':'N'
    };
    return String(text).replace(/\[+\/?(?:small|center|right|large)\]+/gi, '').replace(/[^\x00-\x7f]/g, function (character) {
      return accents[character] || '';
    });
  }
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
    name = String(name).replace(/[\x00-\x1f\x7f]/g, ' ').replace(/\[+\/?(?:small|center|right|large)\]+/gi, '').replace(/\*\*/g, '').trim();
    if (/^pastel\s+(?:de\s+)?mist(?:ão|ao)$/i.test(name)) return 'Mistão';
    if (/^pastel\s+(?:de\s+)?mist[ou]$/i.test(name)) return 'Misto';
    return Object.prototype.hasOwnProperty.call(names, name) ? names[name] :
      name.replace(/^Pastel de /i, 'Pastel ').replace(/^Pizza brotinho de /i, 'Pizza ').replace(/ com /gi, ' c/ ');
  }
  function pad(value, width) {
    var text = String(value);
    return new Array(Math.max(0, width - text.length) + 1).join('0') + text;
  }

  root.ticketText = function (order, reprint) {
    var width = 32, divider = '--------------------------------';
    var lines = [
      '\x02' + C("D&A LANCHE'S", width),
      C('PEDIDO #' + pad(order.id, 3), width)
    ];
    if (reprint) lines.push(C('REIMPRESSAO', width));
    lines.push('\x02' + divider);
    order.itens.forEach(function (item, itemIndex) {
      if (itemIndex) lines.push("", "");
      var quantity = item.q + 'x ';
      var itemLines = wrap(printerText(printName(item.n)).trim().toUpperCase(), width - quantity.length);
      if (!itemLines.length) itemLines.push('');
      itemLines.forEach(function (line, index) {
        var size = index === 0 ? '\x03' : '';
        lines.push(size + (index === 0 ? quantity : spaces(quantity.length)) + line);
      });
    });
    var date = order.t instanceof Date ? order.t : new Date(String(order.t).replace(" ", "T"));
    var stamp = isNaN(date.getTime()) ? '' :
      pad(date.getDate(), 2) + '/' + pad(date.getMonth() + 1, 2) + '/' + date.getFullYear() +
      ' ' + pad(date.getHours(), 2) + ':' + pad(date.getMinutes(), 2);
    lines.push('\x02' + divider);
    if (stamp) lines.push(C(stamp, width));
    return printerText(lines.join('\n') + '\n\x02');
  };

  root.ticketAppText = function (order, reprint) {
    var text = root.ticketText(order, reprint)
      .replace(/[\x00-\x09\x0b-\x1f\x7f]/g, '')
      .replace(/\[+\/?(?:small|center|right|large)\]+/gi, '')
      .replace(/\*\*/g, '');
    return text.replace(/\n+$/, '') + '\n\n\n';
  };

  root.ticketAndroidText = function (order, reprint) {
    var section = 0;
    // ESC/POS GS ! 1 plus ESC E 1: double height and bold, original width.
    // Flush the line before
    // resetting. The direct Android app must pass these bytes to the printer.
    // Print Bridge continues using ticketText, without this transformation.
    return root.ticketAppText(order, reprint).split('\n').map(function (line) {
      var content = line.trim();
      if (content === '--------------------------------') {
        section++;
        return line + '\n';
      }
      var enlarge = content && (section === 1 ||
        (section === 2 && /^\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}$/.test(content)));
      return enlarge ? '\x1d!\x01\x1bE\x01' + line + '\n\x1bE\x00\x1d!\x00' : line + '\n';
    }).join('').slice(0, -1);
  };
}(window));


