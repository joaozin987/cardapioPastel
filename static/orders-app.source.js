function formatOrderId(value){var text=String(value);while(text.length<3)text="0"+text;return text}


var NID=1,MENU=[],CF=null,cart={},orders=[],hist=[],seq=1,cat="Todos",EID=0,SENDING=false,REMOVE_PRODUCT_IMAGE=false,IMAGE_PREVIEW_URL=null,PRODUCT_SAVING=false,CATALOG_VERSION=0;
var $=function(i){return document.getElementById(i)},pd=$("pd");
var money=function(v){return "R$ "+v.toFixed(2).replace(".",",")};
async function api(path,options){var r=await fetch(path,options||{}),data=await r.json();if(!r.ok)throw new Error(data.erro||"Falha ao comunicar com o servidor.");return data}
function pedidoFromApi(o){o.t=new Date(String(o.t).replace(" ","T"));return o}
async function loadData(){resetPreparedPrints();var version=++CATALOG_VERSION,data=await api("/api/dados");if(version!==CATALOG_VERSION||PRODUCT_SAVING)return;MENU=data.produtos;orders=data.pedidos.map(pedidoFromApi);hist=[];NID=MENU.reduce(function(n,m){return Math.max(n,m.id+1)},1);seq=orders.reduce(function(n,o){return Math.max(n,o.id+1)},1)}
async function loadProducts(){var version=++CATALOG_VERSION,data=await api("/api/produtos");if(version!==CATALOG_VERSION||PRODUCT_SAVING)return;MENU=data.produtos;NID=MENU.reduce(function(n,m){return Math.max(n,m.id+1)},1)}
async function startApp(){try{await loadData();drawCats();drawGrid();drawHist();hdr()}catch(e){console.error(e);toast("Erro ao carregar o banco: "+e.message)}}
function P(id){return MENU.filter(function(m){return m.id==id})[0]}
function cartStorageKey(){return AUTH?"da-lanches-cart:"+AUTH.station_id:null}
function saveCart(){var key=cartStorageKey();if(!key)return;try{if(Object.keys(cart).length)localStorage.setItem(key,JSON.stringify(cart));else localStorage.removeItem(key)}catch(error){console.error(error);toast("Não foi possível salvar o pedido neste aparelho.")}}
function restoreCart(){var key=cartStorageKey();if(!key)return;try{var saved=localStorage.getItem(key);if(!saved)return;var parsed=JSON.parse(saved),restored={};Object.keys(parsed).forEach(function(id){var product=P(id),quantity=Number(parsed[id]);if(!product||!product.on||product.p==null||!(isFinite(quantity)&&Math.floor(quantity)===quantity)||quantity<1)return;if(product.e!=null)quantity=Math.min(quantity,product.e);if(quantity>0)restored[id]=quantity});cart=restored;saveCart();if(Object.keys(cart).length)toast("Pedido em andamento restaurado.")}catch(error){console.error(error);toast("Não foi possível restaurar o pedido salvo.")}}
function toast(t){var e=$("toast");e.textContent=t;e.style.display="block";setTimeout(function(){e.style.display="none"},1600)}
async function go(n){[1,3,4].forEach(function(i){$("v"+i).className="view"+(n==i?" on":"");$("t"+i).className=n==i?"on":""});$("bar").style.display=n==1?"flex":"none";if(n==1){try{await loadProducts();drawCats();sum()}catch(e){console.error(e);toast("Erro ao atualizar cardápio: "+e.message)}}if(n==3)drawHist();if(n==4)drawProds()}
function cats(){var c=["Todos"];MENU.forEach(function(m){if(m.on&&c.indexOf(m.c)<0)c.push(m.c)});return c}
function allcats(){var c=[];MENU.forEach(function(m){if(c.indexOf(m.c)<0)c.push(m.c)});return c}
function drawCats(){
  var categories=cats();
  if(categories.indexOf(cat)<0)cat="Todos";
  $("cats").innerHTML=categories.map(function(category){
    var active=category===cat;
    return '<button type="button" class="'+(active?"on":"")+'" aria-pressed="'+active+'" data-c="'+escapePrintText(category)+'" onclick="setCat(this.getAttribute(\'data-c\'))">'+menuIconSvg(categoryIcon(category))+'<span>'+escapePrintText(category)+'</span></button>';
  }).join("");
}
function setCat(c){cat=c;drawCats();drawGrid()}
function productCard(m){var q=cart[m.id]||0,hs=m.e!=null,left=hs?m.e-q:0,noPrice=m.p==null;return '<div id="catalog-product-'+m.id+'" class="item'+(q?' has':'')+'"><div class="top">'+productTile(m)+'<div class="pv">'+(noPrice?'Preço a definir':money(m.p))+'</div></div><div><div class="ct">'+escapePrintText(m.c)+'</div><b>'+escapePrintText(m.n)+'</b><div class="ds">'+escapePrintText(m.d||"")+'</div></div><div class="product-controls">'+(noPrice?'<span class="stk lo">Defina o preço para vender</span>':hs?(left<=0?'<span class="stk no">Esgotado</span>':left<=5?'<span class="stk lo">Estoque baixo: restam '+left+'</span>':'<span class="stk ok">'+left+' em estoque</span>'):'<span class="stk ok">Disponível</span>')+'<div class="st"><button onclick="chg('+m.id+',-1)"'+(q?'':' disabled')+'>−</button><b>'+q+'</b><button class="p" onclick="chg('+m.id+',1)"'+(noPrice||hs&&left<=0?' disabled':'')+'>+</button></div></div>'+(AUTH&&AUTH.role==="admin"?'<button type="button" class="catalog-edit" onclick="editCatalogProduct('+m.id+')">Editar</button>':'')+'</div>'}
function drawGrid(){$("grid").innerHTML=MENU.filter(function(m){return m.on&&(cat=="Todos"||m.c==cat)&&m.n.toLowerCase().indexOf($("sr").value.toLowerCase())>=0}).map(productCard).join("")}
function updateProductCard(id){
var card=$("catalog-product-"+id),product=P(id);
if(card&&product)card.outerHTML=productCard(product);
}
async function editCatalogProduct(id){
if(!AUTH||AUTH.role!=="admin")return;
if(!P(id)){toast("Produto não encontrado. Atualize o catálogo.");return}
await go(4);
var card=$("stock-product-"+id);
if(card)card.scrollIntoView();
edit(id);
}
function chg(id,d){var pm=P(id);if(d>0&&pm.p==null){toast("Defina o preço do produto antes de vender");return}if(d>0&&pm.e!=null&&(cart[id]||0)>=pm.e){toast("Sem estoque");return}cart[id]=(cart[id]||0)+d;if(cart[id]<=0)delete cart[id];saveCart();sum(false);updateProductCard(id)}
function total(){return Object.keys(cart).reduce(function(s,i){return s+P(i).p*cart[i]},0)}
function count(){return Object.keys(cart).reduce(function(s,i){return s+cart[i]},0)}
function sum(redraw){
  var quantity=count();
  $("n").textContent=quantity+(quantity===1?" item":" itens");
  $("tot").textContent=money(total());
  $("rev").disabled=!quantity||SENDING||PRINT_PREPARING;
  $("rev").textContent=SENDING?"Salvando pedido...":"Imprimir pedido";
  updateReprintButton();
  if(redraw!==false)drawGrid();
}
var menuIcons={
  all:'<path d="M4 5h9v9H4zM19 5h9v9h-9zM4 20h9v9H4zM19 20h9v9h-9z" fill="#f2cc79"/>',
  pastel:'<g transform="rotate(-12 16 16)"><path d="M7 4h18l2 2v20l-2 2H7l-2-2V6z" fill="#f6b950"/><rect x="9" y="8" width="14" height="16" rx="3" fill="#ffe09b"/><path d="M9 4v2m5-2v2m5-2v2m5-2v2M9 26v2m5-2v2m5-2v2m5-2v2M5 10h2m-2 6h2m-2 6h2m18-12h2m-2 6h2m-2 6h2"/></g>',
  coxinha:'<path d="M16 3c2 5 10 10 11 17 1 6-4 9-11 9S4 26 5 20C6 13 14 8 16 3Z" fill="#f3ad53"/><path d="M10 19l1-2m3 7 2 1m5-7 1 2m-7-8h1"/>',
  pizza:'<path d="M4 7Q16 0 28 7L16 29Z" fill="#ffd378"/><path d="M4 7Q16 0 28 7l-3 5q-9-5-18 0z" fill="#e9a053"/><circle cx="13" cy="13" r="2" fill="#db6b52"/><circle cx="21" cy="14" r="2" fill="#db6b52"/><circle cx="16" cy="21" r="2" fill="#db6b52"/>',
  cane:'<path d="M5 27L9 7l3 .6L8 27Z" fill="#90c781"/><path d="M8 13l3 .6m-4 6 3 .6M10 8c-1-4 2-5 5-5-1 3-2 4-5 5Z" fill="#79ad64"/><path d="M13 11h15l-2 16H15z" fill="#f5f0c5"/><path d="M14 17h13l-1 10H15z" fill="#b3c979"/><path d="M21 20l2-14h5m-9 15h1m2 3h1"/>',
  juice:'<path d="M7 10h18l-2 17H9z" fill="#fff3ca"/><path d="M8 15h16l-1 12H9z" fill="#ffbb57"/><path d="M17 22 20 6h5"/><path d="M23 10a5 5 0 0 1 7 5h-6z" fill="#ffac54"/>',
  drink:'<path d="M7 9h18l-2 18H9z" fill="#b9dcec"/><path d="M6 7h20v4H6z" fill="#e6f3fa"/><path d="M18 7l2-4h5m-4 13-2 5h-5l-2-5h9z" fill="#eff8ff"/>',
  can:'<rect x="8" y="5" width="16" height="23" rx="4" fill="#ed927f"/><path d="M9 7h14m-14 19h14M15 5V3h5"/><path d="M9 16c5-5 9 4 14 0" stroke="#fff5e7" stroke-width="3"/>',
  bottle:'<path d="M13 5h6v6c0 2 4 3 4 7v8c0 2-2 3-4 3h-6c-2 0-4-1-4-3v-8c0-4 4-5 4-7z" fill="#a8cf88"/><path d="M12 4h8v4h-8z" fill="#e8dfa0"/><path d="M9 17h14v7H9z" fill="#f4edcc"/>',
  water:'<path d="M16 3C12 9 7 15 7 21a9 9 0 0 0 18 0c0-6-5-12-9-18Z" fill="#a7d6ef"/><path d="M11 21c0 3 2 4 4 5" stroke="#f4fbff" stroke-width="2.5"/>',
  lasagna:'<path d="m4 10 16-5 8 5-15 6Z" fill="#e58d65"/><path d="M4 10v13l9 5 15-6V10l-15 6z" fill="#f8c566"/><path d="m4 14 9 5 15-6m-24 6 9 5 15-6" stroke="#a54e38"/><path d="M9 10l3-1m6 1 4-1" stroke="#fff1bd" stroke-width="2.5"/>',
  food:'<path d="M5 22h22m-20 0a9 9 0 0 1 18 0m-9-9V9m-2 0h4" fill="#f4d3a1"/>'
};
function menuKey(value){
  return String(value||"").toLowerCase()
    .replace(/[áàâãä]/g,"a").replace(/[éèêë]/g,"e").replace(/[íìîï]/g,"i")
    .replace(/[óòôõö]/g,"o").replace(/[úùûü]/g,"u").replace(/ç/g,"c")
    .replace(/[^a-z0-9]+/g," ").trim();
}
function categoryIcon(category){
  var key=menuKey(category);
  if(key==="todos")return "all";
  if(/\b(pastel|pasteis)\b/.test(key))return "pastel";
  if(/\bcoxinhas?\b/.test(key))return "coxinha";
  if(/\bpizzas?\b/.test(key))return "pizza";
  if(/\blasanhas?\b/.test(key))return "lasagna";
  if(/\b(caldo|caldos|garapa)\b/.test(key))return "cane";
  if(/\bsucos?\b/.test(key))return "juice";
  if(/\b(refrigerante|refrigerantes)\b/.test(key))return "can";
  if(/\bbebidas?\b/.test(key))return "drink";
  return "food";
}
function productIcon(product){
  var name=menuKey(product.n);
  if(/\b(caldo|garapa)\b/.test(name))return "cane";
  if(/\bsucos?\b/.test(name))return "juice";
  if(/\bagua\b/.test(name))return "water";
  if(/\b(lata|latinha)\b/.test(name))return "can";
  if(/\b(garrafa|garrafinha|pitulinha|guarana)\b/.test(name))return "bottle";
  if(/\b(coca|pepsi|fanta|sprite|refrigerante)\b/.test(name))return "can";
  var named=categoryIcon(name);
  return named==="food"||named==="all"?categoryIcon(product.c):named;
}
function menuIconSvg(icon){
  return '<svg class="menu-icon" aria-hidden="true" focusable="false" viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'+menuIcons[icon]+'</svg>';
}
function escapePrintText(value){
  return String(value).replace(/[&<>"']/g,function(character){
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[character];
  });
}
function productTile(product){
  var icon=productIcon(product);
  var image=product.img?'<img src="'+escapePrintText(product.img)+'" alt="" onerror="this.style.display=&quot;none&quot;">':"";
  return '<div class="tile tile-'+icon+'" aria-hidden="true">'+menuIconSvg(icon)+image+'</div>';
}
var EX=null;
function tgl(id){EX=EX==id?null:id;drawHist()}
function det(o){var h='<div class="dt"><div class="dl"><span>Pedido #'+formatOrderId(o.id)+'</span><span>'+o.t.toLocaleDateString("pt-BR")+' '+o.t.toLocaleTimeString("pt-BR",{hour:"2-digit",minute:"2-digit"})+'</span></div>';
o.itens.forEach(function(x){h+='<div class="dl"><span>'+x.q+'x '+x.n+'</span><span>'+money(x.p)+' cada → <b>'+money(x.q*x.p)+'</b></span></div>'});
var printLabels={pendente:"Sem confirmação",imprimindo:"Enviando",impresso:"Impresso",falhou:"Falha na impressão"};
return h+'<div class="dl"><span>Situação</span><span>'+(o.cancel?'Cancelado':o.pronto?'Entregue':'Em preparo')+'</span></div><div class="dl"><span>Destino</span><span>'+printDestinationLabel(o.impressao_destino)+'</span></div><div class="dl"><span>Impressão</span><span>'+(o.impressao_status==="pendente"&&printDestinationOf(o)!=="padrao"?"Aguardando impressão no aparelho":printLabels[o.impressao_status]||"Não informado")+'</span></div><div class="dl tt"><span>Total</span><span>'+money(tot(o))+'</span></div></div><button class="btn alt" type="button" onclick="tgl('+o.id+')">Voltar</button>'}
function hdr(){updateReprintButton();var today=new Date().toDateString(),daily=hist.concat(orders).filter(function(o){return o.t.toDateString()===today&&!o.cancel});$("hs").innerHTML='<small>HOJE</small><b>'+daily.length+' pedidos · '+money(daily.reduce(function(total,order){return total+tot(order)},0))+'</b>'}
function tot(o){return o.itens.reduce(function(s,x){return s+x.p*x.q},0)}
async function cancelOrder(id){if(CF!=id){CF=id;drawHist();return}resetPreparedPrints();try{await api("/api/pedidos/"+id+"/cancelar",{method:"POST"});CF=null;await loadData();drawHist();hdr();toast("Pedido cancelado")}catch(e){toast("Erro ao cancelar pedido: "+e.message)}}
function drawHist(){var all=hist.concat(orders),day=86400000,now=new Date(),st=new Date(now.getFullYear(),now.getMonth(),now.getDate()).getTime();
function agg(f){var l=all.filter(function(o){return o.t.getTime()>=f&&!o.cancel});return{n:l.length,v:l.reduce(function(s,o){return s+tot(o)},0)}}
$("sum").innerHTML=[["Hoje",agg(st)],["Últimos 7 dias",agg(st-6*day)],["Últimos 30 dias",agg(st-29*day)]].map(function(a){return '<div class="sc"><small>'+a[0]+'</small><b>'+a[1].n+' pedidos</b><span>'+money(a[1].v)+'</span></div>'}).join("");
var q=$("q").value.toLowerCase().replace("#","").trim(),fd=function(o){return o.t.toLocaleDateString("pt-BR",{day:"2-digit",month:"2-digit"})},today=now.toLocaleDateString("pt-BR",{day:"2-digit",month:"2-digit"});
var l=all.slice().sort(function(a,b){return b.t-a.t}).filter(function(o){return!q||String(o.id)==q.replace(/^0+/,"")||o.itens.some(function(x){return x.n.toLowerCase().indexOf(q)>=0})}).slice(0,60),days={},keys=[];
l.forEach(function(o){var k=fd(o);if(!days[k]){days[k]=[];keys.push(k)}days[k].push(o)});
$("hist").innerHTML=keys.length?keys.map(function(k){var a=days[k],v=a.filter(function(o){return!o.cancel});
return '<div class="dh"><span>'+(k==today?"Hoje · ":"")+k+'</span><span>'+v.length+' pedidos · '+money(v.reduce(function(s,o){return s+tot(o)},0))+'</span></div>'+a.map(function(o){
return '<div class="oc"><div class="row" onclick="tgl('+o.id+')" style="cursor:pointer"><span><b>Pedido #'+formatOrderId(o.id)+(o.cancel?' (CANCELADO)':'')+'</b><br><small style="color:var(--mut)">'+o.t.toLocaleTimeString("pt-BR",{hour:"2-digit",minute:"2-digit"})+' · '+o.itens.map(function(x){return x.q+"x "+x.n}).join(", ")+'</small></span><span style="white-space:nowrap"><b'+(o.cancel?' style="text-decoration:line-through"':'')+'>'+money(tot(o))+'</b>'+(o.cancel?'':'<button class="rp" onclick="event.stopPropagation();cancelOrder('+o.id+')">'+(CF==o.id?'Confirmar?':'Cancelar')+'</button>')+'</span></div>'+orderPrintButton(o)+(EX==o.id?det(o):'')+'</div>'}).join("")}).join(""):'<div class="empty">Nenhum pedido encontrado.</div>'}
function drawProds(){$("prods").innerHTML=MENU.slice().sort(function(a,b){return String(b.updated||"").localeCompare(String(a.updated||""))||b.id-a.id}).map(function(m){return '<div id="stock-product-'+m.id+'" class="pc'+(m.on?'':' off')+'">'+productTile(m)+'<b>'+m.n+'</b><small>'+m.c+(m.e!=null?' · estoque: '+m.e:' · sem controle de estoque')+'</small><span class="pr">'+(m.p==null?'Preço a definir':money(m.p))+'</span><label class="sw"><input type="checkbox" '+(m.on?'checked ':'')+'onchange="tog('+m.id+')">'+(m.on?'Ativo':'Desativado')+'</label><button class="ed" onclick="edit('+m.id+')">✎ Editar</button></div>'}).join("")}
async function tog(id){var m=P(id);try{await api("/api/produtos",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:m.id,n:m.n,c:m.c,d:m.d,p:m.p,e:m.e,on:!m.on})});await loadData();drawProds();drawCats();drawGrid()}catch(e){toast("Erro ao atualizar produto: "+e.message)}}
function cs(){$("pc").style.display=$("ps").value=="__new"?"block":"none"}
function showImagePreview(src){var img=$("pimg"),fallback=$("pimgFallback");if(IMAGE_PREVIEW_URL&&src!==IMAGE_PREVIEW_URL){URL.revokeObjectURL(IMAGE_PREVIEW_URL);IMAGE_PREVIEW_URL=null}if(src){img.src=src;img.style.display="block";fallback.style.display="none"}else{img.removeAttribute("src");img.style.display="none";fallback.style.display="";}$("removeProductImageBtn").style.display=src||EID&&P(EID).img?"block":"none"}
function previewProductImage(input){var file=input.files&&input.files[0];if(!file)return;REMOVE_PRODUCT_IMAGE=false;IMAGE_PREVIEW_URL=URL.createObjectURL(file);showImagePreview(IMAGE_PREVIEW_URL)}
function clearProductImage(){if(IMAGE_PREVIEW_URL){URL.revokeObjectURL(IMAGE_PREVIEW_URL);IMAGE_PREVIEW_URL=null}$("pi").value="";REMOVE_PRODUCT_IMAGE=true;showImagePreview("")}
function edit(id){EID=id;var m=id?P(id):{n:"",c:allcats()[0],p:null,on:true,img:null};REMOVE_PRODUCT_IMAGE=false;$("pi").value="";$("pdt").textContent=id?"Editar produto":"Novo produto";$("pn").value=m.n;showImagePreview(m.img);
$("ps").innerHTML=allcats().map(function(c){return '<option'+(c==m.c?' selected':'')+'>'+c+'</option>'}).join("")+'<option value="__new">+ Nova categoria...</option>';cs();$("pc").value="";
$("pp").value=m.p==null?"":String(m.p.toFixed(2)).replace(".",",");$("pa").checked=m.on;$("pe").value=m.e==null?"":m.e;pd.showModal()}
async function saveP(){if(PRODUCT_SAVING)return;var n=$("pn").value.trim(),c=$("ps").value=="__new"?$("pc").value.trim():$("ps").value,priceText=$("pp").value.trim(),p=priceText?parseFloat(priceText.replace(",",".")):null;
if(!n||!c||(priceText&&(isNaN(p)||p<0))){toast("Confira nome, categoria e preço");return}
var ev=$("pe").value.trim(),e=ev===""?null:parseInt(ev,10);if(ev!==""&&(isNaN(e)||e<0)){toast("Estoque inválido");return}
var data={n:n,c:c,p:p,e:e,d:EID&&P(EID)?P(EID).d:"",on:$("pa").checked};if(EID){data.id=EID}
PRODUCT_SAVING=true;CATALOG_VERSION++;
try{var body=new FormData();Object.keys(data).forEach(function(key){body.append(key,data[key]==null?"":data[key])});body.append("remove_image",REMOVE_PRODUCT_IMAGE?"true":"false");if($("pi").files[0])body.append("image",$("pi").files[0]);var result=await api("/api/produtos",{method:EID?"PUT":"POST",body:body}),product=result.produto,index=MENU.findIndex(function(m){return m.id==product.id});CATALOG_VERSION++;if(index<0)MENU.push(product);else MENU[index]=product;NID=Math.max(NID,product.id+1);cat="Todos";$("sr").value="";pd.close();drawProds();drawCats();sum();toast("Produto salvo e cardápio atualizado")}catch(err){toast("Erro ao salvar produto: "+err.message)}finally{PRODUCT_SAVING=false}}



var AUTH=null,CSRF_TOKEN="";
var authStyle=document.createElement("style");
authStyle.textContent=`
#loginScreen{position:fixed;inset:0;z-index:200;display:grid;place-items:center;overflow:auto;padding:28px 18px;background:radial-gradient(ellipse at 12% 12%,#68471b 0,transparent 34%),linear-gradient(135deg,#17130d,#292016 58%,#17130d);color:#241f18}
.login-shell{display:grid;grid-template-columns:1fr .92fr;width:min(900px,100%);min-height:520px;overflow:hidden;border:1px solid rgba(255,255,255,.16);border-radius:26px;background:#fffdf8;box-shadow:0 28px 90px rgba(0,0,0,.42)}
.login-brand{position:relative;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;padding:38px;color:#fff;background:linear-gradient(155deg,#30251a,#17130f 76%);isolation:isolate}
.login-brand:before,.login-brand:after{position:absolute;z-index:-1;content:"";border:1px solid rgba(224,162,27,.2);border-radius:50%}
.login-brand:before{width:360px;height:360px;right:-170px;top:-150px}
.login-brand:after{width:280px;height:280px;right:-110px;top:-110px}
.login-logo{width:66px;height:66px;object-fit:cover;border:2px solid #e0a21b;border-radius:50%;box-shadow:0 0 0 7px rgba(224,162,27,.12)}
.login-brand-copy{max-width:370px;margin:50px 0}
.login-eyebrow{display:block;margin-bottom:14px;color:#e8b643;font-size:11px;font-weight:900;letter-spacing:2.2px;text-transform:uppercase}
.login-brand h1{margin:0 0 14px;font-size:clamp(30px,4vw,43px);line-height:1.08;letter-spacing:-1.3px}
.login-brand-copy p{margin:0;color:#d4c7b1;font-size:15px;line-height:1.7}
.login-foot{color:#a99b84;font-size:12px}
.login-form-panel{display:flex;align-items:center;justify-content:center;padding:42px}
.login-form-content{width:min(360px,100%)}
.login-form-content h2{margin:0 0 8px;color:#241f18;font-size:27px;letter-spacing:-.6px}
.login-subtitle{margin:0 0 28px;color:#766a58;font-size:14px;line-height:1.5}
#loginForm label{display:block;margin:17px 0 7px;color:#443b2e;font-size:12px;font-weight:900;letter-spacing:.35px}
#loginForm select,#loginForm input{width:100%;height:50px;margin:0;padding:0 13px;border:1px solid #e5dcc9;border-radius:11px;outline:none;background:#fff;color:#241f18;font:inherit;transition:border-color .15s,box-shadow .15s}
#loginForm select:focus,#loginForm input:focus{border-color:#c58c16;box-shadow:0 0 0 4px rgba(224,162,27,.16)}
#loginCredential{letter-spacing:1.5px}
#loginForm .btn{height:50px;margin-top:24px;border-radius:11px;background:#d99a13;color:#20180b;font-size:15px;box-shadow:0 5px 12px rgba(185,125,0,.2)}
#loginForm .btn:hover{background:#e5a71f}
#loginError{min-height:20px;margin-top:12px;color:#a52e1b;font-size:13px;font-weight:700}
.login-secure{display:flex;align-items:center;gap:8px;margin-top:18px;color:#827764;font-size:12px}
.auth-badge{display:flex;align-items:center;gap:8px;margin-left:auto}.auth-badge button{border:1px solid var(--gold);background:transparent;color:var(--gold);border-radius:8px;padding:8px;font-weight:800;cursor:pointer}
.admin-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin:14px 0}.admin-card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}.admin-card small{display:block;color:var(--mut);font-weight:800}.admin-card b{font-size:20px}.admin-note{background:var(--line);padding:12px;border-radius:10px;margin:12px 0}
@media(max-width:680px){#loginScreen{padding:16px}.login-shell{grid-template-columns:1fr;min-height:0;max-width:460px;border-radius:22px}.login-brand{min-height:190px;padding:24px 26px}.login-logo{width:52px;height:52px}.login-brand-copy{margin:26px 0 0}.login-brand h1{font-size:29px}.login-brand-copy p{font-size:13px}.login-foot{display:none}.login-form-panel{padding:28px 26px 30px}.login-form-content h2{font-size:24px}.login-subtitle{margin-bottom:20px}}
@media(max-height:700px) and (min-width:681px){#loginScreen{padding:16px}.login-shell{min-height:460px}.login-brand,.login-form-panel{padding:28px}.login-brand-copy{margin:24px 0}}
`;
document.head.appendChild(authStyle);
document.querySelector("header").insertAdjacentHTML("beforeend",'<div class="auth-badge" id="authBadge" style="display:none"><span id="authName"></span><button onclick="logoutApp()">Sair</button></div>');
document.querySelector("nav.tabs").insertAdjacentHTML("beforeend",'<button id="t5" onclick="go(5)" style="display:none">Administrador</button>');
var adminView=document.createElement("section");
adminView.className="view";
adminView.id="v5";
adminView.innerHTML='<h2>Painel do administrador</h2><p>Resumo do dia e acesso ao catálogo.</p><div id="adminSummary"></div><button class="btn" onclick="go(4)">Gerenciar produtos e fotos</button>';
document.querySelector("main").appendChild(adminView);
var productView=$("v4");
productView.insertAdjacentHTML("afterbegin",'<button class="btn alt" id="adminBack" style="margin:0 0 12px;display:none" onclick="go(5)">Voltar ao painel</button>');

api=async function(path,options){
var opts=options||{},method=(opts.method||"GET").toUpperCase(),headers=new Headers(opts.headers||{});
if(method!=="GET"&&CSRF_TOKEN)headers.set("X-CSRF-Token",CSRF_TOKEN);
opts.headers=headers;
var r=await fetch(path,opts),data=await r.json();
if(!r.ok)throw new Error(data.erro||"Falha ao comunicar com o servidor.");
return data
};
function showLogin(){
LOGGING_OUT=false;$("printBridgeCode").value="";$("printBridgeStatus").textContent="";

document.querySelector("header").style.display="none";$("authBadge").style.display="none";
document.querySelector("nav.tabs").style.display="none";document.querySelector("main").style.display="none";$("bar").style.display="none";
var box=$("loginScreen");
if(!box){box=document.createElement("section");box.id="loginScreen";document.body.insertBefore(box,document.querySelector("header"))}
box.innerHTML='<div class="login-shell"><section class="login-brand"><img class="login-logo" src="" alt="D&A Lanche\'s"><div class="login-brand-copy"><span class="login-eyebrow">Sistema de pedidos</span><h1>Bom ter você<br>por aqui.</h1><p>Acesse sua estação para organizar os pedidos com rapidez e manter tudo funcionando em sintonia.</p></div><div class="login-foot">D&A Lanche\'s · Acesso seguro</div></section><section class="login-form-panel"><div class="login-form-content"><span class="login-eyebrow">Bem-vindo</span><h2>Entrar no sistema</h2><p class="login-subtitle">Selecione seu acesso e informe suas credenciais para continuar.</p><form id="loginForm"><label for="loginAccount">TIPO DE ACESSO</label><select id="loginAccount"><option value="employee">Funcionário</option><option value="admin">Administrador</option></select><label id="credentialLabel" for="loginCredential">PIN DO FUNCIONÁRIO</label><input id="loginCredential" type="password" autocomplete="current-password" placeholder="Digite seu PIN" required><button class="btn" type="submit">Entrar</button><div id="loginError" role="alert" aria-live="polite"></div></form><div class="login-secure"><span aria-hidden="true">●</span> Acesso protegido por credenciais</div></div></section></div>';
box.querySelector(".login-logo").src=document.querySelector("header img").src;
var select=$("loginAccount");
select.onchange=function(){var isAdmin=select.value==="admin";$("credentialLabel").textContent=isAdmin?"PIN DO ADMINISTRADOR":"PIN DO FUNCIONÁRIO";$("loginCredential").placeholder=isAdmin?"Digite seu PIN":"Digite seu PIN";$("loginCredential").value=""};
$("loginForm").onsubmit=async function(event){
event.preventDefault();$("loginError").textContent="";
try{AUTH=await api("/api/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({account:select.value,credential:$("loginCredential").value})});CSRF_TOKEN=AUTH.csrf_token;await enterApp()}
catch(error){$("loginError").textContent=error.message}
};
box.style.display="block";$("loginCredential").focus()
}
function showApp(){
var box=$("loginScreen");if(box)box.style.display="none";
document.querySelector("header").style.display="flex";document.querySelector("nav.tabs").style.display="flex";document.querySelector("main").style.display="block";
ensureRefreshButton();
$("authBadge").style.display="flex";$("authName").textContent=AUTH.station_name;
var isAdmin=AUTH.role==="admin";
$("bar").style.display="flex";
$("t1").style.display="";
$("t3").style.display="";
$("t4").style.display=isAdmin?"":"none";
$("t5").style.display=isAdmin?"":"none";
$("pb").style.display="";

$("adminBack").style.display=isAdmin?"block":"none";
}
async function enterApp(){

showApp();
restorePrintDestination();
changePrintDestination();
await loadData();restoreCart();drawCats();drawHist();hdr();go(1,true)
}
async function startAuthApp(){


if(location.protocol==="file:"){
showLogin();
$("loginError").innerHTML='Esta cópia do arquivo não conecta ao servidor. Abra o sistema pelo Flask: <a href="http://127.0.0.1:5000">http://127.0.0.1:5000</a>.';
return
}
try{

var r=await fetch("/api/auth/session"),data=await r.json();

if(!r.ok)throw new Error(data.erro||"Não foi possível iniciar a sessão.");
CSRF_TOKEN=data.csrf_token;

if(!data.authenticated){showLogin();return}
AUTH=data;await enterApp()
}catch(error){console.error(error);showLogin();toast("Erro ao iniciar: "+error.message)}
}
async function go(n,useCurrentProducts){

[1,3,4,5].forEach(function(i){var v=$("v"+i),t=$("t"+i);if(v)v.className="view"+(n===i?" on":"");if(t)t.className=n===i?"on":""});
$("bar").style.display=n===1&&AUTH?"flex":"none";
if(n===1){try{if(!useCurrentProducts)await loadProducts();drawCats();sum()}catch(error){console.error(error);toast("Erro ao atualizar cardápio: "+error.message)}}
if(n===3)drawHist();
if(n===4)drawProds();
if(n===5)await loadAdminSummary()
}
async function loadAdminSummary(){
try{
var data=await api("/api/admin/resumo"),states=data.impressao_hoje||{};
$("adminSummary").innerHTML='<div class="admin-cards"><div class="admin-card"><small>Pedidos hoje</small><b>'+data.pedidos_hoje+'</b></div><div class="admin-card"><small>Vendas hoje</small><b>'+money(data.vendas_hoje)+'</b></div><div class="admin-card"><small>Produtos ativos</small><b>'+data.produtos_ativos+' / '+data.produtos_total+'</b></div></div><h3>Impressões de hoje</h3><div class="hint">Aguardando: '+(states.pendente||0)+' · Em andamento: '+(states.imprimindo||0)+' · Impressos: '+(states.impresso||0)+' · Falhas: '+(states.falhou||0)+'</div><h3>Estações</h3><div class="hint">'+data.estacoes.map(function(s){return s.nome+": "+(s.configurada?"PIN configurado":"PIN não configurado")}).join("<br>")+'</div><p class="admin-note">Os pedidos continuam compartilhados. Cada pedido registra a estação que o criou; a impressão fica no aparelho dessa estação.</p>'
}catch(error){$("adminSummary").innerHTML='<div class="hint">Não foi possível carregar o painel: '+error.message+'</div>'}
}
async function logoutApp(){
LOGGING_OUT=true;SAVE_REQUEST=null;SENDING=false;resetPreparedPrints();
$("printDestination").disabled=false;
try{await api("/api/auth/logout",{method:"POST"})}catch(error){console.error(error)}
cart={};saveCart();AUTH=null;CSRF_TOKEN="";MENU=[];orders=[];showLogin()
}
var REFRESHING=false;
window.addEventListener("keydown",function(event){
var key=event.key||"",reloadKey=key==="F5"||(key.toLowerCase()==="r"&&(event.ctrlKey||event.metaKey));
if(!reloadKey||!AUTH)return;
event.preventDefault();
event.stopPropagation();
if($("pd").open){toast("Feche o formulário antes de atualizar os dados.");return}
refreshAppData()
},true);
function ensureRefreshButton(){
if($("refreshDataButton"))return;
var button=document.createElement("button");
button.id="refreshDataButton";
button.className="refresh-data";
button.type="button";
button.textContent="↻ Atualizar dados (sem desconectar)";
button.onclick=function(){refreshAppData()};
document.querySelector("main").insertBefore(button,document.querySelector("main").firstChild)
}
async function refreshAppData(silent){
if(SENDING){toast("Aguarde a impressão terminar antes de atualizar.");return}
if(REFRESHING||PRODUCT_SAVING||$("pd").hasAttribute("open"))return;
resetPreparedPrints();
REFRESHING=true;
var refreshButton=$("refreshDataButton");
if(refreshButton){refreshButton.disabled=true;refreshButton.textContent="Atualizando dados..."}
try{
var activeView=document.querySelector(".view.on"),activeTab=activeView?Number(activeView.id.slice(1)):1;
await loadData();
Object.keys(cart).forEach(function(id){
var product=P(id);
if(!product||product.p==null){delete cart[id];return}
if(product.e!=null&&cart[id]>product.e)cart[id]=product.e;
if(cart[id]<=0)delete cart[id]
});
saveCart();
drawCats();drawGrid();drawHist();hdr();sum();
if(activeTab===4)drawProds();
if(activeTab===5)await loadAdminSummary();
if(!silent)toast(" impressora continua conectada.")
}catch(error){
console.error(error);
toast("Não foi possível atualizar os dados: "+error.message)
}finally{
REFRESHING=false;
if(refreshButton){refreshButton.disabled=false;refreshButton.textContent="↻ Atualizar dados (sem desconectar)"}
}
}
window.addEventListener("online",function(){if(AUTH)refreshAppData(true)});
document.addEventListener("visibilitychange",function(){if(AUTH&&document.visibilityState==="visible")refreshAppData(true)});
var PRINT_PREPARING=false,PRINT_PREPARATION=0,SAVE_REQUEST=null,LOGGING_OUT=false,ANDROID_PRINT=null;
function printDestinationOf(order){return order.impressao_destino==="web_bluetooth"?"web_bluetooth":"simple_bluetooth"}
function printDestinationLabel(destination){
return destination==="web_bluetooth"?"Web Bluetooth (histórico)":"Bluetooth-USB Thermal Printer+"
}
function getSavedOrder(id){return hist.concat(orders).filter(function(order){return order.id==id})[0]}
function canPrintSavedOrder(order,destination){return !!(!LOGGING_OUT&&AUTH&&order&&["station","admin"].indexOf(AUTH.role)!==-1&&order.estacao_id===AUTH.station_id&&!order.cancel&&(!destination||printDestinationOf(order)===destination))}
function canPrintWithCurrentMethod(order){
return canPrintSavedOrder(order)&&($("printDestination").value==="android_app"||printDestinationOf(order)==="simple_bluetooth");
}
function latestPrintableOrder(){
  var latest=null;
  hist.concat(orders).forEach(function(order){
    if(canPrintWithCurrentMethod(order)&&(!latest||order.id>latest.id))latest=order;
  });
  return latest;
}
function updateReprintButton(){
  var order=latestPrintableOrder(),button=$("reprintLast");
  button.hidden=!order;
  button.disabled=SENDING||PRINT_PREPARING;
  if(order)button.setAttribute("aria-label","Reimprimir pedido "+order.id);
}
function reprintLastOrder(){
  var order=latestPrintableOrder();
  if(order)printSelectedOrder(order.id);
}
function resetPreparedPrints(){
PRINT_PREPARATION++;PRINT_PREPARING=false;
ANDROID_PRINT=null;
$("androidPrintSaved").hidden=true;
$("androidPrintOpen").hidden=false;
if(window.PrintBridge)window.PrintBridge.reset()
}
function isAndroidDevice(){
return /Android/i.test(navigator.userAgent+" "+(navigator.userAgentData&&navigator.userAgentData.platform||""));
}
function restorePrintDestination(){
var selector=$("printDestination"),android=isAndroidDevice();
var chosen=null;
try{chosen=localStorage.getItem("da-lanches-printer:"+AUTH.station_id)}catch(error){}
selector.value=window.location.pathname==="/android"?"android_app":chosen==="android_app"?"android_app":chosen==="print_bridge"?"print_bridge":android?"android_app":"print_bridge";
}
function changePrintDestination(){
if(SENDING)return;
resetPreparedPrints();
try{if(AUTH)localStorage.setItem("da-lanches-printer:"+AUTH.station_id,$("printDestination").value)}catch(error){}
$("printBridgeSettings").style.display=$("printDestination").value==="print_bridge"?"block":"none";
$("androidPrinterSettings").hidden=$("printDestination").value!=="android_app";
$("printDestinationHelp").textContent=$("printDestination").value==="print_bridge"?
  "O pedido segue pela internet para o Android e sai na impressora conectada a ele. Teste gratuito limitado a 10 impressões por aparelho.":
  "No Android, ative o serviço de impressão Bluetooth-USB Thermal Printer+. Ao imprimir, selecione esse serviço e o papel de 58 mm. A nota usa letra de 14 pt.";
sum();drawHist()
}
function orderPrintButton(order){
if(!canPrintWithCurrentMethod(order))return "";
var busy=SENDING||PRINT_PREPARING;
return '<button class="btn" type="button" data-print-order="'+order.id+'" aria-label="Reimprimir pedido '+order.id+'" aria-busy="'+(busy?"true":"false")+'"'+(busy?' disabled':'')+' onclick="printSelectedOrder('+order.id+')">Reimprimir pedido</button>'
}
function togglePrinterSettings(){
var settings=$("printerSettings");
if(settings.hasAttribute("open"))settings.removeAttribute("open");
else settings.setAttribute("open","");
}
function prepareAndroidPrint(order,reprint){
ANDROID_PRINT={order:order,reprint:reprint,lastAttempt:0};
$("androidPrintMessage").textContent="Pedido #"+order.id+" salvo. Selecione Bluetooth-USB Thermal Printer+ e papel de 58 mm para imprimir com a letra maior.";
$("androidPrintOpen").textContent="Imprimir nota com letra maior";
$("androidPrintOpen").hidden=false;
$("androidPrintSaved").hidden=false;
}
function openAndroidPrint(){
var prepared=ANDROID_PRINT;
if(!prepared||$("printDestination").value!=="android_app"||!canPrintSavedOrder(prepared.order))return;
var now=new Date().getTime();
if(prepared.lastAttempt&&now-prepared.lastAttempt<1500)return;
prepared.lastAttempt=now;
var receipt=$("androidNativeReceipt"),section=0,lastItem=null;
receipt.textContent="";
function add(tag,text,className){
var element=document.createElement(tag);
element.textContent=text;
if(className)element.className=className;
receipt.appendChild(element);
return element;
}
String(ticketText(prepared.order,prepared.reprint)).replace(/[\x00-\x09\x0b-\x1f\x7f]/g,"").split("\n").forEach(function(line){
line=line.replace(/\[\/?(?:small|center|right|large)\]/gi,"").replace(/\*\*/g,"").trim();
if(!line)return;
if(line==="--------------------------------"){section++;add("hr","");return}
if(section===1){
if(/^\d+x\s/.test(line)||!lastItem)lastItem=add("p",line,"native-item");
else lastItem.textContent+=" "+line;
}else add("p",line,section===0?"native-heading":"native-footer");
});
document.documentElement.classList.add("native-receipt-print");
function finish(){
document.documentElement.classList.remove("native-receipt-print");
window.removeEventListener("afterprint",finish);
}
window.addEventListener("afterprint",finish);
try{window.print()}catch(error){finish();throw error}
}
function printSavedNow(order,reprint){
if(!canPrintSavedOrder(order))return;
if($("printDestination").value==="android_app"){
prepareAndroidPrint(order,reprint);
return openAndroidPrint();
}
if(!window.PrintBridge)throw new Error("A integração não carregou. Recarregue a página e reimprima pelo histórico.");
return window.PrintBridge.print(order,reprint)
}
async function send(){
 if(SENDING||PRINT_PREPARING||LOGGING_OUT||!AUTH)return;
 if(!count())return;
 resetPreparedPrints();
 var saveRequest={owner:AUTH,generation:PRINT_PREPARATION};SAVE_REQUEST=saveRequest;
 SENDING=true;$("rev").disabled=true;$("rev").textContent="Salvando pedido...";$("printDestination").disabled=true;updateReprintButton();
 var order=null;
 try{
 var result=await api("/api/pedidos",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({impressao_destino:"simple_bluetooth",itens:Object.keys(cart).map(function(i){return{id:Number(i),q:cart[i]}})})});
 if(SAVE_REQUEST!==saveRequest||AUTH!==saveRequest.owner||PRINT_PREPARATION!==saveRequest.generation)return;
 order=pedidoFromApi(result.pedido);orders.unshift(order);seq=Math.max(seq,order.id+1);
 Object.keys(cart).forEach(function(i){var product=P(i);if(product&&product.e!=null)product.e=Math.max(0,product.e-cart[i])});
 cart={};saveCart();sum();hdr();drawHist();
 await printSavedNow(order,false);
 }catch(error){console.error(error);toast(order?"Pedido salvo. "+error.message:"Não foi possível salvar: "+error.message)}
 finally{if(SAVE_REQUEST===saveRequest){SAVE_REQUEST=null;SENDING=false;$("printDestination").disabled=false;sum();drawHist()}}
}
async function printSelectedOrder(id){
var order=getSavedOrder(id);
if(!canPrintWithCurrentMethod(order)||SENDING||PRINT_PREPARING)return;
resetPreparedPrints();PRINT_PREPARING=true;updateReprintButton();drawHist();
var generation=PRINT_PREPARATION,owner=AUTH,timer;
try{
var result=await Promise.race([
api("/api/pedidos/"+id+"/impressao/preparar",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({destino:printDestinationOf(order)})}),
new Promise(function(resolve,reject){timer=setTimeout(function(){reject(new Error("O servidor não respondeu. O pedido continua salvo."))},15000)})
]);
if(generation!==PRINT_PREPARATION||AUTH!==owner||LOGGING_OUT)return;
var fresh=result.pedido;
if(!fresh||fresh.id!==id||!canPrintSavedOrder(fresh,printDestinationOf(order)))throw new Error("Pedido indisponível nesta estação.");
fresh=pedidoFromApi(fresh);Object.keys(fresh).forEach(function(key){order[key]=fresh[key]});
await printSavedNow(order,true);
}catch(error){toast("Não foi possível imprimir: "+error.message)}
finally{clearTimeout(timer);if(generation===PRINT_PREPARATION){PRINT_PREPARING=false;drawHist();sum()}}
}
var printContext={getAuth:function(){return AUTH},getOrder:getSavedOrder,canPrint:canPrintSavedOrder,onMessage:toast,request:function(path,options){return api(path,options)}};
if(window.PrintBridge)window.PrintBridge.configure(printContext);
startAuthApp();
