const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const test = require('node:test');
const path = require('node:path');
const file = process.env.TICKET_FILE || path.join(__dirname, '..', 'static', 'ticket-text.js');
const context = {window:{}};
vm.runInNewContext(fs.readFileSync(file, 'utf8'), context);
const api = context.window;
const order = {id:118,t:'2026-11-19T15:24:00',itens:[
  {q:2,n:'[small]Pastel mistão[/small]'},
  {q:1,n:'Pastel de frango com catupiry'},
  {q:12,n:'Pastel com um nome muito longo para verificar todas as continuacoes'}
]};
const command = /\x1d![\x00\x01]/g;
function inspect(text) {
  let height=1, line='', lines=[];
  for(let i=0;i<text.length;i++) {
    if(text[i]==='\x1d') {
      assert.equal(text[++i], '!');
      const value=text.charCodeAt(++i);
      assert.ok(value===0 || value===1);
      height=value+1;
    } else if(text[i]==='\n') {
      lines.push({text:line,height});line='';
    } else line+=text[i];
  }
  assert.equal(height,1,'normal size restored at the end');
  return lines;
}
test('Only products and footer are taller, including continuation lines',()=>{
  const plain=api.ticketAppText(order,true);
  const result=api.ticketAndroidText(order,true);
  assert.equal(result.replace(command,''),plain,'content and spacing unchanged');
  const lines=inspect(result);
  let section=0;
  for(const line of lines) {
    if(line.text.trim()==='--------------------------------') {
      section++;assert.equal(line.height,1);continue;
    }
    if(!line.text.trim()) continue;
    assert.equal(line.height,section===0?1:2);
    assert.ok(line.text.length<=32);
  }
  assert.ok(lines.some(l=>l.text.includes('2x MISTAO')&&l.height===2));
  assert.ok(lines.some(l=>l.text.includes('CATUPIRY')&&l.height===2));
  assert.equal((result.match(/19\/11\/2026 15:24/g)||[]).length,1);
  assert.doesNotMatch(result,/\[\/?(small|center|right|large)\]|\*\*/i);
});
test('URI encoding preserves commands, all products and a single timestamp',()=>{
  const many={...order,itens:Array.from({length:15},(_,i)=>({q:i+1,n:'Pastel de queijo'}))};
  const text=api.ticketAndroidText(many,false);
  const uri='btprinterplus://print?content='+encodeURIComponent(text);
  assert.equal(decodeURIComponent(uri.split('content=')[1]),text);
  assert.ok(uri.length<=2000,'15-item receipt still fits the direct app URI limit');
  assert.equal((text.match(/PASTEL QUEIJO/g)||[]).length,15);
  assert.equal((text.match(/19\/11\/2026 15:24/g)||[]).length,1);
  inspect(text);
});
test('Header, original remote formatter and invalid dates remain safe',()=>{
  const plain=api.ticketAppText(order,false);
  const text=api.ticketAndroidText(order,false);
  const divider='--------------------------------';
  assert.equal(text.split(divider)[0],plain.split(divider)[0]);
  assert.doesNotMatch(api.ticketText(order,false),/\x1d/);
  assert.doesNotMatch(plain,/\x1d/);
  const invalid=api.ticketAndroidText({...order,t:'invalid'},false);
  assert.doesNotMatch(invalid,/Invalid Date|NaN/);
  inspect(invalid);
});
