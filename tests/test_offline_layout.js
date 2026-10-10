/* Optional real-browser layout regression. Node built-ins only; no live Portal APIs.
 * Run: CHROME_BIN=/opt/google/chrome/chrome node tests/test_offline_layout.js
 */
const fs = require('fs'), cp = require('child_process'), http = require('http'), assert = require('assert');
const chromeBin = process.env.CHROME_BIN || '/opt/google/chrome/chrome';
const profile = fs.mkdtempSync('/tmp/portal-offline-layout-');
let chrome, ws, server;
const sleep = ms => new Promise(r => setTimeout(r, ms));
let online = false;
const sample = () => ({status:'ok',server_time:Date.now()/1000,sources:{metrics_status:'ok'},devices:[
  {device_id:'a',display_name:'Offline Device',beszel_status:online?'up':'down',last_seen:new Date(Date.now()-3720000).toISOString()},
  {device_id:'b',display_name:'Multi-day Offline',beszel_status:online?'up':'paused',last_seen:new Date(Date.now()-7*86400000-3720000).toISOString()},
  {device_id:'c',display_name:'Missing Time',beszel_status:online?'up':'down'},
  {device_id:'d',display_name:'Online Device',beszel_status:'up'}]});
(async () => {
 server = http.createServer((req,res) => {
  const path = req.url.split('?')[0];
  if(path.startsWith('/api/')) {res.setHeader('Content-Type','application/json');res.end(JSON.stringify(path==='/api/dashboard'?sample():{status:'ok',devices:[]}));return;}
  if(path==='/' || path==='/lite') {
   let html=fs.readFileSync('templates/'+(path==='/'?'index':'lite')+'.html','utf8');
   html=html.replace(/\{\{ app_name \}\}/g,'HomeLab Portal Test').replace(/\{\{ url_for\('static', filename='([^']+)'\) \}\}/g,'/static/$1')
     .replace(/\{\{ url_for\('lite'\) \}\}/g,'/lite').replace(/\{\{ url_for\('index'\) \}\}/g,'/');
   res.setHeader('Content-Type','text/html');res.end(html);return;
  }
  if(/^\/static\/[a-z-]+\.(js|css)$/.test(path)) {res.setHeader('Content-Type',path.endsWith('.js')?'application/javascript':'text/css');res.end(fs.readFileSync('.'+path));return;}
  res.writeHead(404);res.end();
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const base='http://127.0.0.1:'+server.address().port;
 chrome=cp.spawn(chromeBin,['--headless','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:'ignore'});
 let port;
 for(let i=0;i<100;i++){try{port=fs.readFileSync(profile+'/DevToolsActivePort','utf8').split('\n')[0];break;}catch(e){await sleep(100);}}
 assert(port,'Chrome unavailable');
 const targets=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
 ws=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
 await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
 let id=0,pending={};ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id&&pending[m.id]){pending[m.id](m);delete pending[m.id];}};
 function send(method,params={}){return new Promise((resolve,reject)=>{const n=++id;pending[n]=m=>m.error?reject(Error(JSON.stringify(m.error))):resolve(m.result);ws.send(JSON.stringify({id:n,method,params}));});}
 async function evalJS(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true});assert(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result.value;}
 await send('Page.enable');
 for(const path of ['/','/lite']) {
  online=false;await send('Page.navigate',{url:base+path});
  for(let i=0;i<100;i++){if(await evalJS('document.querySelectorAll(".offline-seen").length === 3'))break;await sleep(100);}
  assert(await evalJS('document.querySelectorAll(".offline-seen").length === 3'));
  for(const width of [320,375,768,1024]) {
   await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});await sleep(100);
   const layout=await evalJS(`(function(){
     var items=document.querySelectorAll('.offline-seen'),ok=true,aligned=true,styles=true;
     function textRect(node){var range=document.createRange();range.selectNodeContents(node);return range.getClientRects()[0];}
     for(var i=0;i<items.length;i++){
       var note=items[i],r=note.getBoundingClientRect(),style=getComputedStyle(note);
       ok=ok&&r.right<=innerWidth&&note.scrollWidth<=note.clientWidth+1;
       styles=styles&&style.fontSize==='12px'&&style.color==='rgb(85, 85, 85)'&&style.fontWeight==='400';
       var isFull=!!document.querySelector('.mini-card');
       var status=isFull?note.previousSibling:note.parentNode.firstChild;
       var a=textRect(status),b=textRect(note);
       if(a&&b){aligned=aligned&&(Math.abs(a.top-b.top)<=1||b.top>=a.bottom);}
       styles=styles&&parseFloat(isFull?style.paddingLeft:style.marginLeft)===10;
       var red=getComputedStyle(isFull?status:note.parentNode);
       styles=styles&&red.fontWeight==='700'&&(red.color==='rgb(160, 0, 32)');
       if(i===0){ok=ok&&/^Last: \\d{2}:\\d{2} \\(1h02m\\)$/.test(note.textContent);}
       if(i===1){ok=ok&&/^Last: \\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2} \\(7d01h02m\\)$/.test(note.textContent);}
       if(i===2){ok=ok&&note.textContent==='Last: —';}
     }
     var cards=document.querySelectorAll('.mini-card'),grid=true;
     if(cards.length===4){
       var expected=innerWidth>800?4:innerWidth>600?2:1;
       for(var j=0;j<cards.length;j++){
         var c=cards[j].getBoundingClientRect();
         if(j%expected){var prev=cards[j-1].getBoundingClientRect();grid=grid&&Math.abs(c.top-prev.top)<=1&&c.left>=prev.right;}
         else if(j){grid=grid&&c.top>=cards[j-expected].getBoundingClientRect().bottom;}
       }
     }
     return {width:innerWidth,scroll:document.documentElement.scrollWidth,ok:ok,aligned:aligned,styles:styles,grid:grid};
   }())`);
   assert(layout.ok&&layout.aligned&&layout.styles&&layout.grid&&layout.scroll<=layout.width+1,JSON.stringify(layout));
   console.log(path,'offline layout PASS',width);
  }
  // Tick retained DOM without a request; then confirm actual online polling removes hints.
  await evalJS('OfflineSeen.sync(Date.now()/1000+120); OfflineSeen.update()');
  assert(await evalJS('document.querySelector(".offline-seen").textContent.indexOf("(1h04m)") >= 0'));
  online=true;
  for(let i=0;i<70;i++){if(await evalJS('document.querySelectorAll(".offline-seen").length === 0'))break;await sleep(100);}
  assert(await evalJS('document.querySelectorAll(".offline-seen").length === 0'));
  console.log(path,'ONLINE recovery hides all hints PASS');
 }
})().then(()=>{if(ws)ws.close();if(chrome)chrome.kill('SIGTERM');if(server)server.close();}).catch(e=>{console.error(e);if(ws)ws.close();if(chrome)chrome.kill('SIGTERM');if(server)server.close();process.exitCode=1;});
